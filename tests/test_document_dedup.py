"""Regression tests for document-family dedup decisions."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dedup.document_dedup import (
    FingerprintedDocument,
    build_stem_key,
    classify_same_stem_group,
    normalize_extracted_text,
    score_similarity,
)


def test_build_stem_key_strips_copy_suffixes() -> None:
    path = Path("Quarterly_Report_Final_1.pdf")
    assert build_stem_key(path) == "quarterly report"


def test_normalize_extracted_text_drops_page_noise() -> None:
    text = "Page 1 of 4\nAlpha Report\n123\nAlpha Report\nPage 2 of 4\nAlpha Report"
    normalized = normalize_extracted_text(text)
    assert "page 1 of 4" not in normalized
    assert normalized.splitlines() == ["alpha report", "alpha report", "alpha report"]


def test_score_similarity_handles_minor_line_drift() -> None:
    left = "alpha report\npart ab-115 moved to birchwood\ncontact: maria"
    right = "alpha report\npart ab-115 moved to birchwood\ncontact: maria\nsigned by director"
    assert score_similarity(left, right) >= 0.9


def test_classify_same_stem_group_marks_cross_format_duplicate() -> None:
    canonical = FingerprintedDocument(
        path=Path(r"C:\data\Report.docx"),
        ext=".docx",
        stem_key="report",
        parse_quality=1.0,
        raw_chars=120,
        normalized_chars=120,
        normalized_hash="hash-a",
        normalized_text=(
            "alpha report\npart ab-115 moved to birchwood\ncontact: maria\nstatus delivered"
        ),
    )
    duplicate = FingerprintedDocument(
        path=Path(r"C:\data\Report.pdf"),
        ext=".pdf",
        stem_key="report",
        parse_quality=0.9,
        raw_chars=136,
        normalized_chars=136,
        normalized_hash="hash-b",
        normalized_text=(
            "alpha report\npart ab-115 moved to birchwood\ncontact: maria\nstatus delivered\nsigned by director"
        ),
    )

    decisions = classify_same_stem_group(
        [duplicate, canonical],
        similarity_threshold=0.9,
        min_chars=20,
    )

    by_path = {row.path: row for row in decisions}
    assert by_path[str(canonical.path)].status == "canonical"
    assert by_path[str(duplicate.path)].status == "duplicate"
    assert by_path[str(duplicate.path)].canonical_path == str(canonical.path)
