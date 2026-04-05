"""
Legacy Excel .xls parser -- reads Excel 97-2003 binary format.

Pipeline: xlrd (best) -> olefile metadata -> raw binary scan.
Ported from V1 (src/parsers/office_xls_parser.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class XlsParser:
    """Parse legacy .xls files with multi-strategy fallback."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        # Strategy 1: xlrd (purpose-built .xls reader)
        text = self._try_xlrd(path)
        if text:
            quality = 0.85
        else:
            # Strategy 2: olefile metadata + stream extraction
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
            file_ext=".xls",
            file_size=path.stat().st_size if path.exists() else 0,
        )

    @staticmethod
    def _try_xlrd(path: Path) -> str:
        """Extract cell values using xlrd."""
        try:
            import xlrd
        except ImportError:
            logger.debug("xlrd not available for .xls parsing")
            return ""

        parts = []
        try:
            wb = xlrd.open_workbook(str(path), on_demand=True)
            for sheet_idx in range(wb.nsheets):
                sheet = wb.sheet_by_index(sheet_idx)
                rows = []
                for row_idx in range(sheet.nrows):
                    cells = []
                    for col_idx in range(sheet.ncols):
                        cell = sheet.cell(row_idx, col_idx)
                        val = cell.value
                        if val is None or (isinstance(val, str) and not val.strip()):
                            continue
                        cells.append(str(val).strip())
                    if cells:
                        rows.append("\t".join(cells))
                if rows:
                    parts.append(f"[Sheet: {sheet.name}]\n" + "\n".join(rows))
            wb.release_resources()
        except Exception as e:
            logger.debug("xlrd failed for %s: %s", path.name, e)

        return "\n\n".join(parts).strip()

    @staticmethod
    def _try_olefile(path: Path) -> str:
        """Extract metadata + text fragments via OLE2 structure."""
        try:
            import olefile
        except ImportError:
            logger.debug("olefile not available for .xls fallback")
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

            for stream_name in ["Workbook", "Book"]:
                if ole.exists(stream_name):
                    stream = ole.openstream(stream_name)
                    data = stream.read(2_000_000)
                    stream.close()
                    text = _extract_runs_from_bytes(data)
                    if text.strip():
                        parts.append(text.strip())
                    break
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
