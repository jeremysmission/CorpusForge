"""Write a JSON report describing the Forge -> V2 metadata contract surface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.export_metadata_contract import write_export_metadata_contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze one Forge export package and write a metadata-contract summary JSON."
    )
    parser.add_argument(
        "--export-dir",
        required=True,
        help="Export directory containing chunks.jsonl / vectors.npy / manifest.json.",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        help="Path to write the derived metadata-contract summary JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = write_export_metadata_contract(args.output_json, args.export_dir)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
