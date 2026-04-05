"""
EML email parser -- extracts headers + body from .eml files.

Uses Python stdlib only (email module). Prefers plain text body,
falls back to stripped HTML.
Ported from V1 (src/parsers/eml_parser.py).
"""

from __future__ import annotations

import html as html_mod
import logging
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Optional

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    """Convert HTML to plain text without external dependencies."""
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = html_mod.unescape(text)
    return text.strip()


def _safe_decode(payload: Optional[bytes], charset: Optional[str]) -> str:
    """Decode email body bytes with encoding fallback."""
    if not payload:
        return ""
    enc = (charset or "utf-8").strip() if charset else "utf-8"
    try:
        return payload.decode(enc, errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


class EmlParser:
    """Parse .eml email files into text."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            with open(path, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)

            # Extract headers
            def _h(name: str) -> str:
                v = msg.get(name)
                return str(v) if v is not None else ""

            headers = {
                "subject": _h("Subject"),
                "from": _h("From"),
                "to": _h("To"),
                "cc": _h("Cc"),
                "date": _h("Date"),
            }

            # Extract body -- prefer plain text, fall back to HTML
            text_plain = ""
            text_html = ""

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    disp = part.get_content_disposition()
                    if disp == "attachment":
                        continue
                    if ctype in ("text/plain", "text/html"):
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset()
                        decoded = _safe_decode(payload, charset).strip()
                        if not decoded:
                            continue
                        if ctype == "text/plain" and not text_plain:
                            text_plain = decoded
                        elif ctype == "text/html" and not text_html:
                            text_html = decoded
            else:
                ctype = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset()
                decoded = _safe_decode(payload, charset).strip()
                if ctype == "text/plain":
                    text_plain = decoded
                elif ctype == "text/html":
                    text_html = decoded

            # Choose best body
            body = ""
            if text_plain:
                body = text_plain
            elif text_html:
                body = _strip_html(text_html)

            # Combine headers + body
            header_block = "\n".join([
                f"Subject: {headers['subject']}",
                f"From: {headers['from']}",
                f"To: {headers['to']}",
                f"Cc: {headers['cc']}",
                f"Date: {headers['date']}",
            ]).strip()

            text = (header_block + "\n\n" + body).strip() if body else header_block
            quality = self._score_quality(text)

        except Exception as e:
            logger.error("EML parse failed for %s: %s", path.name, e)
            text = ""
            quality = 0.0

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".eml",
            file_size=path.stat().st_size if path.exists() else 0,
        )

    @staticmethod
    def _score_quality(text: str) -> float:
        if not text.strip():
            return 0.0
        if len(text.strip()) < 50:
            return 0.3
        return 0.85
