"""
Deduplicator — detects and eliminates duplicate files before processing.

Two dedup strategies:
  1. _1 suffix detection: Report.docx and Report_1.docx with same hash → skip _1
  2. Content-hash dedup: any files with identical SHA-256 → process only once

54% of the production corpus consists of _1 suffix duplicates (measured).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.download.hasher import Hasher

logger = logging.getLogger(__name__)


class Deduplicator:
    """Filters file lists to only new/changed files."""

    def __init__(self, hasher: Hasher):
        self.hasher = hasher
        self.skipped_unchanged = 0
        self.skipped_duplicate = 0

    def filter_new_and_changed(self, files: list[Path]) -> list[Path]:
        """
        Return only files that are new or changed since last run.

        Skips:
          - Files with unchanged content hash
          - _1 suffix duplicates with identical content to the original
        """
        work_list = []
        seen_hashes: dict[str, Path] = {}

        for path in files:
            if not path.exists() or not path.is_file():
                continue

            content_hash = self.hasher.hash_file(path)
            previous_hash = self.hasher.get_stored_hash(path)

            # Skip if unchanged since last run
            if content_hash == previous_hash:
                self.skipped_unchanged += 1
                continue

            # Check for _1 suffix duplicate
            if self._is_suffix_duplicate(path, content_hash):
                self.skipped_duplicate += 1
                logger.debug("Skipping _1 duplicate: %s", path.name)
                continue

            # Check for content-hash duplicate within this batch
            if content_hash in seen_hashes:
                self.skipped_duplicate += 1
                logger.debug(
                    "Skipping content duplicate: %s (same as %s)",
                    path.name, seen_hashes[content_hash].name,
                )
                continue

            seen_hashes[content_hash] = path
            self.hasher.update_hash(path, content_hash)
            work_list.append(path)

        logger.info(
            "Dedup: %d files to process, %d unchanged, %d duplicates",
            len(work_list), self.skipped_unchanged, self.skipped_duplicate,
        )
        return work_list

    def _is_suffix_duplicate(self, path: Path, content_hash: str) -> bool:
        """Check if this file is a _1 suffix copy of another file."""
        stem = path.stem
        if not stem.endswith("_1"):
            return False

        original_stem = stem[:-2]
        original_path = path.with_stem(original_stem)

        if not original_path.exists():
            return False

        original_hash = self.hasher.hash_file(original_path)
        return original_hash == content_hash
