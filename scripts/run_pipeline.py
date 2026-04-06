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
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import load_config
from src.parse.dispatcher import get_supported_extensions
from src.pipeline import Pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="CorpusForge pipeline")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        help="Input file or directory to process.",
    )
    input_group.add_argument(
        "--input-list",
        help="Text file with one file path per line. Use canonical_files.txt from document dedup.",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config YAML (default: config/config.yaml).",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = load_config(config_path)

    logging.basicConfig(
        level=getattr(logging, config.pipeline.log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    supported = get_supported_extensions()
    if args.input_list:
        input_list_path = Path(args.input_list)
        if not input_list_path.is_file():
            print(f"Error: {input_list_path} not found.", file=sys.stderr)
            sys.exit(1)
        files = []
        for raw_line in input_list_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            path = Path(line)
            if path.is_file() and path.suffix.lower() in supported:
                files.append(path)
    else:
        input_path = Path(args.input)
        if input_path.is_file():
            files = [input_path]
        elif input_path.is_dir():
            files = sorted(input_path.rglob("*"))
            files = [f for f in files if f.is_file() and f.suffix.lower() in supported]
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
    print(f"  Chunks enriched:{stats.chunks_enriched}")
    print(f"  Vectors created:{stats.vectors_created}")
    print(f"  Elapsed:        {stats.elapsed_seconds:.1f}s")
    if stats.errors:
        print(f"  Errors:         {len(stats.errors)}")
        for err in stats.errors[:5]:
            print(f"    - {err['file']}: {err['error']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
