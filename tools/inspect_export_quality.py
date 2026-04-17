#!/usr/bin/env python
"""
Quick trust check for a CorpusForge export.

What it does for the operator:
  Streams through the chunks.jsonl of a finished export and looks for the
  "this should not be here" red flags:
    - Basic schema health (missing keys, empty text, length mismatches)
    - Distribution of source-path extensions (did we import .zip internals
      that we meant to skip?)
    - Matches against suspicious source-path globs (e.g., *.sao.zip)
    - Hits on junk markers inside chunk text (XML relationships, etc.)
    - A handful of suspicious sample chunks to inspect by eye

  You can ALSO hard-fail the tool (exit 2) if chunks match a forbidden
  source-path glob, turning this into a pre-import gate.

How to read the result:
  PASS                    Export looks clean enough to import.
  FAIL (exit 2)           At least one forbidden glob matched chunks --
                          DO NOT import. Fix the ingest and re-run.
  No gate was requested   The tool is purely informational.

This is an operator pre-import check, not a full QA harness. Pair with
scripts/check_export_integrity.py for count/integrity gates and
scripts/audit_corpus.py for a richer corpus audit.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_SOURCE_GLOBS = ["*.sao.zip", "*.rsf.zip"]
DEFAULT_TEXT_MARKERS = ["[content_types].xml", "_rels/.rels"]
REQUIRED_KEYS = {"chunk_id", "text", "source_path"}
WHITESPACE_RE = re.compile(r"\s+")


def _preview(text: str, max_chars: int = 140) -> str:
    """Collapse whitespace and truncate chunk text into a short preview for printing."""
    collapsed = WHITESPACE_RE.sub(" ", text).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3] + "..."


def _looks_numeric_dump(text: str) -> bool:
    """Heuristic: does this chunk look like a numeric table dump (mostly digits, very few letters)?"""
    stripped = "".join(ch for ch in text if not ch.isspace())
    if len(stripped) < 80:
        return False

    digit_count = sum(ch.isdigit() for ch in stripped)
    alpha_count = sum(ch.isalpha() for ch in stripped)
    numeric_ratio = digit_count / len(stripped)
    alpha_ratio = alpha_count / len(stripped)
    return numeric_ratio >= 0.55 and alpha_ratio <= 0.20


def _matches_any_glob(path_text: str, patterns: list[str]) -> list[str]:
    """Return the glob patterns (case-insensitive) that a given source_path matches."""
    lowered = path_text.lower()
    basename = Path(lowered).name
    matches: list[str] = []
    for pattern in patterns:
        candidate = pattern.lower()
        if fnmatch.fnmatch(lowered, candidate) or fnmatch.fnmatch(basename, candidate):
            matches.append(pattern)
    return matches


def inspect_export(
    export_dir: Path,
    source_globs: list[str],
    text_markers: list[str],
    require_zero_source_globs: list[str],
    top_ext: int,
    sample_limit: int,
) -> int:
    """Stream chunks.jsonl, compute the quality snapshot, and optionally enforce PASS/FAIL gates."""
    chunks_path = export_dir / "chunks.jsonl"
    if not chunks_path.exists():
        print(f"ERROR: missing {chunks_path}")
        return 1

    ext_counts: Counter[str] = Counter()
    glob_hits: Counter[str] = Counter()
    marker_hits: Counter[str] = Counter()

    total = 0
    invalid_json = 0
    missing_required = 0
    empty_text = 0
    text_length_mismatch = 0
    suspicious_numeric = 0
    suspicious_quality = 0
    suspicious_samples: list[dict[str, str]] = []

    with open(chunks_path, "r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError:
                invalid_json += 1
                continue

            total += 1
            missing = REQUIRED_KEYS - set(chunk)
            if missing:
                missing_required += 1

            source_path = str(chunk.get("source_path", ""))
            text = str(chunk.get("text", ""))
            ext = Path(source_path).suffix.lower() or "<none>"
            ext_counts[ext] += 1

            if not text.strip():
                empty_text += 1

            text_length = chunk.get("text_length")
            if isinstance(text_length, int) and text_length != len(text):
                text_length_mismatch += 1

            reasons: list[str] = []

            matched_globs = _matches_any_glob(source_path, source_globs)
            for pattern in matched_globs:
                glob_hits[pattern] += 1
            if matched_globs:
                reasons.append("source_glob=" + ",".join(matched_globs))

            lowered_text = text.lower()
            matched_markers = [
                marker for marker in text_markers if marker.lower() in lowered_text
            ]
            for marker in matched_markers:
                marker_hits[marker] += 1
            if matched_markers:
                reasons.append("text_marker=" + ",".join(matched_markers))

            if _looks_numeric_dump(text):
                suspicious_numeric += 1
                reasons.append("numeric_dump")

            parse_quality = chunk.get("parse_quality")
            if reasons and isinstance(parse_quality, (int, float)) and parse_quality >= 0.6:
                suspicious_quality += 1
                reasons.append(f"parse_quality={parse_quality}")

            if reasons and len(suspicious_samples) < sample_limit:
                suspicious_samples.append(
                    {
                        "line": str(line_number),
                        "source_path": source_path or "<missing>",
                        "reasons": "; ".join(reasons),
                        "preview": _preview(text),
                    }
                )

    print(f"Export dir: {export_dir}")
    print(f"Chunks file: {chunks_path}")
    print()
    print("Schema health:")
    print(f"  total_chunks: {total}")
    print(f"  invalid_json_lines: {invalid_json}")
    print(f"  missing_required_keys: {missing_required}")
    print(f"  empty_text_chunks: {empty_text}")
    print(f"  text_length_mismatches: {text_length_mismatch}")
    print()
    print("Top source extensions:")
    for ext, count in ext_counts.most_common(top_ext):
        pct = (count / total * 100) if total else 0.0
        print(f"  {ext:>8}  {count:>8}  {pct:>5.1f}%")
    print()
    print("Suspicious source-path globs:")
    for pattern in source_globs:
        print(f"  {pattern}: {glob_hits.get(pattern, 0)}")
    print()
    print("Suspicious text markers:")
    for marker in text_markers:
        print(f"  {marker}: {marker_hits.get(marker, 0)}")
    print(f"  numeric_dump_heuristic: {suspicious_numeric}")
    print(f"  suspicious_chunks_with_quality>=0.6: {suspicious_quality}")
    print()

    if suspicious_samples:
        print("Suspicious sample chunks:")
        for sample in suspicious_samples:
            print(f"  line {sample['line']}: {sample['source_path']}")
            print(f"    reasons: {sample['reasons']}")
            print(f"    preview: {sample['preview']}")
    else:
        print("Suspicious sample chunks: none captured")

    failing_globs = [
        pattern for pattern in require_zero_source_globs if glob_hits.get(pattern, 0) > 0
    ]
    if require_zero_source_globs:
        print()
        print("Gate checks:")
        if failing_globs:
            for pattern in require_zero_source_globs:
                count = glob_hits.get(pattern, 0)
                status = "FAIL" if count > 0 else "PASS"
                print(f"  {status}: {pattern}")
                print(f"    proof: matched_chunks={count}")
            print("RESULT: FAIL")
            return 2

        for pattern in require_zero_source_globs:
            print(f"  PASS: {pattern}")
            print("    proof: matched_chunks=0")
        print("RESULT: PASS")

    return 0


def main() -> int:
    """Parse CLI flags, run the export quality check, and return 0 (ok) or 2 (forbidden glob matched)."""
    parser = argparse.ArgumentParser(
        description="Quick trust check for a CorpusForge export before import/signoff."
    )
    parser.add_argument(
        "--export-dir",
        required=True,
        type=Path,
        help="Path to the export_YYYYMMDD_HHMM directory.",
    )
    parser.add_argument(
        "--source-glob",
        action="append",
        default=[],
        help="Extra case-insensitive source_path glob to count. Can be repeated.",
    )
    parser.add_argument(
        "--text-marker",
        action="append",
        default=[],
        help="Extra case-insensitive text marker to count. Can be repeated.",
    )
    parser.add_argument(
        "--require-zero-source-glob",
        action="append",
        default=[],
        help=(
            "Fail with exit code 2 if any chunk source_path matches this glob. "
            "Can be repeated."
        ),
    )
    parser.add_argument(
        "--top-ext",
        type=int,
        default=15,
        help="How many top source extensions to print.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=8,
        help="How many suspicious sample chunks to print.",
    )
    args = parser.parse_args()

    source_globs = DEFAULT_SOURCE_GLOBS + args.source_glob
    text_markers = DEFAULT_TEXT_MARKERS + args.text_marker
    return inspect_export(
        export_dir=args.export_dir,
        source_globs=source_globs,
        text_markers=text_markers,
        require_zero_source_globs=args.require_zero_source_glob,
        top_ext=args.top_ext,
        sample_limit=args.sample_limit,
    )


if __name__ == "__main__":
    sys.exit(main())
