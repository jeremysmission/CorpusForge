"""
Skip manager — determines which files to hash-only (not parse).

Loads skip_list.yaml at init. Every skipped file is still SHA-256 hashed
and recorded in the skip manifest for full corpus accounting.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

import yaml

from src.download.hasher import Hasher

logger = logging.getLogger(__name__)

# Magic-byte signatures for common encrypted/protected formats.
# Each entry: (offset, bytes_signature).
_ENCRYPTED_SIGNATURES: list[tuple[int, bytes]] = [
    # Encrypted Office (EncryptedPackage inside OLE2)
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),  # OLE2 header — checked + flag below
    # Encrypted PDF: starts with %PDF but contains /Encrypt
]

# Minimum bytes to read for magic-byte detection.
_MAGIC_READ_SIZE = 4096


class SkipManager:
    """
    Decides whether a file should be skipped (hashed but not parsed).

    Checks:
      1. Extension in deferred_formats list
      2. Zero-byte file
      3. Over size limit
      4. Temp file prefix or extension
      5. Encrypted file (magic-byte heuristic)

    All skipped files are recorded with their SHA-256 hash and reason.
    """

    def __init__(self, skip_list_path: str | Path, hasher: Hasher):
        self.hasher = hasher
        self._skipped: list[dict] = []
        self._reason_counts: dict[str, int] = defaultdict(int)

        path = Path(skip_list_path)
        if not path.exists():
            logger.warning("Skip list not found at %s — no skip rules loaded.", path)
            self._deferred_exts: dict[str, str] = {}
            self._conditions: dict = {}
            return

        with open(path, encoding="utf-8-sig") as f:
            raw = yaml.safe_load(f) or {}

        # Build extension -> reason map (lowercase, with leading dot)
        self._deferred_exts = {}
        for entry in raw.get("deferred_formats", []):
            ext = entry["ext"].lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            self._deferred_exts[ext] = entry.get("reason", "deferred format")

        self._conditions = raw.get("skip_conditions", {})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_skip(self, file_path: Path, file_size: int) -> tuple[bool, str]:
        """
        Check whether a file should be skipped.

        Returns (skip: bool, reason: str). If skip is False, reason is empty.
        """
        name = file_path.name
        ext = file_path.suffix.lower()

        # 1. Zero-byte
        if self._conditions.get("zero_byte") and file_size == 0:
            return True, "zero-byte file"

        # 2. Temp file prefix
        for prefix in self._conditions.get("temp_file_prefixes", []):
            if name.startswith(prefix):
                return True, f"temp file prefix '{prefix}'"

        # 3. Temp file extension
        for temp_ext in self._conditions.get("temp_file_extensions", []):
            if ext == temp_ext.lower():
                return True, f"temp file extension '{temp_ext}'"

        # 4. Over size limit
        over_mb = self._conditions.get("over_size_mb")
        if over_mb and file_size > over_mb * 1_048_576:
            return True, f"over size limit ({over_mb} MB)"

        # 5. Deferred format
        if ext in self._deferred_exts:
            return True, self._deferred_exts[ext]

        # 6. Encrypted detection
        if self._conditions.get("encrypted") and file_path.exists():
            if self._is_encrypted(file_path, ext):
                return True, "encrypted file detected"

        return False, ""

    def record_skip(self, file_path: Path, reason: str) -> None:
        """Hash the file and record it in the skip manifest."""
        content_hash = self.hasher.hash_file(file_path)
        entry = {
            "path": str(file_path),
            "sha256": content_hash,
            "size": file_path.stat().st_size,
            "reason": reason,
        }
        self._skipped.append(entry)
        self._reason_counts[reason] += 1
        logger.info("SKIP: %s — %s (sha256=%s)", file_path.name, reason, content_hash[:12])

    @property
    def skip_count(self) -> int:
        return len(self._skipped)

    def get_skip_manifest(self) -> dict:
        """Return the full skip report."""
        return {
            "total_skipped": len(self._skipped),
            "counts_by_reason": dict(self._reason_counts),
            "files": self._skipped,
        }

    def write_skip_manifest(self, output_dir: str | Path) -> Path:
        """Write skip_manifest.json alongside the export."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        manifest_path = out / "skip_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.get_skip_manifest(), f, indent=2, ensure_ascii=False)
        logger.info("Skip manifest written to %s (%d files)", manifest_path, len(self._skipped))
        return manifest_path

    def get_reason_summary(self) -> str:
        """Human-readable reason summary for pipeline output."""
        if not self._reason_counts:
            return "none"
        parts = [f"{v} {k}" for k, v in sorted(self._reason_counts.items(), key=lambda x: -x[1])]
        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _is_encrypted(file_path: Path, ext: str) -> bool:
        """Heuristic encrypted-file detection via magic bytes."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(_MAGIC_READ_SIZE)
        except OSError:
            return False

        if not header:
            return False

        # PDF with /Encrypt dictionary
        if ext == ".pdf" and header[:5] == b"%PDF-":
            if b"/Encrypt" in header:
                return True

        # OLE2 container (Office 97-2003) — check for EncryptedPackage
        if header[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            if b"EncryptedPackage" in header or b"Encrypted" in header:
                return True

        # ZIP-based Office (OOXML) — encrypted OOXML starts with OLE2, not PK
        # If a .docx/.xlsx/.pptx starts with OLE2 header, it's encrypted
        if ext in {".docx", ".xlsx", ".pptx"} and header[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            return True

        return False
