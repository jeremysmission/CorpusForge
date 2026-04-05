"""
EPUB parser -- extracts text from eBook files.

Pipeline: OPF spine (reading order) -> XHTML content -> strip HTML tags.
Ported from V1 (src/parsers/epub_parser.py).
Dependencies: stdlib only (zipfile + xml.etree + html.parser).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class EpubParser:
    """Parse EPUB eBook files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            with zipfile.ZipFile(str(path), "r") as zf:
                names = zf.namelist()
                opf_path = _find_opf(zf, names)

                if opf_path:
                    content_files = _parse_opf_spine(zf, opf_path)
                else:
                    content_files = [
                        n for n in names
                        if n.endswith((".xhtml", ".html", ".htm", ".xml"))
                        and "META-INF" not in n
                    ]

                parts: list[str] = []
                for cf in content_files:
                    try:
                        raw = zf.read(cf).decode("utf-8", errors="ignore")
                        stripped = _strip_html(raw)
                        if stripped.strip():
                            parts.append(stripped.strip())
                    except Exception:
                        continue

                text = "\n\n".join(parts).strip()

        except zipfile.BadZipFile:
            logger.debug("Invalid ZIP structure: %s", path.name)
        except Exception as e:
            logger.debug("EPUB parse failed for %s: %s", path.name, e)

        quality = _score_quality(text)
        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )


def _find_opf(zf: zipfile.ZipFile, names: list[str]) -> str | None:
    """Find the OPF package file inside the EPUB."""
    if "META-INF/container.xml" in names:
        try:
            container = zf.read("META-INF/container.xml").decode("utf-8", errors="ignore")
            root = ET.fromstring(container)
            for elem in root.iter():
                if elem.tag.endswith("rootfile"):
                    opf = elem.get("full-path")
                    if opf and opf in names:
                        return opf
        except Exception:
            pass
    for name in names:
        if name.endswith(".opf"):
            return name
    return None


def _parse_opf_spine(zf: zipfile.ZipFile, opf_path: str) -> list[str]:
    """Parse the OPF manifest to get content files in reading order."""
    try:
        opf_xml = zf.read(opf_path).decode("utf-8", errors="ignore")
        root = ET.fromstring(opf_xml)

        id_to_href: dict[str, str] = {}
        opf_dir = str(Path(opf_path).parent)
        if opf_dir == ".":
            opf_dir = ""

        for elem in root.iter():
            if elem.tag.endswith("}item") or elem.tag == "item":
                item_id = elem.get("id", "")
                href = elem.get("href", "")
                media = elem.get("media-type", "")
                if item_id and href and "html" in media.lower():
                    full_path = f"{opf_dir}/{href}" if opf_dir else href
                    id_to_href[item_id] = full_path

        content_files = []
        for elem in root.iter():
            if elem.tag.endswith("}itemref") or elem.tag == "itemref":
                idref = elem.get("idref", "")
                if idref in id_to_href:
                    content_files.append(id_to_href[idref])

        return content_files if content_files else list(id_to_href.values())
    except Exception:
        return []


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML tag stripper that collects text content."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _strip_html(html_text: str) -> str:
    """Strip HTML tags and return plain text."""
    try:
        extractor = _HTMLTextExtractor()
        extractor.feed(html_text)
        return " ".join(extractor.parts).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html_text).strip()


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
