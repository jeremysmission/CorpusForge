"""Regression tests for corpus profiling summaries.

Plain-English summary for operators:
Before a full ingest, Forge can profile the source tree and give the
operator a human-readable summary: what file types are in there, how
many OCR sidecars look like junk, how many scan-named images, how many
filenames cue 'encrypted', and which subfolders look like duplicate
bundles. If these tests fail, operators could plan a run blind —
missing the signal that a big chunk of the corpus is duplicate
bundles or OCR garbage.
"""

from pathlib import Path

from src.analysis.corpus_profiler import build_markdown_report, profile_source_tree


def test_profile_source_tree_detects_sidecars_and_duplicate_folders(tmp_path: Path) -> None:
    """Protects the profiler's signal detection — sidecars, scan-named images, encrypted-named PDFs, and duplicate folder bundles must all be counted."""
    root = tmp_path / "source"
    root.mkdir()

    a = root / "bundle_a"
    b = root / "bundle_b"
    a.mkdir()
    b.mkdir()
    (a / "doc.pdf").write_text("pdf-a", encoding="utf-8")
    (a / "doc_djvu.txt").write_text("sidecar", encoding="utf-8")
    (b / "doc.pdf").write_text("pdf-a", encoding="utf-8")
    (b / "doc_djvu.txt").write_text("sidecar", encoding="utf-8")
    (root / "scan_001.jpeg").write_text("img", encoding="utf-8")
    (root / "manual_encrypted.pdf").write_text("enc", encoding="utf-8")

    report = profile_source_tree(root, top_n=10, min_duplicate_dir_files=2)

    assert report["total_files"] == 6
    assert report["extension_counts"][".pdf"] == 3
    assert report["signal_counts"]["ocr_sidecar_djvu_txt"] == 2
    assert report["signal_counts"]["scan_named_image"] == 1
    assert report["signal_counts"]["encrypted_pdf_name"] == 1
    assert report["duplicate_folder_signatures"]
    first_group = report["duplicate_folder_signatures"][0]
    assert first_group["folder_count"] == 2
    assert "bundle_a" in first_group["folders"]
    assert "bundle_b" in first_group["folders"]


def test_build_markdown_report_renders_duplicate_section(tmp_path: Path) -> None:
    """Protects the human-readable profile report — the markdown output must include the sections operators rely on for planning."""
    root = tmp_path / "source"
    root.mkdir()
    leaf = root / "engineering_docs"
    leaf.mkdir()
    (leaf / "diagram.drawio").write_text("x", encoding="utf-8")
    report = profile_source_tree(root, top_n=10, min_duplicate_dir_files=1)

    markdown = build_markdown_report(report, top_n=10)

    assert "# Source Corpus Profile" in markdown
    assert "Top Extensions" in markdown
    assert "Duplicate Recursive Folder Signatures" in markdown
