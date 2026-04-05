"""
Parse quality scorer — assigns 0.0-1.0 quality score to parsed text.

Simplified from V1 (src/core/source_quality.py). Detects:
  - Empty/near-empty text
  - Binary garbage (high non-printable ratio)
  - OCR artifacts (low alpha ratio)
  - Boilerplate/navigation fragments
"""

from __future__ import annotations

import re


def score_parse_quality(text: str, source_path: str = "") -> float:
    """
    Score parsed text quality from 0.0 to 1.0.

    Higher scores = more useful for retrieval.
    """
    if not text or not text.strip():
        return 0.0

    stripped = text.strip()
    sample = stripped[:2000]

    # Very short text
    if len(stripped) < 50:
        return 0.3

    # Binary garbage: high ratio of non-printable chars
    printable_count = sum(1 for c in sample if c.isprintable() or c in "\n\r\t")
    printable_ratio = printable_count / len(sample)
    if printable_ratio < 0.7:
        return 0.1

    # OCR garbage: low alpha ratio
    alpha_count = sum(1 for c in sample if c.isalpha())
    alpha_ratio = alpha_count / len(sample)
    if alpha_ratio < 0.2:
        return 0.3

    # Navigation boilerplate (HTML artifacts)
    boilerplate_markers = ["previous", "next", "navigation", "table of contents", "show source"]
    boilerplate_hits = sum(1 for m in boilerplate_markers if m in sample.lower())
    if boilerplate_hits >= 3:
        return 0.4

    # Good quality text
    if alpha_ratio > 0.5 and printable_ratio > 0.95:
        return 1.0

    return 0.8
