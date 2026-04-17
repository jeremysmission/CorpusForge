"""
XML parser -- reads .xml files and keeps just the readable text.

Plain English: XML files mix structural tags and real content. This
parser strips the tags and returns only the text content so it chunks
cleanly. Prefers the ``lxml`` library; falls back to a simple regex
strip if lxml isn't available.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class XmlParser:
    """Read .xml files and return just the text inside the tags."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Read an .xml file and return its text content with tags stripped."""
        path = Path(file_path)
        try:
            try:
                raw = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                raw = path.read_text(encoding="latin-1")

            text = self._extract_text(raw)
        except Exception as e:
            logger.error("XML parse failed for %s: %s", path.name, e)
            text = ""

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=0.85 if text.strip() else 0.0,
            file_ext=".xml",
            file_size=path.stat().st_size,
        )

    def _extract_text(self, xml: str) -> str:
        """Extract text from XML using lxml or regex fallback."""
        try:
            from lxml import etree
            root = etree.fromstring(xml.encode("utf-8", errors="ignore"))
            texts = [t.strip() for t in root.itertext() if t.strip()]
            return "\n".join(texts)
        except ImportError:
            pass
        except Exception:
            pass

        # Regex fallback: strip tags
        text = re.sub(r"<[^>]+>", " ", xml)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
