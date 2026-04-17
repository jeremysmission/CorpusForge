"""
Mbox parser -- reads bulk email archives in the .mbox format.

Plain English: an .mbox file is a single file that contains many emails
concatenated together (used by Unix mailers, Thunderbird exports, and
Gmail Takeout). This parser walks through the messages in order,
extracts each one's From/To/Subject/Date and body, and joins them all
into one searchable text block for the Forge pipeline.

Safety caps (operator-visible):
  * Max 200 messages per archive. Larger archives are truncated with a
    visible note so reviewers know some content was skipped.
  * Max 5000 characters of body per message. Long threads stay readable
    and the index stays a reasonable size.

Ported from V1 (src/parsers/mbox_parser.py).
"""

from __future__ import annotations

import logging
import mailbox
from pathlib import Path
from typing import List

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)

_MAX_MESSAGES = 200
_MAX_BODY_CHARS = 5000


def _decode_payload(part) -> str:
    """Decode email part payload with charset fallback."""
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _get_email_body(msg) -> str:
    """Extract plain text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return _decode_payload(part)
    else:
        return _decode_payload(msg)
    return ""


class MboxParser:
    """Extract messages from .mbox bulk-email archive files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open an .mbox archive and return its messages joined as text."""
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            mbox = mailbox.mbox(str(path))
        except Exception as e:
            logger.error("Cannot open mbox %s: %s", path.name, e)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=".mbox",
                file_size=path.stat().st_size if path.exists() else 0,
            )

        parts: List[str] = [f"Email Archive: {path.name}"]
        msg_count = 0

        try:
            for message in mbox:
                if msg_count >= _MAX_MESSAGES:
                    parts.append(f"\n... truncated at {_MAX_MESSAGES} messages")
                    break
                msg_count += 1
                parts.append(f"\n--- Message {msg_count} ---")

                for header in ["From", "To", "Subject", "Date"]:
                    val = message.get(header, "")
                    if val:
                        parts.append(f"{header}: {val}")

                body = _get_email_body(message)
                if body:
                    parts.append(body[:_MAX_BODY_CHARS])
        except Exception as e:
            logger.error("Mbox parse error for %s: %s", path.name, e)

        text = "\n".join(parts).strip()
        quality = self._score_quality(text, msg_count)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".mbox",
            file_size=path.stat().st_size if path.exists() else 0,
        )

    @staticmethod
    def _score_quality(text: str, msg_count: int) -> float:
        if not text.strip() or msg_count == 0:
            return 0.0
        if len(text.strip()) < 50:
            return 0.3
        return 0.8
