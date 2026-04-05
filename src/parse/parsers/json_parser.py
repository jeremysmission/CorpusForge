"""JSON parser — reads JSON files as formatted text."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class JsonParser:
    """Parse .json files — pretty-prints for readability in chunks."""

    def parse(self, file_path: Path) -> ParsedDocument:
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
