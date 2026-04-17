"""
Plain-text parser -- the simplest parser in Forge.

Plain English: reads plain-text files (.txt, .md, .log, config files,
etc.) straight off disk and hands the text to the pipeline. No fancy
extraction needed because the content is already text.

Also defines ``ParsedDocument``, the small record every parser in Forge
returns -- think of it as a standard envelope containing the cleaned
text plus a few metadata fields (source path, file size, extension, and
a quality score).

Encoding note: files are read as utf-8-sig first (which quietly strips
the Byte-Order-Mark often left by Windows/corporate editors), then
falls back to latin-1 so old Windows files don't blow up.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedDocument:
    """The standard "parsed file" record every parser in Forge returns.

    Fields:
      * source_path    -- original file on disk
      * text           -- the extracted clean text the pipeline will chunk
      * parse_quality  -- 0.0-1.0 confidence score for this parse
      * file_ext       -- the file's extension (lowercased)
      * file_size      -- size in bytes, for reporting/manifests
    """

    source_path: str
    text: str
    parse_quality: float
    file_ext: str
    file_size: int


class TxtParser:
    """Read plain-text files directly, with a safe encoding fallback."""

    SUPPORTED_EXTENSIONS = frozenset({
        ".txt", ".md", ".log", ".csv", ".json", ".xml",
        ".yaml", ".yml", ".ini", ".cfg", ".conf",
    })

    def parse(self, file_path: Path) -> ParsedDocument:
        """Read a plain-text file and return its contents as a ParsedDocument."""
        path = Path(file_path)
        text = self._read_text(path)
        quality = self._score_quality(text)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size,
        )

    def _read_text(self, path: Path) -> str:
        """Read file content with encoding fallback."""
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    def _score_quality(self, text: str) -> float:
        """
        Basic parse quality score 0.0-1.0.

        For plain text, quality is based on whether the file has
        meaningful content (not empty, not all whitespace, not binary garbage).
        """
        if not text or not text.strip():
            return 0.0

        # Check for binary garbage: high ratio of non-printable chars
        printable_ratio = sum(
            1 for c in text[:2000] if c.isprintable() or c in "\n\r\t"
        ) / max(len(text[:2000]), 1)

        if printable_ratio < 0.8:
            return 0.2  # Likely binary or corrupted

        # Reasonable text
        if len(text.strip()) < 50:
            return 0.5  # Very short

        return 1.0
