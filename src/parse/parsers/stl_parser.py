"""
STL parser -- reads 3D mesh files used for CAD and 3D printing.

Plain English: .stl files hold geometry only -- no text content exists
to extract. Instead, this parser produces a human-readable description
of the model so it's still searchable: solid name (for ASCII STLs),
triangle and vertex counts, the bounding-box dimensions, X/Y/Z ranges,
and an estimated volume.

That way, a reviewer searching the corpus can still find a specific
part by its dimensions or name even though the file itself has no
prose.

Uses the optional ``numpy-stl`` library. If it isn't installed the
parser returns empty text rather than failing.

Ported from V1 (src/parsers/stl_parser.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class StlParser:
    """Produce a searchable description (size, counts, bounds) for a .stl 3D model."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a .stl 3D model and return a text summary of its geometry."""
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            from stl import mesh as stl_mesh
        except ImportError:
            logger.debug("numpy-stl not installed, cannot parse %s", path.name)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=".stl",
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            m = stl_mesh.Mesh.from_file(str(path))
        except Exception as e:
            logger.debug("Cannot read STL %s: %s", path.name, e)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=".stl",
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            # Solid name (ASCII STL header)
            name = getattr(m, "name", b"")
            if isinstance(name, bytes):
                name = name.decode("ascii", errors="ignore").strip()
            name = (name or "").strip()

            tri_count = len(m.vectors)
            vert_count = tri_count * 3

            # Bounding box
            mins = m.vectors.reshape(-1, 3).min(axis=0)
            maxs = m.vectors.reshape(-1, 3).max(axis=0)
            dims = maxs - mins

            # Volume estimate
            volume = 0.0
            if hasattr(m, "get_mass_properties"):
                try:
                    volume = float(m.get_mass_properties()[0])
                except Exception:
                    pass

            parts: list[str] = [f"3D Model (STL): {path.name}"]
            if name:
                parts.append(f"Solid name: {name}")
            parts.extend([
                f"Triangles: {tri_count:,}",
                f"Vertices: {vert_count:,}",
                f"Bounding box: {dims[0]:.2f} x {dims[1]:.2f} x {dims[2]:.2f}",
                f"X range: {mins[0]:.2f} to {maxs[0]:.2f}",
                f"Y range: {mins[1]:.2f} to {maxs[1]:.2f}",
                f"Z range: {mins[2]:.2f} to {maxs[2]:.2f}",
            ])
            if volume > 0:
                parts.append(f"Volume: {volume:.2f}")

            text = "\n".join(parts)
            quality = 0.7  # Metadata-only, no searchable text content

        except Exception as e:
            logger.debug("STL parse error for %s: %s", path.name, e)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".stl",
            file_size=path.stat().st_size if path.exists() else 0,
        )
