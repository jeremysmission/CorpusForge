"""Regression tests for running the pipeline from an explicit input list."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_pipeline import _load_input_list


def test_load_input_list_reports_missing_and_duplicates(tmp_path: Path) -> None:
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
