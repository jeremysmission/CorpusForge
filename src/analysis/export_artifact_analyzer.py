"""Analyze a Forge export package for corpus-adaptation work.

Plain-English role
------------------
Offline tool. Takes a finished export folder plus a failure artifact
(the parser-failure log) and produces one JSON summary: which formats
dominate, which known document families were seen, how parse quality
was distributed, what types of files ended up in skip, and which
extensions or families are responsible for most failures.

Used by PMs and operators when deciding how to adjust skip/defer,
parser timeouts, and extraction coverage before the next run.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


FAMILY_PATTERNS = {
    "travel_admin": ["itinerary", "travel approval", "receipts", "packing list"],
    "inventory_manifest": ["inventory", "manifest"],
    "image_photo": ["photo", "photos", "image", "images", "picture", "pictures"],
    "logs": ["desktop_log", "desktop log", "\\logs\\", "/logs/"],
    "archive_derived": ["\\archive\\", "/archive/", "specialfiles"],
    "drawing_diagram": ["drawing", "drawings", "diagram"],
    "calibration_cert": ["calibration", "certificate", "cert of", "certification"],
}

SPECIAL_DIR_NAMES = {
    "packing list",
    "site inventory",
    "pictures",
    "photos",
    "itinerary",
    "archive",
    "receipts",
    "drawings",
    "images",
}

FAILURE_SUMMARY_RE = re.compile(
    r"^###\s+(\.[^\s]+)\s+\((\d+) files\)\nLikely cause:\s+(.+)$",
    re.MULTILINE,
)
FAILURE_LINE_RE = re.compile(r"^\[([^\]]+)\]\s")


def _load_json(path: Path) -> dict:
    """Read a UTF-8 JSON file and return its parsed dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_chunks(chunks_path: Path):
    """Yield one chunk-dict per line from a chunks.jsonl file."""
    with open(chunks_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                yield json.loads(line)


def analyze_export_artifacts(
    export_dir: str | Path,
    *,
    failure_artifact: str | Path,
    sample_profile_json: str | Path | None = None,
) -> dict:
    """Summarize one export package plus a real failure artifact."""
    export_path = Path(export_dir).resolve()
    failure_path = Path(failure_artifact).resolve()
    sample_profile_path = Path(sample_profile_json).resolve() if sample_profile_json else None

    manifest_path = export_path / "manifest.json"
    skip_manifest_path = export_path / "skip_manifest.json"
    chunks_path = export_path / "chunks.jsonl"
    run_report_path = export_path / "run_report.txt"

    manifest = _load_json(manifest_path)
    skip = _load_json(skip_manifest_path)

    chunk_ext = Counter()
    chunk_parse_quality_bucket = Counter()
    chunk_source_docs = Counter()
    chunk_text_len_by_ext = defaultdict(int)
    family_docs: dict[str, set[str]] = defaultdict(set)
    family_chunks = Counter()
    family_examples: dict[str, list[str]] = defaultdict(list)
    special_dir_hits = Counter()
    archive_path_chunks = 0
    image_path_chunks = 0
    drawing_path_chunks = 0

    for row in _iter_chunks(chunks_path):
        source = row["source_path"]
        source_path = Path(source)
        ext = source_path.suffix.lower() or "[no_ext]"
        lower_source = source.lower()

        chunk_ext[ext] += 1
        chunk_source_docs[source] += 1
        chunk_text_len_by_ext[ext] += row.get("text_length", 0)

        parse_quality = row.get("parse_quality", 0.0)
        if parse_quality >= 0.95:
            chunk_parse_quality_bucket["0.95-1.00"] += 1
        elif parse_quality >= 0.85:
            chunk_parse_quality_bucket["0.85-0.94"] += 1
        elif parse_quality >= 0.70:
            chunk_parse_quality_bucket["0.70-0.84"] += 1
        else:
            chunk_parse_quality_bucket["<0.70"] += 1

        if "\\archive\\" in lower_source or "/archive/" in lower_source:
            archive_path_chunks += 1
        if any(segment in lower_source for segment in ("\\images\\", "\\photos\\", "\\pictures\\", "/images/", "/photos/", "/pictures/")):
            image_path_chunks += 1
        if any(segment in lower_source for segment in ("drawing", "drawings", "diagram")):
            drawing_path_chunks += 1

        for part in (part.lower() for part in source_path.parts):
            if part in SPECIAL_DIR_NAMES:
                special_dir_hits[part] += 1

        for family, patterns in FAMILY_PATTERNS.items():
            if any(pattern in lower_source for pattern in patterns):
                family_docs[family].add(source)
                family_chunks[family] += 1
                if len(family_examples[family]) < 5 and source not in family_examples[family]:
                    family_examples[family].append(source)

    ext_to_doc_counts = Counter(Path(source).suffix.lower() or "[no_ext]" for source in chunk_source_docs)
    avg_chunks_per_doc_by_ext_top = [
        {
            "extension": ext,
            "doc_count": ext_to_doc_counts[ext],
            "chunk_count": chunk_ext[ext],
            "avg_chunks_per_doc": round(chunk_ext[ext] / ext_to_doc_counts[ext], 1),
        }
        for ext, _count in chunk_ext.most_common(15)
    ]

    basename_to_paths: dict[str, set[str]] = defaultdict(set)
    for source in chunk_source_docs:
        basename_to_paths[Path(source).name.lower()].add(source)
    reused_basenames = [
        {
            "basename": name,
            "path_count": len(paths),
            "paths": sorted(paths)[:5],
        }
        for name, paths in basename_to_paths.items()
        if len(paths) > 1
    ]
    reused_basenames.sort(key=lambda row: (-row["path_count"], row["basename"]))

    skip_ext = Counter()
    for row in skip["files"]:
        skip_ext[Path(row["path"]).suffix.lower() or "[no_ext]"] += 1

    failure_text = failure_path.read_text(encoding="utf-8")
    failure_summary = [
        {
            "extension": match.group(1),
            "count": int(match.group(2)),
            "likely_cause": match.group(3).strip(),
        }
        for match in FAILURE_SUMMARY_RE.finditer(failure_text)
    ]

    raw_failure_counts = Counter()
    for line in failure_text.splitlines():
        match = FAILURE_LINE_RE.match(line)
        if match:
            raw_failure_counts[f".{match.group(1).lower()}"] += 1

    return {
        "generated_at": datetime.now().isoformat(),
        "sample_profile_json": str(sample_profile_path) if sample_profile_path else "",
        "export_dir": str(export_path),
        "manifest_path": str(manifest_path),
        "run_report_path": str(run_report_path),
        "skip_manifest_path": str(skip_manifest_path),
        "chunks_path": str(chunks_path),
        "failure_artifact_path": str(failure_path),
        "manifest_stats": manifest["stats"],
        "chunk_ext_top": chunk_ext.most_common(15),
        "avg_chunks_per_doc_by_ext_top": avg_chunks_per_doc_by_ext_top,
        "parse_quality_buckets": dict(chunk_parse_quality_bucket),
        "distinct_source_docs_in_chunks": len(chunk_source_docs),
        "family_doc_counts": {
            family: len(paths)
            for family, paths in sorted(family_docs.items(), key=lambda item: -len(item[1]))
        },
        "family_chunk_counts": dict(family_chunks.most_common()),
        "family_examples": family_examples,
        "archive_path_chunks": archive_path_chunks,
        "image_path_chunks": image_path_chunks,
        "drawing_path_chunks": drawing_path_chunks,
        "special_dir_hits": special_dir_hits.most_common(15),
        "skip_reason_counts": skip["counts_by_reason"],
        "skip_ext_top": skip_ext.most_common(15),
        "reused_basenames_top": reused_basenames[:25],
        "failure_summary": failure_summary,
        "raw_failure_counts": dict(raw_failure_counts),
    }


def write_export_analysis(
    output_json: str | Path,
    export_dir: str | Path,
    *,
    failure_artifact: str | Path,
    sample_profile_json: str | Path | None = None,
) -> Path:
    """Analyze and write one JSON payload to disk."""
    payload = analyze_export_artifacts(
        export_dir,
        failure_artifact=failure_artifact,
        sample_profile_json=sample_profile_json,
    )
    output_path = Path(output_json).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return output_path
