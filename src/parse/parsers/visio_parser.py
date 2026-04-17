"""
Visio parser -- reads modern Microsoft Visio (.vsdx) diagrams.

Plain English: opens a Visio diagram and pulls the readable text out of
every shape, label, and grouped sub-shape on every page. Great for
architecture drawings, flow charts, and network diagrams where the
useful content is the text labels.

Uses the optional ``vsdx`` library. If it isn't installed the parser
returns empty text rather than failing, so the rest of the pipeline
keeps moving.

Ported from V1 (src/parsers/visio_parser.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class VisioParser:
    """Extract shape labels and page text from Microsoft Visio .vsdx diagrams."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a .vsdx diagram and return all shape/page text."""
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
