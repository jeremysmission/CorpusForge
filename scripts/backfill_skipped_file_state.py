"""
Backfill file-state entries for legacy deferred or unsupported files.

Purpose:
  Hash files that were historically discovered but may never have entered
  file_state tracking because they were skipped, deferred, or unsupported.

Safety:
  By default this script only backfills deferred and unsupported files.
  It does not mark parseable files as already indexed.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import load_config
from src.download.hasher import Hasher
from src.parse.dispatcher import get_supported_extensions
from src.skip.skip_manager import load_deferred_extension_map


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill file_state for deferred/unsupported files.")
    parser.add_argument("--input", required=True, help="Input file or directory to scan.")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config YAML (default: config/config.yaml).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max files to backfill. 0 means no limit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assess what would be backfilled without writing to file_state.",
    )
    return parser.parse_args()


def discover_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(f for f in input_path.rglob("*") if f.is_file())
    raise FileNotFoundError(input_path)


def classify_file(path: Path, supported: set[str], deferred: dict[str, str]) -> tuple[str | None, str]:
    ext = path.suffix.lower()
    if ext in deferred:
        return "deferred", deferred[ext]
    if ext in supported:
        return None, ""
    return "unsupported", "Unsupported extension backfilled for restart accounting"


def backfill_file_state(
    *,
    input_path: Path,
    config_path: Path,
    limit: int = 0,
    dry_run: bool = False,
) -> dict:
    config = load_config(config_path)
    files = discover_files(input_path)

    supported = get_supported_extensions()
    deferred = load_deferred_extension_map(config.paths.skip_list)
    deferred.update({ext: "Deferred by config for this run" for ext in config.parse.defer_extensions})

    hasher = Hasher(config.paths.state_db)
    scanned = 0
    hashed = 0
    unchanged = 0
    skipped_supported = 0
    by_status: Counter[str] = Counter()

    try:
        for file_path in files:
            scanned += 1
            if limit and hashed >= limit:
                break

            status, _reason = classify_file(file_path, supported, deferred)
            if status is None:
                skipped_supported += 1
                continue

            row = hasher.get_state(file_path)
            stat = file_path.stat()
            if row and row["mtime"] == stat.st_mtime and row["size"] == stat.st_size and row["status"] == status:
                unchanged += 1
                continue

            if dry_run:
                hashed += 1
                by_status[status] += 1
                continue

            content_hash = hasher.hash_file(file_path)
            hasher.update_hash(file_path, content_hash, status=status)
            hashed += 1
            by_status[status] += 1
    finally:
        hasher.close()

    return {
        "state_db": config.paths.state_db,
        "scanned": scanned,
        "parseable_skipped": skipped_supported,
        "backfilled": hashed,
        "already_current": unchanged,
        "by_status": dict(by_status),
        "mode": "DRY RUN" if dry_run else "WRITE",
    }


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / config_path).resolve()

    input_path = Path(args.input).resolve()
    summary = backfill_file_state(
        input_path=input_path,
        config_path=config_path,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print("=" * 56)
    print("  CorpusForge — Skipped File-State Backfill")
    print("=" * 56)
    print(f"  Mode:               {summary['mode']}")
    print(f"  Input:              {input_path}")
    print(f"  State DB:           {summary['state_db']}")
    print(f"  Files scanned:      {summary['scanned']}")
    print(f"  Parseable skipped:  {summary['parseable_skipped']}")
    print(f"  Backfilled:         {summary['backfilled']}")
    print(f"  Already current:    {summary['already_current']}")
    if summary["by_status"]:
        for status, count in sorted(summary["by_status"].items()):
            print(f"  {status.title():<18}{count}")
    print("=" * 56)


if __name__ == "__main__":
    main()
