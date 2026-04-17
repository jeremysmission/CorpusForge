"""
Profile a source tree to guide parser, skip/defer, and retrieval tuning.

What it does for the operator:
  Walks a source folder and gathers metadata (no parsing, no GPU, no
  hashing of file contents). Produces a Markdown report (printed to the
  terminal) and optional JSON summarizing:
    - Extension distribution (what formats dominate the corpus?)
    - Size distribution (how big are the files?)
    - Suspected duplicate folders (identical recursive signatures)
    - Other heuristics useful for planning

  Use it BEFORE deciding what to skip/defer, how many workers to run, and
  how much disk / time a full ingest will need.

When to run it:
  - First look at a new corpus
  - When planning skip / defer rules in config.yaml
  - To size overnight ingests before running them

Inputs:
  --root                       Root directory to profile (required).
  --output-json                Optional JSON report path.
  --output-md                  Optional Markdown report path.
  --top-n                      How many top rows to include in summaries.
  --min-duplicate-dir-files    Minimum files before a folder is considered
                               for duplicate-folder grouping.
  --max-files                  Optional scan cap for proof runs.

Outputs: Markdown report to stdout, plus optional JSON and Markdown files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.corpus_profiler import build_markdown_report, profile_source_tree


def parse_args() -> argparse.Namespace:
    """Read and validate CLI flags for the corpus profile run."""
    parser = argparse.ArgumentParser(description="Profile a source tree with metadata-only heuristics.")
    parser.add_argument("--root", required=True, help="Root directory to profile.")
    parser.add_argument("--output-json", default="", help="Optional JSON report path.")
    parser.add_argument("--output-md", default="", help="Optional markdown report path.")
    parser.add_argument("--top-n", type=int, default=20, help="How many top rows to keep in summaries.")
    parser.add_argument(
        "--min-duplicate-dir-files",
        type=int,
        default=3,
        help="Minimum descendant files before recursive folder-signature grouping is considered.",
    )
    parser.add_argument("--max-files", type=int, default=None, help="Optional scan cap for proof runs.")
    return parser.parse_args()


def _resolve_output(path_text: str) -> Path:
    """Resolve an output path to absolute form (relative paths are anchored at the project root)."""
    path = Path(path_text)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def main() -> int:
    """Run the profiler, print the Markdown report, and (optionally) persist JSON/MD copies."""
    args = parse_args()
    report = profile_source_tree(
        args.root,
        top_n=args.top_n,
        min_duplicate_dir_files=args.min_duplicate_dir_files,
        max_files=args.max_files,
    )

    markdown = build_markdown_report(report, top_n=min(args.top_n, 12))
    print(markdown)

    if args.output_json:
        json_path = _resolve_output(args.output_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print(f"JSON report written to {json_path}")

    if args.output_md:
        md_path = _resolve_output(args.output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(md_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(markdown)
        print(f"Markdown report written to {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
