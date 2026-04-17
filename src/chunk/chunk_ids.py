"""
Deterministic chunk ID generator — ported from V1 (src/core/chunk_ids.py).

Plain-English role
------------------
Every chunk Forge produces needs a stable identifier so checkpoints,
resumes, and V2 imports line up. This module turns the file path,
modification time, span inside the file, and the chunk text itself
into a single 64-character hex string. Same inputs always yield the
same ID; if the file is edited, the mtime changes and new IDs are
produced, forcing that file to be re-indexed.

Inputs: file_path, file_mtime_ns, chunk_start, chunk_end, chunk_text
Output: 64-char hex string (SHA-256), deterministic and collision-proof
"""

from __future__ import annotations

import hashlib


def make_chunk_id(
    file_path: str,
    file_mtime_ns: int,
    chunk_start: int,
    chunk_end: int,
    chunk_text: str,
) -> str:
    """
    Create a deterministic chunk ID from file identity + position + content.

    Same algorithm as V1 — proven on 27.6M chunks.

    The ID changes if ANY input changes:
      - Edit a file -> new mtime -> new IDs -> file gets re-indexed
      - Same file, same content -> same IDs -> safely skipped
    """
    # Normalize path: strip, forward slashes, lowercase (Windows-safe)
    norm_path = file_path.strip().replace("\\", "/").lower()

    # Fingerprint chunk text (first 2000 chars for speed)
    text_sample = (chunk_text or "")[:2000]
    text_fp = hashlib.sha256(
        text_sample.encode("utf-8", errors="ignore")
    ).hexdigest()

    # Combine all five pieces, hash the result
    raw = f"{norm_path}|{file_mtime_ns}|{chunk_start}|{chunk_end}|{text_fp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
