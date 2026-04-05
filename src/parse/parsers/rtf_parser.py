"""RTF parser — strips Rich Text Format markup via striprtf."""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class RtfParser:
    """Parse .rtf files using striprtf library."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        try:
            raw = path.read_text(encoding="utf-8-sig", errors="ignore")
            from striprtf.striprtf import rtf_to_text
            text = rtf_to_text(raw)
        except ImportError:
            logger.warning("striprtf not installed — falling back to raw text for %s", path.name)
            try:
                text = path.read_text(encoding="utf-8-sig", errors="ignore")
            except Exception:
                text = ""
        except Exception as e:
            logger.error("RTF parse failed for %s: %s", path.name, e)
            text = ""

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=0.85 if text.strip() else 0.0,
            file_ext=".rtf",
            file_size=path.stat().st_size,
        )
