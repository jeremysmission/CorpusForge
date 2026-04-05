"""
OpenDocument parser -- extracts text from .odt, .ods, .odp files.

These are ZIP archives containing XML (OASIS standard).
Ported from V1 (src/parsers/opendocument_parser.py).
Dependencies: stdlib only (zipfile + xml.etree).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class OpenDocumentParser:
    """Parse OpenDocument files (.odt, .ods, .odp)."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            with zipfile.ZipFile(str(path), "r") as zf:
                parts: list[str] = []

                # Extract metadata from meta.xml
                if "meta.xml" in zf.namelist():
                    try:
                        meta_xml = zf.read("meta.xml").decode("utf-8", errors="ignore")
                        meta_parts = _extract_meta(meta_xml)
                        parts.extend(meta_parts)
                    except Exception:
                        pass

                # Extract text from content.xml
                if "content.xml" in zf.namelist():
                    content_xml = zf.read("content.xml").decode("utf-8", errors="ignore")
                    content_text = _strip_xml_tags(content_xml)
                    if content_text.strip():
                        parts.append(content_text.strip())

                text = "\n\n".join(parts).strip()

        except zipfile.BadZipFile:
            logger.debug("Invalid ZIP structure: %s", path.name)
        except Exception as e:
            logger.debug("OpenDocument parse failed for %s: %s", path.name, e)

        quality = _score_quality(text)
        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )


def _extract_meta(meta_xml: str) -> list[str]:
    """Extract metadata fields from meta.xml."""
    parts: list[str] = []
    try:
        root = ET.fromstring(meta_xml)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("title", "subject", "keyword", "description", "creator"):
                if elem.text and elem.text.strip():
                    parts.append(f"{tag.title()}: {elem.text.strip()}")
    except ET.ParseError:
        pass
    return parts


def _strip_xml_tags(xml_text: str) -> str:
    """Strip XML tags and return plain text, inserting breaks at block elements."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return re.sub(r"<[^>]+>", " ", xml_text).strip()

    parts: list[str] = []
    _walk_element(root, parts)
    return "\n".join(line for line in parts if line.strip())


def _walk_element(elem: ET.Element, parts: list[str], depth: int = 0) -> None:
    """Recursively walk XML tree, collecting text from elements."""
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
    block_tags = {"p", "h", "table-row", "list-item", "frame"}

    if elem.text and elem.text.strip():
        parts.append(elem.text.strip())

    for child in elem:
        _walk_element(child, parts, depth + 1)

    if tag in block_tags:
        parts.append("")

    if elem.tail and elem.tail.strip():
        parts.append(elem.tail.strip())


def _score_quality(text: str) -> float:
    """Score text quality 0.0-1.0."""
    if not text.strip():
        return 0.0
    if len(text.strip()) < 50:
        return 0.3
    alpha_ratio = sum(1 for c in text[:2000] if c.isalpha()) / max(len(text[:2000]), 1)
    if alpha_ratio < 0.3:
        return 0.4
    return 0.9
