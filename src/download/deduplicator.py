"""
Deduplicator — detects and eliminates duplicate files before processing.

Two dedup strategies:
  1. _N suffix detection: Report.docx and Report_1.docx with same hash -> skip _N
  2. Content-hash dedup: any files with identical SHA-256 -> process only once

54% of the production corpus consists of _1 suffix duplicates (measured).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional

from src.download.hasher import Hasher

logger = logging.getLogger(__name__)

# Mtime tolerance for float comparison (2 seconds covers FAT32/NTFS precision)
_MTIME_TOLERANCE = 2.0

# Pattern matching _1, _2, _3 etc. at end of stem
_SUFFIX_RE = re.compile(r"^(.+?)_(\d+)$")


class Deduplicator:
    """Filters file lists to only new/changed files."""

    def __init__(self, hasher: Hasher):
        self.hasher = hasher
        self.skipped_unchanged = 0
        self.skipped_duplicate = 0
        self._pending_hashes: dict[str, str] = {}

    def filter_new_and_changed(
        self,
        files: list[Path],
        on_progress: Optional[Callable[[int, int, str, int], None]] = None,
    ) -> list[Path]:
        """
        Return only files that are new or changed since last run.

        Skips:
          - Files with unchanged content hash
          - _N suffix duplicates with identical content to the original

        Args:
            files: List of file paths to check.
            on_progress: Optional callback(scanned, total, current_file, duplicates)
                called periodically for GUI/CLI progress display.
        """
        work_list = []
        seen_hashes: dict[str, Path] = {}
        total = len(files)
        last_progress = time.time()

        for i, path in enumerate(files):
            if not path.exists() or not path.is_file():
                continue

            # Emit progress every 5 seconds
            now = time.time()
            if on_progress and (now - last_progress >= 5.0 or i == 0):
                on_progress(i, total, path.name, self.skipped_duplicate)
                last_progress = now

            state = self.hasher.get_state(path)

            if state:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                mtime_match = abs(state["mtime"] - stat.st_mtime) < _MTIME_TOLERANCE
                size_match = state["size"] == stat.st_size

                if mtime_match and size_match:
                    if state["status"] == "indexed":
                        self.skipped_unchanged += 1
                        continue
                    if state["status"] == "duplicate":
                        self.skipped_duplicate += 1
                        continue

            content_hash = self.hasher.hash_file(path)
            previous_hash = self.hasher.get_stored_hash(path)

            # Skip if unchanged since last run (hash matches despite mtime drift)
            if state and state["status"] == "indexed" and content_hash == previous_hash:
                self.skipped_unchanged += 1
                # Update mtime in DB to avoid re-hashing next time
                self.hasher.update_hash(path, content_hash, status="indexed")
                continue

            # Check for _N suffix duplicate (e.g. Report_1.docx, Report_2.docx)
            if self._is_suffix_duplicate(path, content_hash):
                self.skipped_duplicate += 1
                self.hasher.update_hash(path, content_hash, status="duplicate")
                logger.debug("Skipping suffix duplicate: %s", path.name)
                continue

            # Check for content-hash duplicate within this batch
            if content_hash in seen_hashes:
                self.skipped_duplicate += 1
                self.hasher.update_hash(path, content_hash, status="duplicate")
                logger.debug(
                    "Skipping content duplicate: %s (same as %s)",
                    path.name, seen_hashes[content_hash].name,
                )
                continue

            seen_hashes[content_hash] = path
            self._pending_hashes[self.hasher._normalize_path(path)] = content_hash
            work_list.append(path)

        # Final progress
        if on_progress:
            on_progress(total, total, "", self.skipped_duplicate)

        logger.info(
            "Dedup: %d files to process, %d unchanged, %d duplicates",
            len(work_list), self.skipped_unchanged, self.skipped_duplicate,
        )
        return work_list

    def mark_indexed(self, files: list[Path]) -> None:
        """Mark successfully processed files as indexed after the pipeline completes."""
        for path in files:
            norm = self.hasher._normalize_path(path)
            content_hash = self._pending_hashes.pop(norm, None)
            if content_hash is None:
                content_hash = self.hasher.hash_file(path)
            self.hasher.update_hash(path, content_hash, status="indexed")

    def _is_suffix_duplicate(self, path: Path, content_hash: str) -> bool:
        """Check if this file is a _N suffix copy of another file."""
        stem = path.stem
        m = _SUFFIX_RE.match(stem)
        if not m:
            return False

        original_stem = m.group(1)
        # Reconstruct original path with same parent and suffix
        original_path = path.parent / (original_stem + path.suffix)

        if not original_path.exists():
            return False

        original_hash = self.hasher.hash_file(original_path)
        return original_hash == content_hash
