"""HTML parser — extracts text from local HTML files."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class HtmlParser:
    """Parse .html and .htm files. No network access — local files only."""

    def parse(self, file_path: Path) -> ParsedDocument:
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
