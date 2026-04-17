"""
Chunker — splits documents into overlapping chunks with smart boundary detection.

Plain-English role
------------------
Stage 5 of the pipeline. The parser has already turned a file into one
long block of text. This module cuts that block into retrieval-sized
passages (roughly 1200 characters each, with 200 characters of overlap
so no fact falls cleanly through a boundary). Each passage also gets
its section heading prepended when one can be found nearby, which helps
the embedding model keep document context.

Output feeds directly into the enrichment and embedding stages.

Ported from HybridRAG V1 (src/core/chunker.py). Battle-tested on 420K+ files.

Key design decisions (carried from V1):
  1. Smart boundary: paragraph > sentence > newline > hard cut
  2. Overlap (200 chars) ensures facts near boundaries appear in at least one chunk
  3. Section heading prepend gives the embedding model document context
  4. Heading detection via ALL CAPS, numbered sections, colon-terminated lines
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ChunkerConfig:
    """Chunking parameters — matches CorpusForge config schema."""

    chunk_size: int = 1200
    overlap: int = 200
    max_heading_len: int = 160


class Chunker:
    """
    Splits one document's text into overlapping chunks.

    An operator can picture this as scissors that try to cut at the end
    of a paragraph or sentence, leave a short overlap so ideas that span
    the cut stay together, and stick the nearest section heading on the
    front of each chunk so the embedding model sees the context.

    Ported from V1 — identical algorithm, cleaned up for CorpusForge.
    """

    def __init__(self, chunk_size: int = 1200, overlap: int = 200, max_heading_len: int = 160):
        """Store chunk-size targets used by every split."""
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.max_heading_len = max_heading_len

    @classmethod
    def from_config(cls, config: ChunkerConfig) -> "Chunker":
        """Create Chunker from a ChunkerConfig dataclass."""
        return cls(
            chunk_size=config.chunk_size,
            overlap=config.overlap,
            max_heading_len=config.max_heading_len,
        )

    def chunk_text(self, text: str) -> list[str]:
        """
        Split text into overlapping chunks.

        Algorithm (from V1):
          1. Start at position 0
          2. Look ahead chunk_size chars for tentative end
          3. In the second half, search backward for best break point
          4. Extract chunk, strip whitespace
          5. Look backward for nearest section heading, prepend if found
          6. Advance with overlap
          7. Repeat until end of text
        """
        if not text or not text.strip():
            return []

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.chunk_size, text_len)

            # Find best break point in the second half of the window
            if end < text_len:
                half = start + self.chunk_size // 2

                # First choice: paragraph break (double newline)
                para = text.rfind("\n\n", half, end)
                if para != -1:
                    end = para + 2
                else:
                    # Second choice: sentence end
                    sent = text.rfind(". ", half, end)
                    if sent != -1:
                        end = sent + 2
                    else:
                        # Third choice: any newline
                        nl = text.rfind("\n", half, end)
                        if nl != -1:
                            end = nl + 1
                        # Last resort: hard cut at chunk_size

            chunk = text[start:end].strip()

            if chunk:
                heading = self._find_heading(text, start)
                if heading and not chunk.startswith(heading):
                    chunk = "[SECTION] " + heading + "\n" + chunk
                chunks.append(chunk)

            if end >= text_len:
                break

            # Advance with overlap; max() prevents infinite loop
            start = max(end - self.overlap, start + 1)

        return chunks

    def _find_heading(self, text: str, pos: int) -> str:
        """
        Look backward from pos to find nearest section heading.

        Searches up to 2000 chars back. Returns heading text or empty string.

        Heading rules (from V1):
          1. ALL CAPS line > 3 chars
          2. Numbered section (e.g. "3.2.1 Signal Processing")
          3. Line ending with ":" under 80 chars
        """
        search_start = max(0, pos - 2000)
        region = text[search_start:pos]
        lines = region.split("\n")

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            if len(line) <= self.max_heading_len:
                if line.isupper() and len(line) > 3:
                    return line
                if re.match(r"^\d+(\.\d+)*\s+", line):
                    return line
                if line.endswith(":") and len(line) < 80:
                    return line

            # Only check the nearest non-empty line
            break

        return ""
