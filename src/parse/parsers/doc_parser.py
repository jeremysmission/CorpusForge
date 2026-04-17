"""
Legacy Word (.doc) parser -- reads the old Word 97-2003 binary format.

Plain English: .doc is the binary Word format used before 2007. It's
harder to read than modern .docx, so this parser tries three strategies
in order and uses whichever one produces readable text:

  1. ``antiword`` command-line tool -- cleanest output if installed.
  2. ``olefile`` -- pulls document metadata plus raw WordDocument stream
     out of the file's OLE2 container.
  3. Raw binary scan -- last resort; scans bytes for readable text runs.

Quality score reflects which strategy produced the text (high for
antiword, low for raw scan).

Ported from V1 (src/parsers/doc_parser.py).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class DocParser:
    """Extract text from legacy Word .doc files, with three fallback strategies."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a .doc file and return its text using the best available strategy."""
        path = Path(file_path)
        text = ""
        quality = 0.0

        # Strategy 1: antiword (external tool, best quality)
        text = self._try_antiword(path)
        if text:
            quality = 0.9
        else:
            # Strategy 2: olefile OLE2 extraction
            text = self._try_olefile(path)
            if text:
                quality = 0.5
            else:
                # Strategy 3: raw binary text scan
                text = _extract_text_from_binary(path)
                quality = 0.3 if text else 0.0

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".doc",
            file_size=path.stat().st_size if path.exists() else 0,
        )

    @staticmethod
    def _try_antiword(path: Path) -> str:
        """Extract text using antiword command-line tool."""
        try:
            result = subprocess.run(
                ["antiword", str(path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except FileNotFoundError:
            logger.debug("antiword not installed")
        except Exception as e:
            logger.debug("antiword failed for %s: %s", path.name, e)
        return ""

    @staticmethod
    def _try_olefile(path: Path) -> str:
        """Extract text and metadata via OLE2 structure."""
        try:
            import olefile
        except ImportError:
            logger.debug("olefile not available for .doc fallback")
            return ""

        parts = []
        try:
            ole = olefile.OleFileIO(str(path))
            meta = ole.get_metadata()
            for field in ["title", "subject", "author", "comments", "keywords"]:
                val = getattr(meta, field, None)
                if val:
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="ignore")
                    val = str(val).strip()
                    if val:
                        parts.append(f"{field.title()}: {val}")

            if ole.exists("WordDocument"):
                stream = ole.openstream("WordDocument")
                data = stream.read()
                stream.close()
                text = _extract_runs_from_bytes(data)
                if text.strip():
                    parts.append(text.strip())

            ole.close()
        except Exception as e:
            logger.debug("olefile failed for %s: %s", path.name, e)

        return "\n\n".join(parts).strip()


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
