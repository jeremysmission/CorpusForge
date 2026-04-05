"""DOCX parser — extracts text from Word documents via python-docx."""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class DocxParser:
    """Parse .docx files using python-docx."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        try:
            from docx import Document
            doc = Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n\n".join(paragraphs)
        except Exception as e:
            logger.error("DOCX parse failed for %s: %s", path.name, e)
            text = ""

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=1.0 if text.strip() else 0.0,
            file_ext=".docx",
            file_size=path.stat().st_size,
        )
