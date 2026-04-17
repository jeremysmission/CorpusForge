"""Inspect a Forge export's metadata surface for V2 contract review.

Plain-English role
------------------
Offline tool. Reads a completed export folder and compares the fields
actually present on each chunk against the planned V2 metadata
contract (authority tier, archive class, log-record fields, cyber
fields, etc.). Reports field coverage and highlights any contract
gaps — missing source_ext, missing source_doc_hash, missing legacy
alias keys in ``skip_manifest.json``, and similar.

Used by the Forge + V2 integration team to confirm that each export
honors the V2 import contract before it is shipped over.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

CURRENT_CHUNK_FIELDS = [
    "chunk_id",
    "text",
    "enriched_text",
    "source_path",
    "chunk_index",
    "text_length",
    "parse_quality",
]

PLANNED_METADATA_FIELDS = [
    "source_ext",
    "source_doc_hash",
    "authority_tier",
    "authority_signals",
    "business_domain",
    "archive_class",
    "archive_depth",
    "is_archive_derived",
    "is_visual_heavy",
    "visual_family",
    "table_heavy",
    "is_ocr",
    "doc_date",
    "site_token",
    "program_token",
    "identifier_tokens",
    "log_clin",
    "log_vendor",
    "log_purchase_req",
    "log_purchase_order",
    "log_part_number",
    "log_model_number",
    "log_oem",
    "log_nomenclature",
    "log_qty",
    "log_serial_number",
    "log_acquisition_contract_code",
    "log_acquisition_cost",
    "log_acquisition_date",
    "log_revision",
    "log_remarks",
    "cyber_report_family",
    "cyber_scan_date",
    "cyber_system_scope",
    "cyber_site_scope",
    "cyber_finding_id",
    "cyber_severity",
    "cyber_status",
    "cyber_waiver_flag",
]

ENTITY_FIELDS = [
    "chunk_id",
    "text",
    "label",
    "score",
    "start",
    "end",
    "source_path",
]


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


def _load_json(path: Path) -> dict[str, Any]:
    """Read one JSON file, returning an empty dict when the file is missing."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _iter_jsonl(path: Path):
    """Yield one parsed JSON record per non-empty line of a JSONL file."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                yield json.loads(line)


def _has_value(value: Any) -> bool:
    """True when a field is present and non-empty (not None, '', or empty container)."""
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _bucket_parse_quality(value: Any) -> str:
    """Classify a parse_quality score into coarse human-readable buckets."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "missing"
    if score >= 0.95:
        return "0.95-1.00"
    if score >= 0.85:
        return "0.85-0.94"
    if score >= 0.70:
        return "0.70-0.84"
    return "<0.70"


def _summarize_field_presence(
    field_order: list[str],
    counts: Counter[str],
    total_rows: int,
) -> list[dict[str, Any]]:
    """Return per-field coverage rows: how often each field appears in the export."""
    rows: list[dict[str, Any]] = []
    for field in field_order:
        present = int(counts.get(field, 0))
        rows.append({
            "field": field,
            "present_rows": present,
            "coverage_pct": round((present / total_rows * 100.0), 2) if total_rows else 0.0,
        })
    return rows


