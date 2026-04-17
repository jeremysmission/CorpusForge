"""
EVTX parser -- reads Windows Event Log (.evtx) files.

Plain English: when Windows records system, security, or application
events, they land in a binary .evtx file. This parser walks through
each event and writes it out as a one-line summary containing the
timestamp, Event ID, provider, and up to five data fields so the
Forge pipeline can index events as searchable text.

Safety: hard cap of 500 events per file to keep output sizes
reasonable; anything beyond that is truncated with a visible note.

Uses the optional ``python-evtx`` library. If it isn't installed the
parser returns empty text rather than failing.

Ported from V1 (src/parsers/evtx_parser.py).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)

_MAX_EVENTS = 500


class EvtxParser:
    """Extract searchable event records from Windows .evtx event logs."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a Windows .evtx log and return one text line per event."""
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            import Evtx.Evtx as evtx
        except ImportError:
            logger.debug("python-evtx not installed, cannot parse %s", path.name)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=".evtx",
                file_size=path.stat().st_size if path.exists() else 0,
            )

        parts: list[str] = [f"Windows Event Log: {path.name}"]
        event_count = 0

        try:
            with evtx.Evtx(str(path)) as log:
                for record in log.records():
                    if event_count >= _MAX_EVENTS:
                        parts.append(f"\n... truncated at {_MAX_EVENTS} events")
                        break
                    event_count += 1
                    try:
                        xml = record.xml()
                        line = _extract_event_text(xml)
                        if line:
                            parts.append(line)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("EVTX parse error for %s: %s", path.name, e)

        text = "\n".join(parts).strip()
        quality = _score_quality(event_count)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".evtx",
            file_size=path.stat().st_size if path.exists() else 0,
        )


def _extract_event_text(xml_str: str) -> str:
    """Extract key fields from an event XML record as plain text."""
    fields: dict[str, str] = {}

    for tag in ("TimeCreated", "EventID", "Level", "Provider",
                "Channel", "Computer"):
        m = re.search(
            rf"<{tag}[^>]*?(?:SystemTime=['\"]([^'\"]+)['\"]|>([^<]+)<)",
            xml_str,
        )
        if m:
            fields[tag] = m.group(1) or m.group(2)

    # Provider has Name attribute
    m = re.search(r"<Provider\s+Name=['\"]([^'\"]+)['\"]", xml_str)
    if m:
        fields["Provider"] = m.group(1)

    # Event data fields
    data_parts = re.findall(r"<Data[^>]*>([^<]+)</Data>", xml_str)

    ts = fields.get("TimeCreated", "")
    eid = fields.get("EventID", "")
    prov = fields.get("Provider", "")

    if ts or eid:
        line = f"[{ts}] EventID={eid} Provider={prov}"
        if data_parts:
            line += " | " + " ".join(data_parts[:5])
        return line.strip()
    return ""


def _score_quality(event_count: int) -> float:
    """Score quality based on event count."""
    if event_count == 0:
        return 0.0
    if event_count < 5:
        return 0.4
    return 0.8
