"""
Legacy PowerPoint .ppt parser -- reads PowerPoint 97-2003 binary format.

Extracts text records from the OLE2 PowerPoint Document stream.
Falls back to raw binary text scan if olefile is unavailable.
Ported from V1 (src/parsers/office_ppt_parser.py).
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import List

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class PptParser:
    """Parse legacy .ppt files via OLE2 binary extraction."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        # Strategy 1: olefile structured extraction
        text = self._try_olefile(path)
        if text:
            quality = 0.7
        else:
            # Strategy 2: raw binary text scan
            text = _extract_text_from_binary(path)
            quality = 0.3 if text else 0.0

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".ppt",
            file_size=path.stat().st_size if path.exists() else 0,
        )

    @staticmethod
    def _try_olefile(path: Path) -> str:
        """Extract text and metadata from .ppt via OLE2 structure."""
        try:
            import olefile
        except ImportError:
            logger.debug("olefile not available for .ppt parsing")
            return ""

        parts = []
        try:
            ole = olefile.OleFileIO(str(path))

            # Extract metadata
            meta = ole.get_metadata()
            for field in ["title", "subject", "author", "comments", "keywords"]:
                val = getattr(meta, field, None)
                if val:
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="ignore")
                    val = str(val).strip()
                    if val:
                        parts.append(f"{field.title()}: {val}")

            # Read PowerPoint Document stream for text records
            if ole.exists("PowerPoint Document"):
                stream = ole.openstream("PowerPoint Document")
                data = stream.read()
                stream.close()
                texts = _extract_ppt_text_records(data)
                if texts:
                    parts.extend(texts)
                elif data:
                    text = _extract_runs_from_bytes(data)
                    if text.strip():
                        parts.append(text.strip())

            ole.close()
        except Exception as e:
            logger.debug("olefile failed for %s: %s", path.name, e)

        return "\n\n".join(parts).strip()


def _extract_ppt_text_records(data: bytes) -> List[str]:
    """
    Parse PPT binary for text records.

    Record types: 0x0FA0 = TextCharsAtom (UTF-16LE),
                  0x0FA8 = TextBytesAtom (ASCII/Latin-1).
    """
    texts = []
    pos = 0
    data_len = len(data)

    while pos + 8 <= data_len:
        try:
            ver_inst, rec_type, rec_len = struct.unpack_from("<HHI", data, pos)
        except struct.error:
            break

        pos += 8
        if rec_len > data_len - pos:
            break

        if rec_type == 0x0FA0 and rec_len >= 2:
            try:
                text = data[pos:pos + rec_len].decode("utf-16-le", errors="ignore").strip()
                if text and len(text) > 1:
                    texts.append(text)
            except Exception:
                pass
        elif rec_type == 0x0FA8 and rec_len >= 1:
            try:
                text = data[pos:pos + rec_len].decode("latin-1", errors="ignore").strip()
                if text and len(text) > 1:
                    texts.append(text)
            except Exception:
                pass

        pos += rec_len

    return texts


def _extract_text_from_binary(path: Path) -> str:
    """Last resort: scan binary for printable text runs."""
    try:
        with open(path, "rb") as f:
            data = f.read(2_000_000)
        return _extract_runs_from_bytes(data)
    except Exception as e:
        logger.debug("Raw binary scan failed for %s: %s", path.name, e)
        return ""


def _extract_runs_from_bytes(data: bytes) -> str:
    """Extract readable text runs (8+ printable chars) from binary data."""
    MIN_RUN = 8
    parts = []
    current = []

    for byte in data:
        if 32 <= byte <= 126 or byte in (9, 10, 13):
            current.append(chr(byte))
        else:
            if len(current) >= MIN_RUN:
                parts.append("".join(current).strip())
            current = []

    if len(current) >= MIN_RUN:
        parts.append("".join(current).strip())

    filtered = []
    for p in parts:
        alpha = sum(1 for c in p if c.isalpha() or c.isspace())
        if alpha > len(p) * 0.5 and len(p) > MIN_RUN:
            filtered.append(p)

    return "\n".join(filtered).strip()
