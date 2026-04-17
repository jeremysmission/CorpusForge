"""
Nightly delta tracker -- detects new or changed source files and persists
source-side resume state in SQLite.

Plain-English role
------------------
Pre-stage helper for scheduled nightly runs. Before the main pipeline
kicks off, this module walks an upstream source tree and decides which
files are new, changed, or can be skipped because the local mirror
already has an up-to-date copy.

The tracker intentionally reuses the Hasher schema and status contract:
  - `hashed` means a source file has been fingerprinted and admitted to the
    pending delta set, but the mirror step has not completed successfully.
  - `mirrored` means the file is already present in the local mirror and can
    be skipped on the next nightly scan unless size or mtime changes.

The output (the delta list) is then fed to the syncer, which copies
those files into the local mirror before the main pipeline starts.
"""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .hasher import Hasher

_MTIME_TOLERANCE = 2.0
_PROGRESS_INTERVAL_SECONDS = 1.0
_PROGRESS_INTERVAL_FILES = 250


@dataclass
class DeltaScanResult:
    """Summary of a nightly delta scan — what is new, changed, and what was dropped."""

    source_root: str
    total_files: int = 0
    delta_files: int = 0
    new_files: int = 0
    changed_files: int = 0
    resumed_hashed: int = 0
    unchanged_files: int = 0
    deleted_files: int = 0
    elapsed_seconds: float = 0.0
    stopped: bool = False
    canary_matches: list[str] = field(default_factory=list)
    delta_paths: list[str] = field(default_factory=list)
    deleted_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the scan summary as a plain dict for JSON reporting."""
        return {
            "source_root": self.source_root,
            "total_files": self.total_files,
            "delta_files": self.delta_files,
            "new_files": self.new_files,
            "changed_files": self.changed_files,
            "resumed_hashed": self.resumed_hashed,
            "unchanged_files": self.unchanged_files,
            "deleted_files": self.deleted_files,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "stopped": self.stopped,
            "canary_matches": list(self.canary_matches),
            "delta_paths": list(self.delta_paths),
            "deleted_paths": list(self.deleted_paths),
        }


class NightlyDeltaTracker:
    """Tracks source-side delta state for the nightly mirror lane."""

    def __init__(self, state_db: str):
        """Open the source-side transfer state database (its own SQLite file)."""
        self.hasher = Hasher(state_db)

    def close(self) -> None:
        """Close the underlying state database."""
        self.hasher.close()

    def mark_mirrored(self, file_path: Path | str) -> None:
        """Promote a source file from `hashed` to `mirrored` after transfer."""
        path = Path(file_path)
        state = self.hasher.get_state(path)
        content_hash = state["hash"] if state else self.hasher.hash_file(path)
        self.hasher.update_hash(path, content_hash, status="mirrored")

    def scan(
        self,
        source_root: Path | str,
        files: list[Path] | None = None,
        max_files: int | None = None,
        canary_globs: list[str] | None = None,
        on_progress: Optional[Callable[[int, int, str, int], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> DeltaScanResult:
        """Detect the current nightly delta from the source tree."""
        root = Path(source_root).resolve()
        if files is None:
            source_files = sorted(f for f in root.rglob("*") if f.is_file())
        else:
            source_files = sorted(Path(f).resolve() for f in files if Path(f).is_file())
        if max_files:
            source_files = source_files[:max_files]

        result = DeltaScanResult(source_root=str(root), total_files=len(source_files))
        normalized_root = self.hasher._normalize_path(root)
        current_paths: set[str] = set()
        globs = [pattern for pattern in (canary_globs or []) if pattern]
        start = time.time()
        last_progress = start
        last_progress_count = 0

        for index, file_path in enumerate(source_files, start=1):
            if should_stop and should_stop():
                result.stopped = True
                break

            current_paths.add(self.hasher._normalize_path(file_path))
            rel_display = str(file_path.relative_to(root))
            if self._matches_any_glob(file_path, globs):
                result.canary_matches.append(rel_display)

            now = time.time()
            if on_progress and (
                index == 1
                or (now - last_progress) >= _PROGRESS_INTERVAL_SECONDS
                or (index - last_progress_count) >= _PROGRESS_INTERVAL_FILES
            ):
                on_progress(index, result.total_files, file_path.name, result.delta_files)
                last_progress = now
                last_progress_count = index

            state = self.hasher.get_state(file_path)
            if state and self._state_matches_file(state, file_path):
                if state["status"] == "mirrored":
                    result.unchanged_files += 1
                    continue
                result.resumed_hashed += 1
                result.delta_files += 1
                result.delta_paths.append(str(file_path))
                continue

            content_hash = self.hasher.hash_file(file_path)
            self.hasher.update_hash(file_path, content_hash, status="hashed")
            if state is None:
                result.new_files += 1
            else:
                result.changed_files += 1
            result.delta_files += 1
            result.delta_paths.append(str(file_path))

        tracked_paths = self.hasher.get_all_tracked_paths()
        prefix = normalized_root.rstrip("/") + "/"
        result.deleted_paths = sorted(
            path for path in tracked_paths
            if path.startswith(prefix) and path not in current_paths
        )
        result.deleted_files = len(result.deleted_paths)
        result.elapsed_seconds = time.time() - start

        if on_progress:
            current = result.total_files if not result.stopped else min(len(current_paths), result.total_files)
            on_progress(current, result.total_files, "", result.delta_files)

        return result

    @staticmethod
    def _matches_any_glob(file_path: Path, patterns: list[str]) -> bool:
        """Return True if file name or path matches any of the given glob patterns."""
        if not patterns:
            return False
        name = file_path.name.lower()
        full = str(file_path).lower()
        for pattern in patterns:
            pat = pattern.lower()
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(full, pat):
                return True
        return False

    @staticmethod
    def _state_matches_file(state, file_path: Path) -> bool:
        """True if stored size/mtime still match the live file (fast unchanged check)."""
        stat = file_path.stat()
        size_match = state["size"] == stat.st_size
        mtime_match = abs(state["mtime"] - stat.st_mtime) < _MTIME_TOLERANCE
        return size_match and mtime_match
