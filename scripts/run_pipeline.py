"""
CorpusForge CLI entry point.

Usage:
  python scripts/run_pipeline.py --input test_file.txt
  python scripts/run_pipeline.py --input data/source/ --config config/config.yaml
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.schema import load_config
from src.pipeline import Pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="CorpusForge pipeline")
    parser.add_argument(
        "--input",
        required=True,
        help="Input file or directory to process.",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config YAML (default: config/config.yaml).",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    logging.basicConfig(
        level=getattr(logging, config.pipeline.log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    input_path = Path(args.input)
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = sorted(input_path.rglob("*"))
        files = [f for f in files if f.is_file() and f.suffix.lower() in {
            ".txt", ".md", ".log", ".csv", ".json", ".xml",
            ".yaml", ".yml", ".ini", ".cfg", ".conf",
        }]
    else:
        print(f"Error: {input_path} not found.", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("No files to process.", file=sys.stderr)
        sys.exit(1)

    print(f"CorpusForge: processing {len(files)} file(s)...")

    pipeline = Pipeline(config)
    stats = pipeline.run(files)

    print()
    print("=" * 50)
    print("  CorpusForge — Run Complete")
    print("=" * 50)
    print(f"  Files found:    {stats.files_found}")
    print(f"  Files parsed:   {stats.files_parsed}")
    print(f"  Files failed:   {stats.files_failed}")
    print(f"  Chunks created: {stats.chunks_created}")
    print(f"  Vectors created:{stats.vectors_created}")
    print(f"  Elapsed:        {stats.elapsed_seconds:.1f}s")
    if stats.errors:
        print(f"  Errors:         {len(stats.errors)}")
        for err in stats.errors[:5]:
            print(f"    - {err['file']}: {err['error']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
