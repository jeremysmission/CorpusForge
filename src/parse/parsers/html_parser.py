"""
HTML parser -- reads local HTML/HTM files and strips out the markup.

Plain English: opens an HTML file from disk (never from the network)
and returns just the visible reading text -- navigation bars, scripts,
and styles are removed first so the chunks the Forge pipeline stores
are readable prose, not raw tags.

Prefers BeautifulSoup when available; falls back to simple regex tag
stripping if it isn't installed. Hardened for local-only use, no URLs
are ever fetched.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class HtmlParser:
    """Extract readable text from local .html/.htm files (no network access)."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a local HTML file and return its visible text."""
        path = Path(file_path)
        try:
            try:
                raw = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                raw = path.read_text(encoding="latin-1")

            text = self._extract_text(raw)
        except Exception as e:
            logger.error("HTML parse failed for %s: %s", path.name, e)
            text = ""

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=0.6 if text.strip() else 0.0,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size,
        )

    def _extract_text(self, html: str) -> str:
        """Strip HTML tags and extract visible text."""
        # Try BeautifulSoup first
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            # Remove script and style elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            pass

        # Fallback: regex strip
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
