"""
Parse quality scorer -- rates how trustworthy a parsed file's text is.

Plain English: after a parser runs, we need a single number that says
"is this actually useful text, or is it junk?" This module produces a
score between 0.0 (garbage) and 1.0 (clean, readable text) based on
simple red flags:

  * Empty or nearly empty text -> probably nothing usable.
  * Lots of non-printable bytes -> probably binary that slipped through.
  * Very few letters for the length -> looks like bad OCR from a scan.
  * Lots of "Next / Previous / Table of Contents" markers -> HTML
    navigation junk, not real content.

The quality score is attached to each chunk as metadata so downstream
stages can filter, rank, or flag low-quality material during retrieval
and review.

Simplified from V1 (src/core/source_quality.py).
"""

from __future__ import annotations

import re


def score_parse_quality(text: str, source_path: str = "") -> float:
    """Give parsed text a 0.0-1.0 quality score. Higher means more useful."""
    if not text or not text.strip():
        return 0.0

    stripped = text.strip()
    # Only look at the first 2000 chars for speed; a file's opening is a
    # reliable sample of whether the whole thing looks like real text.
    sample = stripped[:2000]

    # Very short text
    if len(stripped) < 50:
        return 0.3

    # Binary garbage: high ratio of non-printable chars
    printable_count = sum(1 for c in sample if c.isprintable() or c in "\n\r\t")
    printable_ratio = printable_count / len(sample)
    if printable_ratio < 0.7:
        return 0.1

    # OCR garbage: low alpha ratio (scans that didn't resolve into letters)
    alpha_count = sum(1 for c in sample if c.isalpha())
    alpha_ratio = alpha_count / len(sample)
    if alpha_ratio < 0.2:
        return 0.3

    # Navigation boilerplate (HTML artifacts like "Previous / Next / TOC")
    boilerplate_markers = ["previous", "next", "navigation", "table of contents", "show source"]
    boilerplate_hits = sum(1 for m in boilerplate_markers if m in sample.lower())
    if boilerplate_hits >= 3:
        return 0.4

    # Good quality text
    if alpha_ratio > 0.5 and printable_ratio > 0.95:
        return 1.0

    return 0.8
