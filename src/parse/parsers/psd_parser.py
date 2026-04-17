"""
Photoshop PSD parser -- reads Adobe Photoshop .psd files.

Plain English: Photoshop documents are layered images with optional
text layers (captions, labels, annotations). This parser opens the PSD
and returns:

  * Document dimensions and color mode
  * All layer names
  * The contents of every text layer it can find

So an engineer searching the corpus can locate a diagram by a caption
that lives inside its source Photoshop file.

Uses the ``psd-tools`` library. If it isn't installed the parser
returns empty text rather than failing.
"""

from __future__ import annotations

from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument


class PsdParser:
    """Extract layer names and text-layer contents from Photoshop .psd files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a .psd file and return its layer names plus any text-layer contents."""
        path = Path(file_path)

        try:
            from psd_tools import PSDImage
        except ImportError:
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            psd = PSDImage.open(str(path))
        except Exception:
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        parts: list[str] = [
            f"Photoshop Document: {path.name}",
            f"Dimensions: {psd.width} x {psd.height}",
            f"Color mode: {psd.color_mode}",
        ]

        layer_names: list[str] = []
        text_contents: list[str] = []
        try:
            descendants = list(psd.descendants())
            parts.append(f"Layers: {len(descendants)}")
            for layer in descendants:
                layer_names.append(layer.name)
                if getattr(layer, "kind", "") == "type":
                    try:
                        layer_text = getattr(layer, "text", "") or ""
                        if layer_text.strip():
                            text_contents.append(layer_text.strip())
                    except Exception:
                        pass
        except Exception:
            pass

        if layer_names:
            parts.append("Layer names: " + ", ".join(layer_names))
        if text_contents:
            parts.append("")
            parts.append("Text content:")
            parts.extend(f"  {text}" for text in text_contents)

        text = "\n".join(parts).strip()
        quality = 0.8 if text_contents else 0.3 if text else 0.0
        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )
