"""
Write a JSON report describing the Forge -> V2 metadata contract surface.

What it does for the operator:
  Reads one Forge export folder and summarizes the "metadata contract" --
  the shape of the data that HybridRAG V2 will consume (chunk fields,
  vector dim, manifest keys, etc.). The JSON output is used to verify that
  a new export still matches the agreed-upon schema before V2 imports it.

When to run it:
  - Before handing an export folder to the V2 ingest step
  - When updating Forge and wanting to confirm the contract did not drift

Inputs:
  --export-dir    Export folder (with chunks.jsonl / vectors.npy / manifest.json).
  --output-json   Where to write the metadata-contract summary JSON.

Outputs: a single JSON summary file, and its path printed to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.export_metadata_contract import write_export_metadata_contract


def parse_args() -> argparse.Namespace:
    """Read and validate CLI flags for the metadata-contract report."""
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
    """Build and persist the metadata-contract summary JSON for a given export folder."""
    args = parse_args()
    output_path = write_export_metadata_contract(args.output_json, args.export_dir)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
