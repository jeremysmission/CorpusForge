"""
Bulk file syncer — atomic copy with SHA-256 verification and resume.

Designed for 700GB+ production transfers across network paths or USB.
Ported from V1 bulk_transfer_v2.py patterns:
  - Atomic: write to .tmp, verify hash, rename to final
  - Resume: skip files already copied with matching hash
  - Progress: callback every N files for GUI/CLI display
  - Thread-safe: parallel copy workers with shared state
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class TransferStats:
    """Tracks bulk transfer progress."""

    total_files: int = 0
    files_copied: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    bytes_transferred: int = 0
    bytes_total: int = 0
    current_file: str = ""
    elapsed_seconds: float = 0.0
    errors: list[dict] = field(default_factory=list)

    @property
    def files_done(self) -> int:
        return self.files_copied + self.files_skipped + self.files_failed

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "files_copied": self.files_copied,
            "files_skipped": self.files_skipped,
            "files_failed": self.files_failed,
            "bytes_transferred": self.bytes_transferred,
            "bytes_total": self.bytes_total,
            "current_file": self.current_file,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error_count": len(self.errors),
        }


# 128 KB read chunks for hashing/copying
_BUF_SIZE = 131072


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(_BUF_SIZE)
            if not buf:
                break
            sha.update(buf)
    return sha.hexdigest()


def _atomic_copy(src: Path, dest: Path) -> int:
    """Copy file atomically: write to .tmp then rename. Returns bytes copied."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        bytes_copied = 0
        with open(src, "rb") as fin, open(tmp, "wb") as fout:
            while True:
                buf = fin.read(_BUF_SIZE)
                if not buf:
                    break
                fout.write(buf)
                bytes_copied += len(buf)
        # Atomic rename (same filesystem) or fallback
        try:
            tmp.replace(dest)
        except OSError:
            shutil.move(str(tmp), str(dest))
        return bytes_copied
    except Exception:
        # Clean up partial .tmp on failure
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class BulkSyncer:
    """
    Bulk file syncer with SHA-256 verification and resume support.

    Args:
        source_dir: Root directory to copy from.
        dest_dir: Root staging directory to copy into.
        workers: Number of parallel copy threads.
        on_progress: Callback(TransferStats) called periodically.
        should_stop: Callable returning True to abort transfer.
    """

    def __init__(
        self,
        source_dir: Path | str,
        dest_dir: Path | str,
        workers: int = 4,
        on_progress: Optional[Callable[[TransferStats], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ):
        self.source_dir = Path(source_dir).resolve()
        self.dest_dir = Path(dest_dir).resolve()
        self.workers = max(1, workers)
        self._on_progress = on_progress
        self._should_stop = should_stop or (lambda: False)
        self._hash_cache: dict[str, str] = {}

    def discover_files(self) -> list[Path]:
        """Discover all files under source_dir recursively."""
        if not self.source_dir.exists():
            raise FileNotFoundError(f"Source not found: {self.source_dir}")
        return sorted(f for f in self.source_dir.rglob("*") if f.is_file())

    def _dest_path(self, src_file: Path) -> Path:
        """Map a source file to its destination path, preserving directory structure."""
        rel = src_file.relative_to(self.source_dir)
        return self.dest_dir / rel

    def _is_already_synced(self, src_file: Path, dest_file: Path) -> bool:
        """Check if dest already has an identical copy (by SHA-256)."""
        if not dest_file.exists():
            return False
        try:
            # Quick size check first
            if src_file.stat().st_size != dest_file.stat().st_size:
                return False
            src_hash = self._hash_file(src_file)
            dest_hash = self._hash_file(dest_file)
            return src_hash == dest_hash
        except OSError:
            return False

    def _hash_file(self, path: Path) -> str:
        """Hash with caching for repeated lookups."""
        key = str(path)
        if key not in self._hash_cache:
            self._hash_cache[key] = _sha256_file(path)
        return self._hash_cache[key]

    def _copy_one(self, src_file: Path) -> tuple[str, int, str]:
        """
        Copy a single file. Returns (status, bytes, error_msg).
        Status: "copied", "skipped", "failed"
        """
        dest_file = self._dest_path(src_file)

        # Resume check: skip if already synced
        if self._is_already_synced(src_file, dest_file):
            return "skipped", 0, ""

        try:
            nbytes = _atomic_copy(src_file, dest_file)
            # Verify hash after copy
            src_hash = self._hash_file(src_file)
            # Clear dest cache since we just wrote it
            dest_key = str(dest_file)
            self._hash_cache.pop(dest_key, None)
            dest_hash = _sha256_file(dest_file)

            if src_hash != dest_hash:
                dest_file.unlink(missing_ok=True)
                return "failed", 0, f"Hash mismatch: src={src_hash[:12]} dest={dest_hash[:12]}"

            return "copied", nbytes, ""
        except Exception as exc:
            return "failed", 0, str(exc)

    def run(self) -> TransferStats:
        """Execute the bulk transfer. Returns final stats."""
        stats = TransferStats()
        start_time = time.time()

        logger.info("Discovering files in %s...", self.source_dir)
        all_files = self.discover_files()
        stats.total_files = len(all_files)
        stats.bytes_total = sum(f.stat().st_size for f in all_files)

        logger.info(
            "Transfer: %d files, %.1f GB from %s -> %s",
            stats.total_files,
            stats.bytes_total / (1024**3),
            self.source_dir,
            self.dest_dir,
        )

        self._emit_progress(stats, start_time)

        if self.workers > 1 and len(all_files) > 1:
            self._run_parallel(all_files, stats, start_time)
        else:
            self._run_sequential(all_files, stats, start_time)

        stats.elapsed_seconds = time.time() - start_time
        logger.info(
            "Transfer complete: %d copied, %d skipped, %d failed in %.1fs",
            stats.files_copied, stats.files_skipped, stats.files_failed,
            stats.elapsed_seconds,
        )
        return stats

    def _run_sequential(
        self, files: list[Path], stats: TransferStats, start_time: float
    ) -> None:
        last_progress = time.time()
        for src_file in files:
            if self._should_stop():
                logger.warning("Transfer aborted by user.")
                break
            stats.current_file = src_file.name
            status, nbytes, err = self._copy_one(src_file)
            self._apply_result(stats, src_file, status, nbytes, err)
            # Progress every 2 seconds
            now = time.time()
            if now - last_progress >= 2.0:
                stats.elapsed_seconds = now - start_time
                self._emit_progress(stats, start_time)
                last_progress = now

        stats.elapsed_seconds = time.time() - start_time
        self._emit_progress(stats, start_time)

    def _run_parallel(
        self, files: list[Path], stats: TransferStats, start_time: float
    ) -> None:
        last_progress = time.time()
        with ThreadPoolExecutor(
            max_workers=self.workers, thread_name_prefix="sync"
        ) as pool:
            futures = {}
            for src_file in files:
                if self._should_stop():
                    break
                fut = pool.submit(self._copy_one, src_file)
                futures[fut] = src_file

            for fut in as_completed(futures):
                if self._should_stop():
                    break
                src_file = futures[fut]
                stats.current_file = src_file.name
                try:
                    status, nbytes, err = fut.result(timeout=300)
                except Exception as exc:
                    status, nbytes, err = "failed", 0, str(exc)
                self._apply_result(stats, src_file, status, nbytes, err)
                # Progress every 2 seconds
                now = time.time()
                if now - last_progress >= 2.0:
                    stats.elapsed_seconds = now - start_time
                    self._emit_progress(stats, start_time)
                    last_progress = now

        stats.elapsed_seconds = time.time() - start_time
        self._emit_progress(stats, start_time)

    def _apply_result(
        self,
        stats: TransferStats,
        src_file: Path,
        status: str,
        nbytes: int,
        err: str,
    ) -> None:
        if status == "copied":
            stats.files_copied += 1
            stats.bytes_transferred += nbytes
        elif status == "skipped":
            stats.files_skipped += 1
        else:
            stats.files_failed += 1
            stats.errors.append({"file": str(src_file), "error": err})
            logger.error("Transfer failed: %s: %s", src_file.name, err)

    def _emit_progress(self, stats: TransferStats, start_time: float) -> None:
        if self._on_progress:
            try:
                self._on_progress(stats)
            except Exception:
                pass
