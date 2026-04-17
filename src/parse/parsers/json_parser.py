"""
JSON parser -- reads .json files and pretty-prints them as text.

Plain English: JSON files hold structured data. This parser loads the
file, re-prints it with consistent indentation so chunks stay readable,
and returns the result as text the Forge pipeline can index. If a file
isn't valid JSON (e.g., someone saved a plain log as .json by mistake),
it falls back to returning the raw file contents.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class JsonParser:
    """Read .json files and pretty-print them for readable chunks."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Read a .json file and return formatted text, or raw text on parse error."""
        path = Path(file_path)
        try:
            raw = path.read_text(encoding="utf-8-sig")
            data = json.loads(raw)
            text = json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # Not valid JSON — treat as plain text
            try:
                text = path.read_text(encoding="utf-8-sig")
            except Exception:
                text = ""
        except Exception as e:
            logger.error("JSON parse failed for %s: %s", path.name, e)
            text = ""

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=0.9 if text.strip() else 0.0,
            file_ext=".json",
            file_size=path.stat().st_size,
        )
