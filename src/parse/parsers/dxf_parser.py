"""
DXF parser -- reads AutoCAD DXF (.dxf) drawing files.

Plain English: DXF is the open exchange format AutoCAD uses for
engineering drawings. A drawing is mostly geometry, but engineers
embed plenty of searchable text: TEXT/MTEXT notes, attribute tags,
dimension callouts, layer names, and block definitions. This parser
pulls all of that out so the Forge pipeline can index drawings like
any other document.

Uses the optional ``ezdxf`` library. If it's missing or the file isn't
a valid DXF, the parser returns empty text rather than crashing.

Ported from V1 (src/parsers/dxf_parser.py).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class DxfParser:
    """Extract searchable text (labels, notes, layers) from AutoCAD .dxf files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a .dxf drawing and return all embedded text."""
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            import ezdxf
        except ImportError:
            logger.debug("ezdxf not installed, cannot parse %s", path.name)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=".dxf",
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            doc = ezdxf.readfile(str(path))
        except Exception as e:
            logger.debug("Cannot read DXF %s: %s", path.name, e)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=".dxf",
                file_size=path.stat().st_size if path.exists() else 0,
            )

        parts: list[str] = []
        layer_names: list[str] = []

        try:
            # Drawing metadata
            header = doc.header
            title = header.get("$TITLE", "") if hasattr(header, "get") else ""
            if title:
                parts.append(f"Title: {title}")

            # Layer names
            layer_names = [layer.dxf.name for layer in doc.layers]
            if layer_names:
                parts.append("Layers: " + ", ".join(layer_names))

            # Text entities from modelspace
            msp = doc.modelspace()
            for entity in msp:
                etype = entity.dxftype()

                if etype == "TEXT":
                    t = entity.dxf.text or ""
                    if t.strip():
                        parts.append(t.strip())

                elif etype == "MTEXT":
                    raw = entity.text or ""
                    clean = _strip_mtext_formatting(raw)
                    if clean.strip():
                        parts.append(clean.strip())

                elif etype == "ATTRIB":
                    tag = getattr(entity.dxf, "tag", "")
                    val = getattr(entity.dxf, "text", "")
                    if val.strip():
                        prefix = f"{tag}: " if tag else ""
                        parts.append(f"{prefix}{val.strip()}")

                elif etype == "DIMENSION":
                    t = getattr(entity.dxf, "text", "")
                    if t and t.strip() and t.strip() != "<>":
                        parts.append(f"DIM: {t.strip()}")

            # Block definitions
            for block in doc.blocks:
                if block.name.startswith("*"):
                    continue
                for entity in block:
                    etype = entity.dxftype()
                    if etype in ("TEXT", "MTEXT"):
                        t = entity.dxf.text if etype == "TEXT" else entity.text
                        t = t or ""
                        if etype == "MTEXT":
                            t = _strip_mtext_formatting(t)
                        if t.strip():
                            parts.append(t.strip())

        except Exception as e:
            logger.debug("DXF parse error for %s: %s", path.name, e)

        text = "\n\n".join(parts).strip()
        quality = _score_quality(text, len(parts))

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".dxf",
            file_size=path.stat().st_size if path.exists() else 0,
        )


def _strip_mtext_formatting(raw: str) -> str:
    """Remove common MTEXT formatting codes for cleaner text output."""
    text = raw
    text = re.sub(r"\{\\f[^;]*;", "", text)
    text = re.sub(r"\{\\[A-Za-z][^;]*;", "", text)
    text = text.replace("}", "")
    text = text.replace("\\P", "\n")
    text = text.replace("\\p", "\n")
    text = re.sub(r"\\[A-Za-z]", " ", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _score_quality(text: str, entity_count: int) -> float:
    """Score quality based on extracted content."""
    if not text.strip():
        return 0.0
    if entity_count < 2:
        return 0.3
    if entity_count < 5:
        return 0.5
    return 0.8
