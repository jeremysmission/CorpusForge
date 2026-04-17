"""
File hasher — SHA-256 content hashing with SQLite state tracking.

Plain-English role
------------------
Stage 1 of the pipeline. Every candidate file is fingerprinted with
SHA-256. The fingerprint plus mtime and size are stored in a small
SQLite database (``file_state.sqlite3``) so later stages can answer
quickly: have we already indexed this file? Is it a duplicate of
another file? Has it changed since last run?

The hasher is also reused by the dedup, skip, and delta stages, which
is why it lives in the ``download`` package alongside the syncer.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


class Hasher:
    """SHA-256 file hashing with a small SQLite table that remembers state across runs."""

    def __init__(self, state_db: str):
        """Open (or create) the file_state SQLite database."""
        self.db_path = Path(state_db)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the file_state table on first use."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS file_state (
                path       TEXT PRIMARY KEY,
                hash       TEXT NOT NULL,
                mtime      REAL NOT NULL,
                size       INTEGER NOT NULL,
                status     TEXT DEFAULT 'indexed'
            );
        """)
        self._conn.commit()

    @staticmethod
    def _normalize_path(file_path: Path | str) -> str:
        """Return path with forward slashes for consistent DB keys across OSes."""
        return str(file_path).replace("\\", "/")

    def hash_file(self, file_path: Path) -> str:
        """Compute SHA-256 hash of file contents."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()

    def get_stored_hash(self, file_path: Path) -> str | None:
        """Get previously stored hash for a file path."""
        norm = self._normalize_path(file_path)
        row = self._conn.execute(
            "SELECT hash FROM file_state WHERE path = ?", (norm,)
        ).fetchone()
        return row["hash"] if row else None

    def get_state(self, file_path: Path | str) -> sqlite3.Row | None:
        """Get the stored row for a file path."""
        norm = self._normalize_path(file_path)
        return self._conn.execute(
            "SELECT path, hash, mtime, size, status FROM file_state WHERE path = ?",
            (norm,),
        ).fetchone()

    def update_hash(self, file_path: Path, content_hash: str, status: str = "indexed") -> None:
        """Store or update hash for a file."""
        norm = self._normalize_path(file_path)
        stat = file_path.stat()
        self._conn.execute(
            """INSERT OR REPLACE INTO file_state (path, hash, mtime, size, status)
               VALUES (?, ?, ?, ?, ?)""",
            (norm, content_hash, stat.st_mtime, stat.st_size, status),
        )
        self._conn.commit()

    def get_all_tracked_paths(self) -> list[str]:
        """Return all tracked file paths."""
        rows = self._conn.execute("SELECT path FROM file_state").fetchall()
        return [r["path"] for r in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
