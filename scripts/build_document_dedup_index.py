"""
Focused document dedup index builder for PDF/DOC/DOCX source trees.

What it does for the operator:
  Scans a folder for PDFs / DOCs / DOCXs that look like the same document
  in different wrappers (e.g., file.doc, file.docx, file.pdf). Parses each
  candidate, normalizes the text, and picks ONE canonical file per "family".
  All the others are flagged as duplicates.

  Outputs a canonical_files.txt list -- this is the file you feed into
  run_pipeline.py via --input-list so the ingest only processes the ONE
  best version of each document.

When to run it:
  - BEFORE a big pipeline run, when the source tree has known format
    duplicates (common for legacy corpora with .doc/.docx/.pdf copies)
  - To estimate duplicate reduction before committing to a full ingest

Inputs:
  --input                  Source file or directory to scan.
  --config                 Config YAML (default config/config.yaml).
  --extensions             Comma-separated list (default ".pdf,.doc,.docx").
  --similarity-threshold   How alike two docs must be to be called duplicates
                           (default 0.9 containment).
  --min-chars              Minimum normalized text size before a match counts.
  --workers                Parser threads for same-stem candidate groups.
  --output-dir             Where to write the dedup artifacts (auto-timestamped
                           folder under data/dedup/ by default).

Outputs (all under the output directory):
  document_dedup.sqlite3   Searchable SQLite index of every file's decision.
  canonical_files.txt      One path per line -- feed to run_pipeline.py.
  duplicate_files.jsonl    Duplicates with reason + similarity to canonical.
  dedup_report.json        Summary counts and parameters used.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.schema import load_config
from src.dedup.document_dedup import (
    run_document_dedup,
    write_index,
)
from src.parse.dispatcher import ParseDispatcher


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    """Read and validate CLI flags for the dedup index build."""
    parser = argparse.ArgumentParser(description="Build a cross-format document dedup index.")
    parser.add_argument("--input", required=True, help="Source file or directory.")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config YAML (default: config/config.yaml).",
    )
    parser.add_argument(
        "--extensions",
        default=".pdf,.doc,.docx",
        help="Comma-separated extensions to consider (default: .pdf,.doc,.docx).",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.9,
        help="Containment threshold for same-stem near-duplicates (default: 0.9).",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=200,
        help="Minimum normalized chars before duplicate matching is allowed.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parser workers for same-stem candidate groups (default: 4).",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory. Defaults under data/dedup with timestamp.",
    )
    return parser.parse_args()


def main() -> None:
    """Scan, parse, classify, and emit the dedup index + canonical file list."""
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = load_config(config_path)

    logging.basicConfig(
        level=getattr(logging, config.pipeline.log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    input_path = Path(args.input).resolve()
    extensions = {
        ext if ext.startswith(".") else f".{ext}"
        for ext in (item.strip().lower() for item in args.extensions.split(","))
        if ext
    }
    from src.dedup.document_dedup import discover_files
    files = discover_files(input_path, extensions)
    if not files:
        print("No matching files found.", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        (Path(args.output_dir) if Path(args.output_dir).is_absolute() else PROJECT_ROOT / args.output_dir).resolve()
        if args.output_dir
        else (PROJECT_ROOT / "data/dedup" / f"document_dedup_{timestamp}").resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    dispatcher = ParseDispatcher(
        timeout_seconds=config.parse.timeout_seconds,
        max_chars=config.parse.max_chars_per_file,
    )
    print(f"Document dedup: scanning {len(files):,} file(s)")
    print(f"  Relevant extensions: {', '.join(sorted(extensions))}")
    print()

    def on_group(**progress) -> None:
        print(
            f"[{progress['group_index']}/{progress['total_groups']}] "
            f"{progress['stem_key'] or '<unknown>'} ({progress['group_size']} files)"
        )

    decisions, stats = run_document_dedup(
        input_path=input_path,
        dispatcher=dispatcher,
        extensions=extensions,
        similarity_threshold=args.similarity_threshold,
        min_chars=args.min_chars,
        workers=args.workers,
        on_group=on_group,
    )

    db_path = output_dir / "document_dedup.sqlite3"
    canonical_list_path = output_dir / "canonical_files.txt"
    duplicate_jsonl_path = output_dir / "duplicate_files.jsonl"
    report_path = output_dir / "dedup_report.json"

    write_index(
        decisions,
        db_path=db_path,
        canonical_list_path=canonical_list_path,
        duplicate_jsonl_path=duplicate_jsonl_path,
        report_path=report_path,
        source_root=input_path,
        extensions=sorted(extensions),
        similarity_threshold=args.similarity_threshold,
        min_chars=args.min_chars,
    )

    print()
    print("=" * 60)
    print("  Document Dedup Index Complete")
    print("=" * 60)
    print(f"  Files seen:        {stats.files_seen:,}")
    print(f"  Candidate groups:  {stats.candidate_groups:,}")
    print(f"  Singleton skips:   {stats.singleton_files:,}")
    print(f"  Canonical files:   {stats.canonical_files:,}")
    print(f"  Duplicate files:   {stats.duplicate_files:,}")
    print(f"  Reduction:         {(stats.duplicate_files / max(1, stats.files_seen)) * 100.0:.2f}%")
    print(f"  SQLite index:      {db_path}")
    print(f"  Canonical list:    {canonical_list_path}")
    print(f"  Duplicate report:  {duplicate_jsonl_path}")
    print(f"  Summary report:    {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
