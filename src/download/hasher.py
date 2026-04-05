"""
File hasher — SHA-256 content hashing with SQLite state tracking.

Tracks file hashes across runs for incremental processing.
Unchanged files (same hash) are skipped on subsequent runs.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


class Hasher:
    """SHA-256 file hashing with SQLite-backed state tracking."""

    def __init__(self, state_db: str):
        self.db_path = Path(state_db)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
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
        norm = str(file_path).replace("\\", "/")
        row = self._conn.execute(
            "SELECT hash FROM file_state WHERE path = ?", (norm,)
        ).fetchone()
        return row["hash"] if row else None

    def update_hash(self, file_path: Path, content_hash: str) -> None:
        """Store or update hash for a file."""
        norm = str(file_path).replace("\\", "/")
        stat = file_path.stat()
        self._conn.execute(
            """INSERT OR REPLACE INTO file_state (path, hash, mtime, size, status)
               VALUES (?, ?, ?, ?, 'indexed')""",
            (norm, content_hash, stat.st_mtime, stat.st_size),
        )
        self._conn.commit()

    def get_all_tracked_paths(self) -> list[str]:
        """Return all tracked file paths."""
        rows = self._conn.execute("SELECT path FROM file_state").fetchall()
        return [r["path"] for r in rows]

    def close(self) -> None:
        self._conn.close()
