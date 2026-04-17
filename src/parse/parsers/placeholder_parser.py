"""
Placeholder parser -- the "we know about this file but can't fully
read it yet" stand-in.

Plain English: some formats are recognized by Forge (SolidWorks parts,
DWG drawings, OneNote sections, MS Project files, legacy Visio, etc.)
but we can't fully extract their contents without heavyweight or
environment-specific tooling. Rather than silently dropping those files
from the export, this parser creates a small "identity card" so the
file still appears in the corpus:

  * File name and type
  * File size
  * A low quality score (0.15) so downstream stages know it's a stub
  * A human-readable note explaining what would be needed to fully
    parse it (e.g., "convert DWG to DXF first")

This is the "deferred-not-forgotten" pattern: operators and reviewers
can always see that the file existed and know what the next step would
be to bring it into the real index.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

_PLACEHOLDER_INFO = {
    ".prt": (
        "SolidWorks Part",
        "Requires SolidWorks installed plus pywin32 COM API. Alternative: export to STEP or IGES.",
    ),
    ".sldprt": (
        "SolidWorks Part",
        "Same as .prt -- requires SolidWorks installed.",
    ),
    ".asm": (
        "SolidWorks Assembly",
        "Requires SolidWorks installed plus pywin32 COM API. Alternative: export to STEP.",
    ),
    ".sldasm": (
        "SolidWorks Assembly",
        "Same as .asm -- requires SolidWorks installed.",
    ),
    ".dwg": (
        "AutoCAD Drawing",
        "DWG is proprietary. Typical path is convert DWG to DXF, then parse DXF.",
    ),
    ".dwt": (
        "AutoCAD Drawing Template",
        "Same binary format family as DWG. Conversion to DXF is typically required.",
    ),
    ".mpp": (
        "Microsoft Project",
        "MPXJ can read .mpp files but needs a Java runtime. Current Forge path is placeholder-only.",
    ),
    ".vsd": (
        "Visio Diagram (Legacy)",
        "Legacy .vsd is binary OLE. Convert to .vsdx for full parsing.",
    ),
    ".one": (
        "OneNote Section",
        "Best practical path is exporting OneNote content to PDF or HTML before ingest.",
    ),
    ".ost": (
        "Outlook Offline Storage",
        "Prefer exporting messages as .msg or .eml. Native .ost parsing is heavy and environment-specific.",
    ),
    ".eps": (
        "Encapsulated PostScript",
        "Current Forge path is placeholder-only. Full rendering/extraction needs extra tooling.",
    ),
}


class PlaceholderParser:
    """Create a small identity-card record for a recognized-but-unparseable file."""

    def __init__(self, extension: str = "") -> None:
        self._ext = extension.lower()

    def parse(self, file_path: Path) -> ParsedDocument:
        """Produce an identity-card ParsedDocument describing the skipped file."""
        path = Path(file_path)
        ext = self._ext or path.suffix.lower()
        format_name, requirement = _PLACEHOLDER_INFO.get(ext, ("Unknown Format", "No parser available."))

        parts = [
            f"File: {path.name}",
            f"Type: {format_name} ({ext})",
        ]

        try:
            st = os.stat(str(path))
            size_mb = st.st_size / (1024 * 1024)
            parts.append(f"Size: {size_mb:.1f} MB ({st.st_size:,} bytes)")
        except Exception:
            pass

        parts.append("Parser status: PLACEHOLDER (content not yet extractable)")
        parts.append(f"Requirement: {requirement}")
        text = "\n".join(parts)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=0.15,
            file_ext=ext,
            file_size=path.stat().st_size if path.exists() else 0,
        )
