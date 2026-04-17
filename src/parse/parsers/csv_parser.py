"""
CSV/TSV parser -- reads comma-separated and tab-separated spreadsheets
as plain text.

Plain English: treats the whole file as text so the chunker downstream
can split on rows naturally. Handles utf-8-sig first (strips the BOM
some Excel exports leave behind) and falls back to latin-1 for old
Windows files. Large files are capped at 100,000 rows.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)

_MAX_ROWS = 100_000  # safety cap against giant CSV exports


class CsvParser:
    """Read .csv and .tsv files as text, preserving row structure."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Read a CSV/TSV file and return its rows as text."""
        path = Path(file_path)
        try:
            text = self._read_file(path)
        except Exception as e:
            logger.error("CSV parse failed for %s: %s", path.name, e)
            text = ""

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=0.9 if text.strip() else 0.0,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size,
        )

    def _read_file(self, path: Path) -> str:
        """Read CSV as text, preserving structure for chunking."""
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="latin-1")

        lines = raw.splitlines()
        if len(lines) > _MAX_ROWS:
            lines = lines[:_MAX_ROWS]
        return "\n".join(lines)