def analyze_export_metadata_contract(export_dir: str | Path) -> dict[str, Any]:
    """Summarize the metadata/export contract surface of one Forge export."""
    export_path, redirect_from = resolve_export_dir(export_dir)

    chunks_path = export_path / "chunks.jsonl"
    entities_path = export_path / "entities.jsonl"
    manifest_path = export_path / "manifest.json"
    skip_manifest_path = export_path / "skip_manifest.json"
    run_report_path = export_path / "run_report.txt"

    manifest = _load_json(manifest_path)
    skip_manifest = _load_json(skip_manifest_path)

    chunk_field_counts: Counter[str] = Counter()
    chunk_key_counts: Counter[str] = Counter()
    ext_counts: Counter[str] = Counter()
    parse_quality_buckets: Counter[str] = Counter()
    source_docs: set[str] = set()
    chunk_rows = 0

    for row in _iter_jsonl(chunks_path) or []:
        chunk_rows += 1
        chunk_key_counts.update(row.keys())
        for field in CURRENT_CHUNK_FIELDS + PLANNED_METADATA_FIELDS:
            if field in row and _has_value(row[field]):
                chunk_field_counts[field] += 1

        source_path = str(row.get("source_path", ""))
        if source_path:
            source_docs.add(source_path)
            ext_counts[Path(source_path).suffix.lower() or "[no_ext]"] += 1

        parse_quality_buckets[_bucket_parse_quality(row.get("parse_quality"))] += 1

    entity_field_counts: Counter[str] = Counter()
    entity_key_counts: Counter[str] = Counter()
    entity_rows = 0
    for row in _iter_jsonl(entities_path) or []:
        entity_rows += 1
        entity_key_counts.update(row.keys())
        for field in ENTITY_FIELDS:
            if field in row and _has_value(row[field]):
                entity_field_counts[field] += 1

    legacy_aliases = {
        "count": "count" in skip_manifest,
        "skipped_files": "skipped_files" in skip_manifest,
        "deferred_formats": "deferred_formats" in skip_manifest,
    }

    contract_gaps: list[str] = []
    if chunk_field_counts.get("source_ext", 0) == 0:
        contract_gaps.append("chunks.jsonl does not emit source_ext today.")
    if chunk_field_counts.get("source_doc_hash", 0) == 0:
        contract_gaps.append("chunks.jsonl does not emit source_doc_hash today.")
    if chunk_field_counts.get("authority_tier", 0) == 0:
        contract_gaps.append("chunks.jsonl does not emit authority/domain/archive metadata today.")
    if not all(legacy_aliases.values()):
        contract_gaps.append("skip_manifest.json is missing one or more legacy V2 alias keys.")
    if entity_rows > 0 and entity_field_counts.get("source_path", 0) == 0:
        contract_gaps.append("entities.jsonl rows omit source_path and require chunk_id backfill.")

    return {
        "export_dir": str(export_path),
        "redirect_from": redirect_from,
        "artifacts": {
            "chunks_jsonl": {
                "path": str(chunks_path),
                "exists": chunks_path.exists(),
                "size_bytes": chunks_path.stat().st_size if chunks_path.exists() else 0,
            },
            "entities_jsonl": {
                "path": str(entities_path),
                "exists": entities_path.exists(),
                "size_bytes": entities_path.stat().st_size if entities_path.exists() else 0,
            },
            "manifest_json": {
                "path": str(manifest_path),
                "exists": manifest_path.exists(),
                "size_bytes": manifest_path.stat().st_size if manifest_path.exists() else 0,
            },
            "skip_manifest_json": {
                "path": str(skip_manifest_path),
                "exists": skip_manifest_path.exists(),
                "size_bytes": skip_manifest_path.stat().st_size if skip_manifest_path.exists() else 0,
            },
            "run_report_txt": {
                "path": str(run_report_path),
                "exists": run_report_path.exists(),
                "size_bytes": run_report_path.stat().st_size if run_report_path.exists() else 0,
            },
        },
        "manifest_summary": {
            "chunk_count": manifest.get("chunk_count"),
            "vector_dim": manifest.get("vector_dim"),
            "vector_dtype": manifest.get("vector_dtype"),
            "entity_count": manifest.get("entity_count"),
            "embedding_model": manifest.get("embedding_model"),
            "timestamp": manifest.get("timestamp"),
            "stats_keys": sorted((manifest.get("stats") or {}).keys()),
        },
        "chunk_schema": {
            "rows": chunk_rows,
            "unique_source_files": len(source_docs),
            "unique_keys": sorted(chunk_key_counts),
            "field_presence": _summarize_field_presence(
                CURRENT_CHUNK_FIELDS + PLANNED_METADATA_FIELDS,
                chunk_field_counts,
                chunk_rows,
            ),
            "top_extensions": [
                {"extension": ext, "count": count}
                for ext, count in ext_counts.most_common(15)
            ],
            "parse_quality_buckets": dict(parse_quality_buckets),
        },
        "entities_artifact": {
            "rows": entity_rows,
            "unique_keys": sorted(entity_key_counts),
            "field_presence": _summarize_field_presence(
                ENTITY_FIELDS,
                entity_field_counts,
                entity_rows,
            ),
        },
        "skip_manifest_summary": {
            "keys": sorted(skip_manifest),
            "total_skipped": skip_manifest.get("total_skipped"),
            "counts_by_reason": skip_manifest.get("counts_by_reason", {}),
            "legacy_aliases_present": legacy_aliases,
            "deferred_formats_count": len(skip_manifest.get("deferred_formats", []))
            if isinstance(skip_manifest.get("deferred_formats"), list)
            else 0,
        },
        "contract_gaps": contract_gaps,
    }


def write_export_metadata_contract(output_json: str | Path, export_dir: str | Path) -> Path:
    """Analyze and write one JSON payload to disk."""
    payload = analyze_export_metadata_contract(export_dir)
    output_path = Path(output_json).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_path
