"""
PCAP parser -- extracts summary metadata from network captures.

Analyzes packet counts, protocol breakdown, IP addresses, and time range.
Ported from V1 (src/parsers/pcap_parser.py).
Dependencies: pip install dpkt (optional, graceful fallback).
"""

from __future__ import annotations

import logging
import socket
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)

_MAX_PACKETS = 10000


class PcapParser:
    """Parse PCAP/PCAPNG network capture files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            import dpkt
        except ImportError:
            logger.debug("dpkt not installed, cannot parse %s", path.name)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            with open(str(path), "rb") as f:
                try:
                    pcap = dpkt.pcap.Reader(f)
                except Exception:
                    f.seek(0)
                    try:
                        pcap = dpkt.pcapng.Reader(f)
                    except Exception as e:
                        logger.debug("Not a valid pcap %s: %s", path.name, e)
                        return ParsedDocument(
                            source_path=str(path),
                            text="",
                            parse_quality=0.0,
                            file_ext=path.suffix.lower(),
                            file_size=path.stat().st_size if path.exists() else 0,
                        )

                text, pkt_count = self._analyze(pcap, path)
        except Exception as e:
            logger.debug("PCAP parse error for %s: %s", path.name, e)
            pkt_count = 0

        quality = _score_quality(pkt_count)
        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )

    def _analyze(self, pcap, path: Path) -> tuple[str, int]:
        """Analyze packets and build summary text."""
        import dpkt

        parts: list[str] = [f"Network Capture: {path.name}"]
        pkt_count = 0
        protos: Counter = Counter()
        src_ips: Counter = Counter()
        dst_ips: Counter = Counter()
        ts_first = None
        ts_last = None

        for ts, buf in pcap:
            if pkt_count >= _MAX_PACKETS:
                break
            pkt_count += 1
            if ts_first is None:
                ts_first = ts
            ts_last = ts

            try:
                eth = dpkt.ethernet.Ethernet(buf)
                if isinstance(eth.data, dpkt.ip.IP):
                    ip = eth.data
                    src = socket.inet_ntoa(ip.src)
                    dst = socket.inet_ntoa(ip.dst)
                    src_ips[src] += 1
                    dst_ips[dst] += 1

                    if isinstance(ip.data, dpkt.tcp.TCP):
                        protos["TCP"] += 1
                    elif isinstance(ip.data, dpkt.udp.UDP):
                        protos["UDP"] += 1
                    elif isinstance(ip.data, dpkt.icmp.ICMP):
                        protos["ICMP"] += 1
                    else:
                        protos["Other IP"] += 1
                elif isinstance(eth.data, dpkt.ip6.IP6):
                    ip6 = eth.data
                    src = socket.inet_ntop(socket.AF_INET6, ip6.src)
                    dst = socket.inet_ntop(socket.AF_INET6, ip6.dst)
                    src_ips[src] += 1
                    dst_ips[dst] += 1

                    if isinstance(ip6.data, dpkt.tcp.TCP):
                        protos["TCP"] += 1
                    elif isinstance(ip6.data, dpkt.udp.UDP):
                        protos["UDP"] += 1
                    else:
                        protos["Other IPv6"] += 1
                else:
                    protos["Non-IP"] += 1
            except Exception:
                protos["Malformed"] += 1

        parts.append(f"Packets analyzed: {pkt_count:,}")

        if ts_first is not None and ts_last is not None:
            t1 = datetime.fromtimestamp(ts_first, tz=timezone.utc)
            t2 = datetime.fromtimestamp(ts_last, tz=timezone.utc)
            parts.append(f"Time range: {t1.isoformat()} to {t2.isoformat()}")

        if protos:
            parts.append("Protocols: " + ", ".join(
                f"{p}={c}" for p, c in protos.most_common(10)
            ))

        if src_ips:
            top_src = src_ips.most_common(10)
            parts.append("Top source IPs: " + ", ".join(
                f"{ip}({c})" for ip, c in top_src
            ))

        if dst_ips:
            top_dst = dst_ips.most_common(10)
            parts.append("Top dest IPs: " + ", ".join(
                f"{ip}({c})" for ip, c in top_dst
            ))

        return "\n".join(parts).strip(), pkt_count


def _score_quality(pkt_count: int) -> float:
    """Score quality based on packet count."""
    if pkt_count == 0:
        return 0.0
    if pkt_count < 10:
        return 0.4
    return 0.7  # Metadata-only, no full-text content
