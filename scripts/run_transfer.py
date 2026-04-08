"""
CorpusForge CLI bulk transfer — atomic copy with SHA-256 verification.

Usage:
  python scripts/run_transfer.py --source "D:\\production" --dest "data/staging"
  python scripts/run_transfer.py --source "\\\\server\\share" --dest "data/staging" --workers 8

Exit codes:
  0 = success (all files copied or skipped)
  1 = error (source not found, config error)
  2 = partial (some files failed)
"""

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.download.syncer import BulkSyncer, TransferStats


def _format_bytes(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _format_elapsed(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


_last_log_time = 0.0


def _progress_callback(stats: TransferStats) -> None:
    """Print progress line to stdout every 2 seconds minimum."""
    global _last_log_time
    now = time.time()
    if now - _last_log_time < 2.0:
        return
    _last_log_time = now

    done = stats.files_done
    total = stats.total_files
    pct = (done / total * 100) if total > 0 else 0

    eta = "--"
    if stats.elapsed_seconds > 0 and done > 0:
        rate = done / stats.elapsed_seconds
        remaining = total - done
        if rate > 0:
            eta = _format_elapsed(remaining / rate)

    speed = ""
    if stats.elapsed_seconds > 0:
        mbps = stats.bytes_transferred / stats.elapsed_seconds / (1024**2)
        speed = f"{mbps:.1f} MB/s"

    print(
        f"\r  [{pct:5.1f}%] {done}/{total} files | "
        f"{_format_bytes(stats.bytes_transferred)}/{_format_bytes(stats.bytes_total)} | "
        f"{speed} | ETA {eta} | {stats.current_file[:40]}",
        end="", flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="CorpusForge bulk file transfer")
    parser.add_argument("--source", required=True, help="Source directory")
    parser.add_argument("--dest", required=True, help="Destination staging directory")
    parser.add_argument("--workers", type=int, default=4, help="Parallel copy threads (default: 4)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    source = Path(args.source).resolve()
    dest = Path(args.dest).resolve()

    if not source.exists():
        print(f"Error: source not found: {source}", file=sys.stderr)
        return 1

    print(f"CorpusForge Transfer: {source} -> {dest}")
    print(f"Workers: {args.workers}")
    print()

    syncer = BulkSyncer(
        source_dir=source,
        dest_dir=dest,
        workers=args.workers,
        on_progress=_progress_callback,
    )

    stats = syncer.run()

    print()  # newline after \r progress
    print()
    print(f"{'=' * 50}")
    print(f"  Transfer Complete")
    print(f"{'=' * 50}")
    print(f"  Files copied:  {stats.files_copied}")
    print(f"  Files skipped: {stats.files_skipped} (already synced)")
    print(f"  Files failed:  {stats.files_failed}")
    print(f"  Transferred:   {_format_bytes(stats.bytes_transferred)}")
    print(f"  Elapsed:       {_format_elapsed(stats.elapsed_seconds)}")
    if stats.errors:
        print(f"  Errors ({len(stats.errors)}):")
        for err in stats.errors[:10]:
            print(f"    - {err['file']}: {err['error']}")
    print(f"{'=' * 50}")

    if stats.files_failed > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
