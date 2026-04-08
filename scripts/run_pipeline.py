"""
CorpusForge CLI entry point — headless-safe for overnight/scheduled runs.

Usage:
  python scripts/run_pipeline.py --input data/source/
  python scripts/run_pipeline.py --input data/source/ --config config/config.yaml
  python scripts/run_pipeline.py --input-list canonical_files.txt --log-file logs/run.log

Exit codes:
  0 = success (chunks produced)
  1 = error (no files, config error, pipeline crash)
  2 = partial success (some files failed)
"""

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import load_config
from src.gpu_selector import apply_gpu_selection
from src.parse.dispatcher import get_supported_extensions
from src.pipeline import Pipeline
from src.skip.skip_manager import load_deferred_extension_map


def _discover_candidates(files: list[Path], supported: set[str], deferred: dict[str, str]) -> tuple[list[Path], Counter, Counter]:
    candidates: list[Path] = []
    deferred_counts: Counter = Counter()
    unsupported_counts: Counter = Counter()

    for file_path in files:
        ext = file_path.suffix.lower()
        if ext in deferred:
            candidates.append(file_path)
            deferred_counts[ext or "[no extension]"] += 1
        elif ext in supported:
            candidates.append(file_path)
        else:
            unsupported_counts[ext or "[no extension]"] += 1

    return candidates, deferred_counts, unsupported_counts


def _format_counts(label: str, counts: Counter, deferred: dict[str, str] | None = None) -> list[str]:
    if not counts:
        return []

    lines = [f"{label}:"]
    for ext, count in counts.most_common(8):
        if deferred and ext in deferred:
            lines.append(f"  - {ext}: {count} ({deferred[ext]})")
        else:
            lines.append(f"  - {ext}: {count}")
    return lines


def _load_input_list(input_list_path: Path) -> tuple[list[Path], Counter, int]:
    listed_files: list[Path] = []
    missing_counts: Counter = Counter()
    duplicate_entries = 0
    seen_paths: set[str] = set()

    for raw_line in input_list_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        path = Path(line).expanduser()
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            resolved = path

        key = str(resolved).lower()
        if key in seen_paths:
            duplicate_entries += 1
            continue
        seen_paths.add(key)

        if resolved.is_file():
            listed_files.append(resolved)
        else:
            missing_counts[resolved.suffix.lower() or "[no extension]"] += 1

    return listed_files, missing_counts, duplicate_entries


def main() -> int:
    parser = argparse.ArgumentParser(description="CorpusForge pipeline (headless-safe)")
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
    parser.add_argument(
        "--strict-input-list",
        action="store_true",
        help="Fail if --input-list contains missing file paths.",
    )
    parser.add_argument(
        "--log-file",
        help="Write logs to file in addition to stdout (for overnight runs).",
    )
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        help="Process all files, not just new/changed (ignores dedup state).",
    )
    parser.add_argument(
        "--strip-enrichment",
        action="store_true",
        help="Export raw text only — strip enrichment preambles from chunks.jsonl.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = load_config(config_path)

    # Logging setup — stdout + optional file
    log_level = getattr(logging, config.pipeline.log_level, logging.INFO)
    handlers = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(str(log_path), encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    logger = logging.getLogger("run_pipeline")

    # GPU selection before any CUDA operations
    gpu_idx = apply_gpu_selection()
    logger.info("GPU %d selected for compute.", gpu_idx)

    if args.full_reindex:
        config.pipeline.full_reindex = True
    if args.strip_enrichment:
        config.enrich.enabled = False
        logger.info("--strip-enrichment: enrichment disabled, raw text only in export.")

    supported = get_supported_extensions(config.paths.skip_list)
    deferred = load_deferred_extension_map(config.paths.skip_list)
    deferred.update({ext: "Deferred by config for this run" for ext in config.parse.defer_extensions})
    if args.input_list:
        input_list_path = Path(args.input_list)
        if not input_list_path.is_file():
            print(f"Error: {input_list_path} not found.", file=sys.stderr)
            sys.exit(1)
        listed_files, missing_counts, duplicate_entries = _load_input_list(input_list_path)
        files, deferred_counts, unsupported_counts = _discover_candidates(listed_files, supported, deferred)
    else:
        missing_counts = Counter()
        duplicate_entries = 0
        input_path = Path(args.input)
        if input_path.is_file():
            discovered = [input_path]
        elif input_path.is_dir():
            discovered = sorted(f for f in input_path.rglob("*") if f.is_file())
        else:
            print(f"Error: {input_path} not found.", file=sys.stderr)
            sys.exit(1)
        files, deferred_counts, unsupported_counts = _discover_candidates(discovered, supported, deferred)

    if not files:
        print("No files to process.", file=sys.stderr)
        if args.input_list and missing_counts:
            for line in _format_counts("Missing paths from input list", missing_counts):
                print(line, file=sys.stderr)
        for line in _format_counts("Unsupported extensions skipped before parse", unsupported_counts):
            print(line, file=sys.stderr)
        sys.exit(1)

    print(f"CorpusForge: processing {len(files)} file(s)...")
    if args.input_list and duplicate_entries:
        print(f"Duplicate entries removed from input list: {duplicate_entries}")
    if args.input_list and missing_counts:
        for line in _format_counts("Missing paths in input list", missing_counts):
            print(line)
        if args.strict_input_list:
            print("Strict input-list mode enabled; aborting because paths are missing.", file=sys.stderr)
            sys.exit(1)
    if deferred_counts:
        for line in _format_counts("Deferred formats that will be hashed and recorded in the skip manifest", deferred_counts, deferred):
            print(line)
    if unsupported_counts:
        for line in _format_counts("Unsupported extensions excluded from this run", unsupported_counts):
            print(line)

    try:
        pipeline = Pipeline(config)
    except RuntimeError as e:
        logger.error("Pipeline init failed: %s", e)
        print(f"FATAL: {e}", file=sys.stderr)
        return 1

    stats = pipeline.run(files)

    summary = (
        f"\n{'=' * 50}\n"
        f"  CorpusForge -- Run Complete\n"
        f"{'=' * 50}\n"
        f"  Files found:     {stats.files_found}\n"
        f"  Files parsed:    {stats.files_parsed}\n"
        f"  Files failed:    {stats.files_failed}\n"
        f"  Files skipped:   {stats.files_skipped}\n"
        f"  Chunks created:  {stats.chunks_created}\n"
        f"  Chunks enriched: {stats.chunks_enriched}\n"
        f"  Vectors created: {stats.vectors_created}\n"
        f"  Entities found:  {stats.entities_extracted}\n"
        f"  Elapsed:         {stats.elapsed_seconds:.1f}s\n"
    )
    if stats.errors:
        summary += f"  Errors:          {len(stats.errors)}\n"
        for err in stats.errors[:10]:
            summary += f"    - {err['file']}: {err['error']}\n"
    summary += f"{'=' * 50}"
    print(summary)
    logger.info(summary)

    # Exit codes: 0=success, 1=total failure, 2=partial
    if stats.files_parsed == 0:
        return 1
    if stats.files_failed > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
