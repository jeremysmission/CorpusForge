"""Regression tests for document-family dedup decisions.

Plain-English summary for operators:
Beyond file-level dedup, Forge can also dedup at the 'document family'
level — e.g., the same report exported as both .docx and .pdf with
slightly different normalized text. This file protects that logic:
stem keys that strip 'Final', '_1' etc., text normalization that drops
page-number noise, similarity scoring, and the canonical-vs-duplicate
verdict. If these tests fail, operators could see the same document
appearing multiple times in the export under different formats.
"""

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
    """Protects the stem-key rule — 'Quarterly_Report_Final_1.pdf' must reduce to the same key as 'Quarterly Report.pdf'."""
    path = Path("Quarterly_Report_Final_1.pdf")
    assert build_stem_key(path) == "quarterly report"


def test_normalize_extracted_text_drops_page_noise() -> None:
    """Protects dedup text normalization — 'Page X of Y' headers and page numbers must be stripped before similarity scoring."""
    text = "Page 1 of 4\nAlpha Report\n123\nAlpha Report\nPage 2 of 4\nAlpha Report"
    normalized = normalize_extracted_text(text)
    assert "page 1 of 4" not in normalized
    assert normalized.splitlines() == ["alpha report", "alpha report", "alpha report"]


def test_score_similarity_handles_minor_line_drift() -> None:
    """Protects the similarity score — small extra lines (e.g., signature) must not drop a near-duplicate below the threshold."""
    left = "alpha report\npart ab-115 moved to birchwood\ncontact: maria"
    right = "alpha report\npart ab-115 moved to birchwood\ncontact: maria\nsigned by director"
    assert score_similarity(left, right) >= 0.9


def test_classify_same_stem_group_marks_cross_format_duplicate() -> None:
    """Protects the cross-format dedup verdict — Report.docx and Report.pdf with near-identical text must collapse to one canonical."""
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
