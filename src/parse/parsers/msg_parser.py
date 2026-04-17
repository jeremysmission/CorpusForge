"""
MSG parser -- reads Outlook .msg email files.

Plain English: .msg is Outlook's proprietary email format. This parser
pulls out the From/To/Subject/Date headers and the message body, then
returns them as plain text so the Forge pipeline can chunk and index
the email like any other document.

Two strategies, tried in order:
  1. python-oxmsg (best quality, clean field access).
  2. olefile fallback that digs raw OLE2 streams out of the file when
     the preferred library isn't installed or fails.

If both strategies come back empty, the operator gets an empty text
result rather than a crash.

Ported from V1 (src/parsers/msg_parser.py).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class MsgParser:
    """Extract email headers and body from Outlook .msg files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a .msg email and return its headers + body as text."""
        path = Path(file_path)
        text = self._try_oxmsg(path)
        if not text.strip():
            text = self._try_olefile(path)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=0.85 if text.strip() else 0.0,
            file_ext=".msg",
            file_size=path.stat().st_size,
        )

    def _try_oxmsg(self, path: Path) -> str:
        """Extract using python-oxmsg (best quality)."""
        try:
            from oxmsg import Message
            msg = Message(str(path))
            parts = []
            if getattr(msg, "sender", None):
                parts.append(f"From: {msg.sender}")
            if getattr(msg, "to", None):
                parts.append(f"To: {msg.to}")
            if getattr(msg, "subject", None):
                parts.append(f"Subject: {msg.subject}")
            if getattr(msg, "date", None):
                parts.append(f"Date: {msg.date}")
            body = getattr(msg, "body", None) or ""
            if not body and getattr(msg, "html_body", None):
                body = re.sub(r"<[^>]+>", " ", msg.html_body)
            if body:
                parts.append(f"\n{body}")
            return "\n".join(parts)
        except ImportError:
            return ""
        except Exception as e:
            logger.debug("oxmsg failed for %s: %s", path.name, e)
            return ""

    def _try_olefile(self, path: Path) -> str:
        """Fallback: extract using olefile (basic OLE2 field extraction)."""
        try:
            import olefile
            ole = olefile.OleFileIO(str(path))
            parts = []
            field_map = {
                "Subject": "__substg1.0_0037001F",
                "From": "__substg1.0_0C1A001F",
                "To": "__substg1.0_0E04001F",
                "Body": "__substg1.0_1000001F",
            }
            for label, stream in field_map.items():
                try:
                    if ole.exists(stream):
                        data = ole.openstream(stream).read()
                        text = data.decode("utf-16-le", errors="ignore").strip()
                        if text:
                            parts.append(f"{label}: {text}")
                except Exception:
                    continue
            ole.close()
            return "\n".join(parts)
        except ImportError:
            return ""
        except Exception as e:
            logger.debug("olefile failed for %s: %s", path.name, e)
            return ""
