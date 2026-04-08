"""Smoke tests for parsers — every parser must handle basic input without crashing."""
import tempfile
from pathlib import Path

import pytest

from src.parse.dispatcher import ParseDispatcher


@pytest.fixture
def dispatcher():
    return ParseDispatcher(timeout_seconds=10, max_chars=100000)


# --- text formats ---

def test_parse_txt(dispatcher, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello world. This is a test document.")
    doc = dispatcher.parse(f)
    assert "Hello world" in doc.text
    assert doc.parse_quality > 0


def test_parse_md(dispatcher, tmp_path):
    f = tmp_path / "test.md"
    f.write_text("# Heading\n\nSome markdown content.")
    doc = dispatcher.parse(f)
    assert "Heading" in doc.text


def test_parse_csv(dispatcher, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("name,value\nfoo,123\nbar,456")
    doc = dispatcher.parse(f)
    assert "foo" in doc.text
    assert "123" in doc.text


def test_parse_json(dispatcher, tmp_path):
    f = tmp_path / "test.json"
    f.write_text('{"key": "value", "number": 42}')
    doc = dispatcher.parse(f)
    assert "key" in doc.text or "value" in doc.text


def test_parse_xml(dispatcher, tmp_path):
    f = tmp_path / "test.xml"
    f.write_text('<?xml version="1.0"?><root><item>content</item></root>')
    doc = dispatcher.parse(f)
    assert "content" in doc.text


def test_parse_yaml_as_txt(dispatcher, tmp_path):
    f = tmp_path / "test.yaml"
    f.write_text("key: value\nlist:\n  - item1\n  - item2")
    doc = dispatcher.parse(f)
    assert "key" in doc.text


def test_parse_html(dispatcher, tmp_path):
    f = tmp_path / "test.html"
    f.write_text("<html><body><p>Hello HTML</p></body></html>")
    doc = dispatcher.parse(f)
    assert "Hello HTML" in doc.text


def test_parse_rtf(dispatcher, tmp_path):
    f = tmp_path / "test.rtf"
    f.write_text(r"{\rtf1\ansi Hello RTF}")
    doc = dispatcher.parse(f)
    # RTF parser should extract something or at least not crash
    assert doc is not None


# --- unsupported format ---

def test_unsupported_extension_returns_empty(dispatcher, tmp_path):
    f = tmp_path / "test.xyz123"
    f.write_text("unknown format")
    doc = dispatcher.parse(f)
    assert doc.text == ""
    assert doc.parse_quality == 0.0


# --- error handling ---

def test_missing_file_returns_empty(dispatcher, tmp_path):
    f = tmp_path / "nonexistent.txt"
    doc = dispatcher.parse(f)
    assert doc is not None  # Should not crash


def test_empty_file_returns_empty(dispatcher, tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    doc = dispatcher.parse(f)
    assert doc.text == ""


# --- placeholder parser ---

def test_placeholder_dwg(dispatcher, tmp_path):
    f = tmp_path / "drawing.dwg"
    f.write_bytes(b"\x00" * 100)
    doc = dispatcher.parse(f)
    assert "AutoCAD" in doc.text or "PLACEHOLDER" in doc.text
    assert doc.parse_quality < 0.5  # Low quality — placeholder only
