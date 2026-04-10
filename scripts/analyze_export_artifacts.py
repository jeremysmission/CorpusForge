"""Analyze a Forge export package for corpus-adaptation work."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.export_artifact_analyzer import write_export_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze one Forge export package and write a corpus-adaptation summary JSON.")
    parser.add_argument("--export-dir", required=True, help="Export directory containing manifest.json, run_report.txt, skip_manifest.json, and chunks.jsonl.")
    parser.add_argument("--failure-artifact", required=True, help="Real failure list or log artifact to summarize alongside the export.")
    parser.add_argument("--sample-profile-json", default="", help="Optional sample-tree profile JSON path used as the baseline input.")
    parser.add_argument("--output-json", required=True, help="Path to write the derived summary JSON.")
    return parser.parse_args()


def main() -> int:
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
