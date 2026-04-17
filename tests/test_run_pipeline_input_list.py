"""Regression tests for running the pipeline from an explicit input list.

Plain-English summary for operators:
Instead of scanning a folder, Forge can accept a canonical_files.txt
and only ingest those specific paths. This file protects that loader:
duplicates are counted, missing files are reported by extension,
comment/blank lines are ignored. If these tests fail, operators could
see silent drops (missing files not reported) or double-ingestion
(duplicates not de-duped).
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_pipeline import _load_input_list


def test_load_input_list_reports_missing_and_duplicates(tmp_path: Path) -> None:
    """Protects the explicit-list loader — duplicates counted, missing files bucketed by extension, comments/blanks ignored."""
    existing = tmp_path / "keep.txt"
    existing.write_text("hello", encoding="utf-8")
    missing = tmp_path / "missing.pdf"

    input_list = tmp_path / "canonical_files.txt"
    input_list.write_text(
        "\n".join(
            [
                str(existing),
                str(existing),
                str(missing),
                "# comment",
                "",
            ]
        ),
        encoding="utf-8",
    )

    files, missing_counts, duplicate_entries = _load_input_list(input_list)

    assert files == [existing]
    assert missing_counts == {".pdf": 1}
    assert duplicate_entries == 1
