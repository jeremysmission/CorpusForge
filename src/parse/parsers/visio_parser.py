"""
Visio parser -- extracts text from .vsdx diagram files.

Extracts shape text, connector labels, and page titles.
Ported from V1 (src/parsers/visio_parser.py).
Dependencies: pip install vsdx (optional, graceful fallback).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class VisioParser:
    """Parse Microsoft Visio .vsdx files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            import vsdx
        except ImportError:
            logger.debug("vsdx not installed, cannot parse %s", path.name)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            doc = vsdx.VisioFile(str(path))
        except Exception as e:
            logger.debug("Cannot read VSDX %s: %s", path.name, e)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        parts: list[str] = [f"Visio Diagram: {path.name}"]
        shape_count = 0

        try:
            for page in doc.pages:
                page_name = getattr(page, "name", "Unnamed Page")
                parts.append(f"\n--- Page: {page_name} ---")

                for shape in page.child_shapes:
                    shape_count += 1
                    shape_text = shape.text or ""
                    shape_text = shape_text.strip()
                    if shape_text:
                        parts.append(shape_text)

                    # Check sub-shapes (grouped shapes)
                    if hasattr(shape, "sub_shapes"):
                        subs = shape.sub_shapes() if callable(shape.sub_shapes) else []
                        for sub in subs:
                            sub_text = getattr(sub, "text", "") or ""
                            if sub_text.strip():
                                parts.append(sub_text.strip())
                                shape_count += 1

            doc.close()
        except Exception as e:
            logger.debug("Visio parse error for %s: %s", path.name, e)

        text = "\n".join(parts).strip()
        quality = _score_quality(text, shape_count)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )


def _score_quality(text: str, shape_count: int) -> float:
    """Score quality based on extracted content."""
    if not text.strip():
        return 0.0
    if shape_count == 0:
        return 0.3
    if shape_count < 3:
        return 0.5
    return 0.8
