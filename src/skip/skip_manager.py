"""
Skip manager — determines which files to hash-only (not parse).

Loads skip/defer rules from the active config file. Every skipped file is
still SHA-256 hashed and recorded in the skip manifest for full corpus
accounting.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

import yaml

from src.download.hasher import Hasher

logger = logging.getLogger(__name__)


def _compile_token_boundary(token: str) -> re.Pattern[str]:
    """Compile a case-insensitive, alnum-boundary-anchored regex for a token.

    The match fires only when the token sits on a non-alphanumeric boundary
    (start/end of the string or next to a separator like ``_`` ``-`` ``.``
    `` ``). This is what keeps ``unencrypted_notes.pdf`` from matching the
    ``encrypted`` token while still catching ``contract_encrypted.pdf``,
    ``Report.ENCRYPTED.v2.pdf``, and ``Budget_PASSWORD-PROTECTED.pdf``.
    Multi-word tokens like ``password-protected`` are treated as one unit —
    the boundary check is applied to the whole token, not the hyphen inside.
    """
    return re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )

# Magic-byte signatures for common encrypted/protected formats.
# Each entry: (offset, bytes_signature).
_ENCRYPTED_SIGNATURES: list[tuple[int, bytes]] = [
    # Encrypted Office (EncryptedPackage inside OLE2)
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),  # OLE2 header — checked + flag below
    # Encrypted PDF: starts with %PDF but contains /Encrypt
]

# Minimum bytes to read for magic-byte detection.
_MAGIC_READ_SIZE = 4096


def _load_format_list(raw: dict, key: str, default_reason: str) -> dict[str, str]:
    """Load an extension -> reason map from a skip_list.yaml section."""
    result: dict[str, str] = {}
    for entry in raw.get(key, []):
        ext = entry["ext"].lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        result[ext] = entry.get("reason", default_reason)
    return result


def _load_skip_source(path: str | Path) -> dict:
    """Load skip/defer config from either config.yaml or a legacy skip_list.yaml."""
    source_path = Path(path)
    if not source_path.exists():
        return {}

    with open(source_path, encoding="utf-8-sig") as f:
        raw = yaml.safe_load(f) or {}

    skip_section = raw.get("skip")
    if isinstance(skip_section, dict):
        return skip_section
    return raw


def load_deferred_extension_map(skip_list_path: str | Path) -> dict[str, str]:
    """Load deferred extension -> reason map without constructing a SkipManager."""
    raw = _load_skip_source(skip_list_path)
    return _load_format_list(raw, "deferred_formats", "deferred format")


def load_placeholder_format_map(skip_list_path: str | Path) -> dict[str, str]:
    """Load placeholder extension -> reason map from skip_list.yaml."""
    raw = _load_skip_source(skip_list_path)
    return _load_format_list(raw, "placeholder_formats", "placeholder format")


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

    def __init__(
        self,
        skip_list_path: str | Path,
        hasher: Hasher,
        extra_deferred_exts: dict[str, str] | None = None,
        ocr_mode: str = "auto",
    ):
        self.hasher = hasher
        self._skipped: list[dict] = []
        self._reason_counts: dict[str, int] = defaultdict(int)
        # Parse-time OCR policy drives whether image-asset families get skipped.
        # "skip" = image parsing is disabled at runtime → hash/defer images so
        # the parser does not burn threads producing [IMAGE_METADATA] junk.
        # "auto"/"force" = images may yield real text → parse them as normal.
        self._ocr_mode = (ocr_mode or "auto").lower()

        path = Path(skip_list_path)
        if not path.exists():
            logger.warning("Skip list not found at %s — no skip rules loaded.", path)
            self._deferred_exts: dict[str, str] = {}
            self._sidecar_suffixes: list[str] = []
            self._conditions: dict = {}
            self._image_asset_exts: set[str] = set()
            self._encrypted_name_tokens: list[str] = []
            self._encrypted_name_patterns: list[tuple[str, re.Pattern[str]]] = []
            if extra_deferred_exts:
                self._deferred_exts.update(extra_deferred_exts)
            return

        raw = _load_skip_source(path)

        # Build extension -> reason map (lowercase, with leading dot)
        self._deferred_exts = load_deferred_extension_map(path)
        if extra_deferred_exts:
            self._deferred_exts.update(extra_deferred_exts)

        # OCR sidecar suffixes — V1 lesson: 55.6% of corpus was junk from these
        self._sidecar_suffixes = [
            s.lower() for s in raw.get("ocr_sidecar_suffixes", [])
        ]
        if self._sidecar_suffixes:
            logger.info("Loaded %d OCR sidecar suffix filters", len(self._sidecar_suffixes))

        # Image-asset family: hash/defer only when OCR is disabled at runtime.
        # Sprint skip/defer hardening 2026-04-09: Run 6 evidence showed 15,237
        # of 15,239 image files produced pure [IMAGE_METADATA] chunks (~6.3% of
        # the whole corpus) because Tesseract was not installed. Deferring this
        # family when ocr_mode == "skip" keeps hash continuity intact and
        # surfaces every file in skip_manifest.json so nothing is hidden.
        image_exts_raw = raw.get("image_asset_extensions", [])
        self._image_asset_exts = set()
        for ext in image_exts_raw:
            e = str(ext).lower()
            if not e.startswith("."):
                e = f".{e}"
            self._image_asset_exts.add(e)
        if self._image_asset_exts:
            logger.info(
                "Loaded %d image-asset extensions (active when ocr_mode='skip'; current='%s')",
                len(self._image_asset_exts), self._ocr_mode,
            )

        # Encrypted-by-filename-cue tokens. These are generic tokens that
        # strongly suggest a file is password-protected or DRM'd even when the
        # magic-byte detector does not fire (e.g. producer tools that wrap
        # encrypted payloads in an outer container). Match is case-insensitive
        # and anchored to alphanumeric boundaries, so ``unencrypted_notes.pdf``
        # does NOT match the ``encrypted`` token while ``contract_encrypted.pdf``
        # and ``Report.ENCRYPTED.v2.pdf`` both do. Distinct from magic-byte
        # detection in the skip manifest so operators can see the two classes
        # separately.
        self._encrypted_name_tokens: list[str] = []
        self._encrypted_name_patterns: list[tuple[str, re.Pattern[str]]] = []
        for tok in raw.get("encrypted_filename_tokens", []):
            tok_str = str(tok).strip()
            if not tok_str:
                continue
            self._encrypted_name_tokens.append(tok_str.lower())
            self._encrypted_name_patterns.append(
                (tok_str.lower(), _compile_token_boundary(tok_str))
            )
        if self._encrypted_name_patterns:
            logger.info(
                "Loaded %d encrypted-filename-cue tokens (boundary-anchored)",
                len(self._encrypted_name_patterns),
            )

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

        # 5. OCR sidecar suffix (V1 lesson: 55.6% of corpus was sidecar junk)
        name_lower = name.lower()
        for suffix in self._sidecar_suffixes:
            if name_lower.endswith(suffix):
                return True, f"OCR sidecar artifact ({suffix})"

        # 6. Image-asset family — hash/defer when OCR is disabled at runtime.
        # This prevents 15K+ [IMAGE_METADATA] junk chunks on Tesseract-less
        # workstations (Run 6 evidence, 2026-04-09).
        if self._ocr_mode == "skip" and ext in self._image_asset_exts:
            return True, "image asset (OCR disabled — metadata-only parse suppressed)"

        # 7. Encrypted-by-filename-cue — distinct class from magic-byte detect.
        # Token boundary is alphanumeric so ``unencrypted_notes.pdf`` does not
        # trip the ``encrypted`` token. Checked against the basename (with
        # extension) to cover forms like ``Report.ENCRYPTED.v2.pdf``.
        encrypted_name_reason = ""
        if self._encrypted_name_patterns:
            for token, pattern in self._encrypted_name_patterns:
                if pattern.search(name):
                    encrypted_name_reason = f"encrypted file (filename cue: '{token}')"
                    break

        # 8. Encrypted magic-byte detection
        # Prefer a confirmed payload-level signal over the filename cue when
        # both are present on the same file.
        if self._conditions.get("encrypted") and file_path.exists():
            if self._is_encrypted(file_path, ext):
                return True, "encrypted file (magic bytes)"

        if encrypted_name_reason:
            return True, encrypted_name_reason

        # 9. Deferred format
        if ext in self._deferred_exts:
            return True, self._deferred_exts[ext]

        return False, ""

    def record_skip(self, file_path: Path, reason: str) -> None:
        """Hash the file and record it in the skip manifest."""
        state = self.hasher.get_state(file_path)
        stat = file_path.stat()
        if state and state["mtime"] == stat.st_mtime and state["size"] == stat.st_size:
            content_hash = state["hash"]
        else:
            content_hash = self.hasher.hash_file(file_path)

        status = "deferred" if file_path.suffix.lower() in self._deferred_exts else "skipped"
        self.hasher.update_hash(file_path, content_hash, status=status)
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

    @property
    def deferred_extensions(self) -> set[str]:
        return set(self._deferred_exts)

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
