"""Tests for SkipManager — sidecar filter, deferred formats, skip conditions."""
import tempfile
from pathlib import Path

import pytest
import yaml

from src.skip.skip_manager import (
    SkipManager, load_deferred_extension_map, load_placeholder_format_map,
)
from src.download.hasher import Hasher


@pytest.fixture
def skip_env(tmp_path):
    """Create a temp skip_list.yaml and state DB for testing."""
    skip_yaml = tmp_path / "skip_list.yaml"
    skip_yaml.write_text(yaml.dump({
        "deferred_formats": [
            {"ext": ".dwf", "reason": "Design Web Format"},
        ],
        "placeholder_formats": [
            {"ext": ".dwg", "reason": "AutoCAD binary"},
            {"ext": ".prt", "reason": "SolidWorks Part"},
        ],
        "ocr_sidecar_suffixes": [
            "_djvu.xml", "_hocr.html", "_meta.xml", "_ocr.pdf",
        ],
        "skip_conditions": {
            "encrypted": True,
            "zero_byte": True,
            "over_size_mb": 1,
            "temp_file_prefixes": ["~$"],
            "temp_file_extensions": [".tmp"],
        },
    }))
    db_path = str(tmp_path / "state.sqlite3")
    hasher = Hasher(db_path)
    sm = SkipManager(str(skip_yaml), hasher)
    return sm, tmp_path


# --- sidecar filter ---

def test_sidecar_djvu_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "report_djvu.xml"
    f.write_text("junk")
    skip, reason = sm.should_skip(f, f.stat().st_size)
    assert skip is True
    assert "_djvu.xml" in reason


def test_sidecar_hocr_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "scan_hocr.html"
    f.write_text("junk")
    skip, _ = sm.should_skip(f, f.stat().st_size)
    assert skip is True


def test_sidecar_ocr_pdf_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "document_ocr.pdf"
    f.write_text("junk")
    skip, _ = sm.should_skip(f, f.stat().st_size)
    assert skip is True


def test_real_pdf_not_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "actual_report.pdf"
    f.write_text("real content")
    skip, _ = sm.should_skip(f, f.stat().st_size)
    assert skip is False


def test_real_xml_not_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "config.xml"
    f.write_text("<config/>")
    skip, _ = sm.should_skip(f, f.stat().st_size)
    assert skip is False


# --- deferred formats ---

def test_deferred_format_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "drawing.dwf"
    f.write_text("binary")
    skip, reason = sm.should_skip(f, f.stat().st_size)
    assert skip is True
    assert "Design Web Format" in reason


# --- skip conditions ---

def test_zero_byte_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "empty.txt"
    f.write_text("")
    skip, _ = sm.should_skip(f, 0)
    assert skip is True


def test_temp_prefix_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "~$document.docx"
    f.write_text("temp")
    skip, _ = sm.should_skip(f, f.stat().st_size)
    assert skip is True


def test_temp_extension_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "data.tmp"
    f.write_text("temp")
    skip, _ = sm.should_skip(f, f.stat().st_size)
    assert skip is True


def test_oversize_skipped(skip_env):
    sm, tmp = skip_env
    f = tmp / "huge.bin"
    f.write_text("x")
    # Fake a 2MB file size (over the 1MB limit)
    skip, _ = sm.should_skip(f, 2 * 1024 * 1024)
    assert skip is True


def test_normal_file_passes(skip_env):
    sm, tmp = skip_env
    f = tmp / "report.docx"
    f.write_text("content")
    skip, _ = sm.should_skip(f, f.stat().st_size)
    assert skip is False


# --- loader functions ---

def test_load_deferred_extension_map(tmp_path):
    f = tmp_path / "skip.yaml"
    f.write_text(yaml.dump({
        "deferred_formats": [
            {"ext": ".dwf", "reason": "test"},
            {"ext": "xyz", "reason": "no dot"},
        ],
    }))
    m = load_deferred_extension_map(str(f))
    assert ".dwf" in m
    assert ".xyz" in m  # auto-prepends dot


def test_load_placeholder_format_map(tmp_path):
    f = tmp_path / "skip.yaml"
    f.write_text(yaml.dump({
        "placeholder_formats": [
            {"ext": ".dwg", "reason": "AutoCAD"},
        ],
    }))
    m = load_placeholder_format_map(str(f))
    assert ".dwg" in m


def test_load_missing_file():
    m = load_deferred_extension_map("/nonexistent.yaml")
    assert m == {}
