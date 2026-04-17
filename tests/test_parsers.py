"""Smoke tests for parsers — every parser must handle basic input without crashing.

Plain-English summary for operators:
Forge's parser dispatcher hands each source file to the right parser
(PDF, DOCX, HTML, CSV, XML, YAML, etc.) and returns extracted text. This
file protects every parser from regressions. If these tests fail,
operators could see entire file types silently produce empty chunks, the
pipeline could crash on a file type it used to handle, or low-quality
placeholder text could replace real content in the shipped export.
"""
import tempfile
from pathlib import Path

import pytest

from src.parse.dispatcher import ParseDispatcher
from src.parse.parsers.pdf_parser import PdfParser


@pytest.fixture
def dispatcher():
    return ParseDispatcher(timeout_seconds=10, max_chars=100000)


# --- text formats ---

def test_parse_txt(dispatcher, tmp_path):
    """Protects the plain-text parser — the simplest case must always work."""
    f = tmp_path / "test.txt"
    f.write_text("Hello world. This is a test document.")
    doc = dispatcher.parse(f)
    assert "Hello world" in doc.text
    assert doc.parse_quality > 0


def test_parse_md(dispatcher, tmp_path):
    """Protects the Markdown parser from losing heading text."""
    f = tmp_path / "test.md"
    f.write_text("# Heading\n\nSome markdown content.")
    doc = dispatcher.parse(f)
    assert "Heading" in doc.text


def test_parse_csv(dispatcher, tmp_path):
    """Protects against CSV rows being dropped — tables are a core source for this pipeline."""
    f = tmp_path / "test.csv"
    f.write_text("name,value\nfoo,123\nbar,456")
    doc = dispatcher.parse(f)
    assert "foo" in doc.text
    assert "123" in doc.text


def test_parse_json(dispatcher, tmp_path):
    """Protects against JSON files ingesting as empty — keys and values must surface as text."""
    f = tmp_path / "test.json"
    f.write_text('{"key": "value", "number": 42}')
    doc = dispatcher.parse(f)
    assert "key" in doc.text or "value" in doc.text


def test_parse_xml(dispatcher, tmp_path):
    """Protects against XML content being stripped — element text must be preserved."""
    f = tmp_path / "test.xml"
    f.write_text('<?xml version="1.0"?><root><item>content</item></root>')
    doc = dispatcher.parse(f)
    assert "content" in doc.text


def test_parse_yaml_as_txt(dispatcher, tmp_path):
    """Protects against YAML files being silently skipped — they route through the text parser."""
    f = tmp_path / "test.yaml"
    f.write_text("key: value\nlist:\n  - item1\n  - item2")
    doc = dispatcher.parse(f)
    assert "key" in doc.text


def test_parse_html(dispatcher, tmp_path):
    """Protects against the HTML parser losing body text while stripping tags."""
    f = tmp_path / "test.html"
    f.write_text("<html><body><p>Hello HTML</p></body></html>")
    doc = dispatcher.parse(f)
    assert "Hello HTML" in doc.text


def test_parse_rtf(dispatcher, tmp_path):
    """Protects against RTF crashing the pipeline — the parser must at minimum not throw."""
    f = tmp_path / "test.rtf"
    f.write_text(r"{\rtf1\ansi Hello RTF}")
    doc = dispatcher.parse(f)
    # RTF parser should extract something or at least not crash
    assert doc is not None


# --- unsupported format ---

def test_unsupported_extension_returns_empty(dispatcher, tmp_path):
    """Protects against unknown file types silently producing chunks — unsupported must route to empty, not garbage."""
    f = tmp_path / "test.xyz123"
    f.write_text("unknown format")
    doc = dispatcher.parse(f)
    assert doc.text == ""
    assert doc.parse_quality == 0.0


# --- error handling ---

def test_missing_file_returns_empty(dispatcher, tmp_path):
    """Protects against a missing file (race condition) crashing the pipeline — must return empty, not throw."""
    f = tmp_path / "nonexistent.txt"
    doc = dispatcher.parse(f)
    assert doc is not None  # Should not crash


def test_empty_file_returns_empty(dispatcher, tmp_path):
    """Protects against zero-byte files producing fake chunks or crashing the parser."""
    f = tmp_path / "empty.txt"
    f.write_text("")
    doc = dispatcher.parse(f)
    assert doc.text == ""


# --- placeholder parser ---

def test_placeholder_dwg(dispatcher, tmp_path):
    """Protects the placeholder pattern for CAD files — Forge must tag them with a placeholder and low quality, not real text."""
    f = tmp_path / "drawing.dwg"
    f.write_bytes(b"\x00" * 100)
    doc = dispatcher.parse(f)
    assert "AutoCAD" in doc.text or "PLACEHOLDER" in doc.text
    assert doc.parse_quality < 0.5  # Low quality — placeholder only


def test_parse_pdf_docling_fallback_uses_docling_when_native_extractors_are_empty(tmp_path, monkeypatch):
    """Protects the PDF fallback chain — when pypdf/pdfplumber/OCR all return empty, Docling must run instead of shipping an empty chunk."""
    # The monkeypatch calls below stub out the native PDF extractors to
    # simulate a scanned PDF where none of the normal paths yield text,
    # then forces Docling to return known markdown so the test can prove
    # the fallback fired.
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4\n%fake\n")

    monkeypatch.setenv("HYBRIDRAG_DOCLING_MODE", "fallback")
    monkeypatch.setattr(PdfParser, "_try_pypdf", lambda self, path: "")
    monkeypatch.setattr(PdfParser, "_try_pdfplumber", lambda self, path: "")
    monkeypatch.setattr(PdfParser, "_try_ocr", lambda self, path: "")
    monkeypatch.setattr(
        "src.parse.parsers.pdf_parser.extract_with_docling",
        lambda path: "# Converted by Docling\n\nProgram status report",
    )

    doc = PdfParser().parse(f)
    assert "Converted by Docling" in doc.text
    assert doc.parse_quality > 0
