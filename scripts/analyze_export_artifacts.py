"""
Analyze a Forge export package for corpus-adaptation work.

What it does for the operator:
  Reads a finished export folder together with a "failure artifact"
  (a list or log of files that failed to parse) and writes a single JSON
  summary combining what's in the export with what went wrong. That JSON
  is the input to the corpus-adaptation workflow -- it tells engineers what
  parser/skip changes would improve a repeat ingest.

  Optionally takes a pre-ingest "sample profile" JSON (from
  profile_source_corpus.py) so the summary can compare what was SEEN in the
  sample to what ACTUALLY landed in the export.

When to run it:
  - After a pipeline run that had parse failures, to plan fixes
  - As part of the corpus-adaptation loop between runs

Inputs:
  --export-dir            Export directory (with manifest.json, run_report.txt,
                          skip_manifest.json, chunks.jsonl).
  --failure-artifact      Real failure list or log file to summarize.
  --sample-profile-json   Optional pre-ingest profile JSON for comparison.
  --output-json           Path to write the derived summary JSON.

Outputs: one JSON file at --output-json. Prints its path on exit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.export_artifact_analyzer import write_export_analysis


def parse_args() -> argparse.Namespace:
    """Read and validate CLI flags for the export analyzer."""
    parser = argparse.ArgumentParser(description="Analyze one Forge export package and write a corpus-adaptation summary JSON.")
    parser.add_argument("--export-dir", required=True, help="Export directory containing manifest.json, run_report.txt, skip_manifest.json, and chunks.jsonl.")
    parser.add_argument("--failure-artifact", required=True, help="Real failure list or log artifact to summarize alongside the export.")
    parser.add_argument("--sample-profile-json", default="", help="Optional sample-tree profile JSON path used as the baseline input.")
    parser.add_argument("--output-json", required=True, help="Path to write the derived summary JSON.")
    return parser.parse_args()


def main() -> int:
    """Run the export analyzer and print the path of the resulting JSON summary."""
    args = parse_args()
    output_path = write_export_analysis(
        args.output_json,
        args.export_dir,
        failure_artifact=args.failure_artifact,
        sample_profile_json=args.sample_profile_json or None,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
