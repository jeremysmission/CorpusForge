"""
Lightweight integrity gate for a Forge export package.

What it does for the operator:
  A fast PASS / FAIL check on an export folder, designed for very large
  exports where a full in-memory audit would be slow. It confirms that:
    - All required artifact files are present
    - chunks.jsonl line count matches manifest.chunk_count matches
      vectors.npy row count (one vector per chunk, no drift)
    - vectors.npy is a readable 2D array with the declared dimension
    - entities.jsonl line count matches manifest.entity_count
    - skip_manifest.json parses and its totals are internally consistent
    - run_report.txt exists and is non-empty

  This is a *count and integrity* gate, NOT a per-row schema check.
  (Use audit_corpus.py or inspect_export_quality.py for deeper review.)

How to read the result:
  - PASS  -> the export is internally consistent and safe to hand off.
  - FAIL  -> there's a real mismatch. Do NOT import into HybridRAG V2
             until the listed issue is resolved.
  - WARN  -> non-blocking inconsistencies (e.g. stats drift). Review,
             but do not necessarily abort.

When to run it:
  - Immediately after a long ingest finishes
  - Before copying/exporting to the GovCloud bucket or to V2

Inputs:
  --export-dir    Export folder path, or a "latest" redirect file.
  --json          Emit JSON to stdout instead of the human-readable block.
  --output-json   Also write the full JSON report to this file.

Exit codes:
  0 = PASS (ok to proceed)
  1 = FAIL (integrity issue; must be fixed)

Usage:
  python scripts/check_export_integrity.py --export-dir data/production_output/export_YYYYMMDD_HHMM
  python scripts/check_export_integrity.py --export-dir data/production_output/latest
  python scripts/check_export_integrity.py --export-dir data/production_output/latest --json
  python scripts/check_export_integrity.py --export-dir data/production_output/latest --output-json reports/export_integrity.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_ARTIFACTS = (
    "chunks.jsonl",
    "vectors.npy",
    "manifest.json",
    "run_report.txt",
    "skip_manifest.json",
    "entities.jsonl",
)


def resolve_export_dir(path_arg: str | Path) -> tuple[Path, str | None]:
    """Resolve an export directory, following the packager's latest redirect file."""
    source = Path(path_arg)
    if not source.is_absolute():
        source = (PROJECT_ROOT / source).resolve()
    else:
        source = source.resolve()

    redirect_from: str | None = None
    if source.is_file() and source.name.lower() == "latest":
        target = source.read_text(encoding="utf-8-sig").strip()
        if not target:
            raise FileNotFoundError(f"Redirect file is empty: {source}")
        redirect_from = str(source)
        source = Path(target).expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(f"Export path not found: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"Export path is not a directory: {source}")
    return source, redirect_from


def count_jsonl_lines(path: Path) -> int:
    """Count JSONL rows efficiently without loading the whole file into memory."""
    total = 0
    last_byte = b""
    with open(path, "rb", buffering=8 * 1024 * 1024) as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            total += chunk.count(b"\n")
            last_byte = chunk[-1:]
    if path.stat().st_size > 0 and last_byte != b"\n":
        total += 1
    return total


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file from disk and return its contents as a dict."""
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def check_export_integrity(export_dir: Path) -> dict[str, Any]:
    """Run every integrity check against the given export folder and return a structured report dict."""
    issues: list[str] = []
    warnings: list[str] = []
    artifacts: dict[str, dict[str, Any]] = {}

    for name in REQUIRED_ARTIFACTS:
        artifact_path = export_dir / name
        present = artifact_path.exists()
        size_bytes = artifact_path.stat().st_size if present else None
        artifacts[name] = {
            "path": str(artifact_path),
            "present": present,
            "size_bytes": size_bytes,
        }
        if not present:
            issues.append(f"missing required artifact: {name}")

    manifest: dict[str, Any] = {}
    skip_manifest: dict[str, Any] = {}
    if issues:
        return {
            "export_dir": str(export_dir),
            "artifacts": artifacts,
            "manifest": manifest,
            "skip_manifest": skip_manifest,
            "counts": {},
            "warnings": warnings,
            "issues": issues,
            "ok": False,
        }

    manifest_path = export_dir / "manifest.json"
    skip_manifest_path = export_dir / "skip_manifest.json"
    run_report_path = export_dir / "run_report.txt"
    chunks_path = export_dir / "chunks.jsonl"
    vectors_path = export_dir / "vectors.npy"
    entities_path = export_dir / "entities.jsonl"

    try:
        manifest = _load_json(manifest_path)
    except Exception as exc:
        issues.append(f"manifest.json unreadable: {exc}")
        manifest = {}

    try:
        skip_manifest = _load_json(skip_manifest_path)
    except Exception as exc:
        issues.append(f"skip_manifest.json unreadable: {exc}")
        skip_manifest = {}

    run_report_bytes = run_report_path.stat().st_size
    if run_report_bytes <= 0:
        issues.append("run_report.txt is empty")

    chunk_lines = count_jsonl_lines(chunks_path)
    entity_lines = count_jsonl_lines(entities_path)

    try:
        vectors = np.load(vectors_path, mmap_mode="r")
        vector_ndim = int(getattr(vectors, "ndim", -1))
        vector_shape = tuple(int(x) for x in getattr(vectors, "shape", ()))
        if vector_ndim != 2:
            issues.append(
                f"vectors.npy must be a 2D array; got ndim={vector_ndim} shape={vector_shape}"
            )
            vector_rows = -1
            vector_dim = -1
        else:
            vector_rows = int(vectors.shape[0])
            vector_dim = int(vectors.shape[1])
        vector_dtype = str(vectors.dtype)
    except Exception as exc:
        issues.append(f"vectors.npy unreadable: {exc}")
        vector_ndim = -1
        vector_shape = ()
        vector_rows = -1
        vector_dim = -1
        vector_dtype = "unreadable"

    manifest_chunk_count = manifest.get("chunk_count")
    manifest_vector_dim = manifest.get("vector_dim")
    manifest_entity_count = manifest.get("entity_count")
    manifest_vector_dtype = manifest.get("vector_dtype")

    if manifest_chunk_count is None:
        issues.append("manifest.json missing chunk_count")
    elif int(manifest_chunk_count) != chunk_lines:
        issues.append(
            f"manifest chunk_count {int(manifest_chunk_count):,} does not match chunks.jsonl lines {chunk_lines:,}"
        )

    if vector_rows >= 0 and vector_rows != chunk_lines:
        issues.append(
            f"vectors.npy rows {vector_rows:,} do not match chunks.jsonl lines {chunk_lines:,}"
        )

    if manifest_vector_dim is None:
        issues.append("manifest.json missing vector_dim")
    elif vector_dim >= 0 and int(manifest_vector_dim) != vector_dim:
        issues.append(
            f"manifest vector_dim {int(manifest_vector_dim)} does not match vectors.npy dim {vector_dim}"
        )

    if manifest_entity_count is None:
        warnings.append("manifest.json missing entity_count")
    elif int(manifest_entity_count) != entity_lines:
        issues.append(
            f"manifest entity_count {int(manifest_entity_count):,} does not match entities.jsonl lines {entity_lines:,}"
        )

    if manifest_vector_dtype is not None and vector_dtype != "unreadable":
        if str(manifest_vector_dtype) != vector_dtype:
            warnings.append(
                f"manifest vector_dtype {manifest_vector_dtype!r} does not match vectors.npy dtype {vector_dtype!r}"
            )

    skip_total = skip_manifest.get("total_skipped")
    skip_counts = skip_manifest.get("counts_by_reason")
    if skip_total is None:
        warnings.append("skip_manifest.json missing total_skipped")
    if not isinstance(skip_counts, dict):
        warnings.append("skip_manifest.json missing counts_by_reason map")
    elif skip_total is not None:
        summed = sum(int(v) for v in skip_counts.values())
        if int(skip_total) != summed:
            issues.append(
                f"skip_manifest total_skipped {int(skip_total):,} does not match counts_by_reason total {summed:,}"
            )

    stats = manifest.get("stats")
    if isinstance(stats, dict):
        stats_chunk_count = stats.get("chunks_created")
        stats_vector_count = stats.get("vectors_created")
        stats_entity_count = stats.get("entities_extracted")
        if stats_chunk_count is not None and int(stats_chunk_count) != chunk_lines:
            warnings.append(
                f"manifest stats.chunks_created {int(stats_chunk_count):,} does not match chunks.jsonl lines {chunk_lines:,}"
            )
        if stats_vector_count is not None and vector_rows >= 0 and int(stats_vector_count) != vector_rows:
            warnings.append(
                f"manifest stats.vectors_created {int(stats_vector_count):,} does not match vectors.npy rows {vector_rows:,}"
            )
        if stats_entity_count is not None and int(stats_entity_count) != entity_lines:
            warnings.append(
                f"manifest stats.entities_extracted {int(stats_entity_count):,} does not match entities.jsonl lines {entity_lines:,}"
            )

    return {
        "export_dir": str(export_dir),
        "artifacts": artifacts,
        "manifest": {
            "chunk_count": manifest_chunk_count,
            "vector_dim": manifest_vector_dim,
            "vector_dtype": manifest_vector_dtype,
            "entity_count": manifest_entity_count,
            "timestamp": manifest.get("timestamp"),
            "embedding_model": manifest.get("embedding_model"),
        },
        "skip_manifest": {
            "total_skipped": skip_total,
            "counts_by_reason": skip_counts if isinstance(skip_counts, dict) else {},
        },
        "counts": {
            "chunks_jsonl_lines": chunk_lines,
            "entities_jsonl_lines": entity_lines,
            "vectors_ndim": vector_ndim,
            "vectors_shape": list(vector_shape),
            "vectors_rows": vector_rows,
            "vectors_dim": vector_dim,
            "vectors_dtype": vector_dtype,
            "run_report_size_bytes": run_report_bytes,
        },
        "warnings": warnings,
        "issues": issues,
        "ok": not issues,
    }


def print_human_report(report: dict[str, Any], *, redirect_from: str | None = None) -> None:
    """Print the integrity report in the operator-friendly text format (Artifacts / Counts / Warnings / Issues / RESULT)."""
    print("=" * 60)
    print("Forge Export Integrity Check")
    print("=" * 60)
    print(f"Export:      {report['export_dir']}")
    if redirect_from:
        print(f"Resolved via: {redirect_from}")
    print()

    print("Artifacts")
    for name in REQUIRED_ARTIFACTS:
        item = report["artifacts"].get(name, {})
        state = "OK" if item.get("present") else "MISSING"
        size = item.get("size_bytes")
        size_text = f"{size:,} bytes" if isinstance(size, int) else "n/a"
        print(f"  {name:18s} {state:8s} {size_text}")
    print()

    counts = report.get("counts", {})
    manifest = report.get("manifest", {})
    skip_manifest = report.get("skip_manifest", {})
    print("Counts")
    print(f"  manifest.chunk_count     {manifest.get('chunk_count')}")
    print(f"  chunks.jsonl lines       {counts.get('chunks_jsonl_lines')}")
    print(f"  manifest.vector_dim      {manifest.get('vector_dim')}")
    print(f"  vectors.npy ndim         {counts.get('vectors_ndim')}")
    print(f"  vectors.npy shape        {counts.get('vectors_shape')}")
    print(f"  vectors.npy dtype        {counts.get('vectors_dtype')}")
    print(f"  manifest.entity_count    {manifest.get('entity_count')}")
    print(f"  entities.jsonl lines     {counts.get('entities_jsonl_lines')}")
    print(f"  skip.total_skipped       {skip_manifest.get('total_skipped')}")
    print(f"  run_report.txt bytes     {counts.get('run_report_size_bytes')}")
    print()

    if report.get("warnings"):
        print("Warnings")
        for item in report["warnings"]:
            print(f"  - {item}")
        print()

    if report.get("issues"):
        print("Issues")
        for item in report["issues"]:
            print(f"  - {item}")
        print()
        print("RESULT: FAIL")
    else:
        print("RESULT: PASS")


def main() -> int:
    """Parse CLI flags, run the integrity checks, print PASS/FAIL, and return an exit code (0=PASS, 1=FAIL)."""
    parser = argparse.ArgumentParser(description="Check Forge export integrity")
    parser.add_argument(
        "--export-dir",
        required=True,
        help="Export directory to check, or a latest redirect file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of the human-readable summary",
    )
    parser.add_argument(
        "--output-json",
        help="Optional file path to write the full JSON report",
    )
    args = parser.parse_args()

    try:
        export_dir, redirect_from = resolve_export_dir(args.export_dir)
        report = check_export_integrity(export_dir)
    except Exception as exc:
        failure = {
            "export_dir": args.export_dir,
            "artifacts": {},
            "manifest": {},
            "skip_manifest": {},
            "counts": {},
            "warnings": [],
            "issues": [str(exc)],
            "ok": False,
        }
        if args.output_json:
            output_path = Path(args.output_json)
            if not output_path.is_absolute():
                output_path = (PROJECT_ROOT / output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(failure, indent=2))
        else:
            print_human_report(failure)
        return 1

    if args.output_json:
        output_path = Path(args.output_json)
        if not output_path.is_absolute():
            output_path = (PROJECT_ROOT / output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human_report(report, redirect_from=redirect_from)

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
