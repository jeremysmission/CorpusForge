from pathlib import Path

from src.analysis.corpus_profiler import build_markdown_report, profile_source_tree


def test_profile_source_tree_detects_sidecars_and_duplicate_folders(tmp_path: Path) -> None:
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
