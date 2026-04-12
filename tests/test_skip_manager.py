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
        "image_asset_extensions": [
            ".jpg", ".jpeg", ".png", ".tif", ".tiff",
        ],
        "encrypted_filename_tokens": [
            "encrypted", "password-protected", "drm-protected",
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


def _make_skip_manager(tmp_path: Path, *, ocr_mode: str = "auto") -> SkipManager:
    skip_yaml = tmp_path / "skip_list.yaml"
    skip_yaml.write_text(yaml.dump({
        "deferred_formats": [
            {"ext": ".dwf", "reason": "Design Web Format"},
        ],
        "image_asset_extensions": [
            ".jpg", ".jpeg", ".png", ".tif", ".tiff",
        ],
        "encrypted_filename_tokens": [
            "encrypted", "password-protected", "drm-protected",
        ],
        "skip_conditions": {
            "encrypted": True,
            "zero_byte": True,
            "over_size_mb": 1,
            "temp_file_prefixes": ["~$"],
            "temp_file_extensions": [".tmp"],
        },
    }))
    hasher = Hasher(str(tmp_path / f"state_{ocr_mode}.sqlite3"))
    return SkipManager(str(skip_yaml), hasher, ocr_mode=ocr_mode)


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


def test_load_deferred_extension_map_from_config_yaml_skip_section(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(yaml.dump({
        "paths": {"skip_list": "config/config.yaml"},
        "skip": {
            "deferred_formats": [
                {"ext": ".sao", "reason": "deferred in config"},
            ],
        },
    }))
    m = load_deferred_extension_map(str(f))
    assert m == {".sao": "deferred in config"}


def test_load_missing_file():
    m = load_deferred_extension_map("/nonexistent.yaml")
    assert m == {}


# --- image-asset family (skip/defer hardening 2026-04-09) ---

def test_image_asset_skipped_when_ocr_mode_skip(tmp_path):
    """Run 6 evidence: 15,237 [IMAGE_METADATA] junk chunks happen because
    ocr_mode == 'skip' produces no real text. Hash/defer them instead."""
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    for name in ("photo.jpg", "scan.jpeg", "diagram.png", "slide.tif"):
        f = tmp_path / name
        f.write_bytes(b"binary image body")
        skip, reason = sm.should_skip(f, f.stat().st_size)
        assert skip is True, f"{name} should skip under ocr_mode=skip"
        assert "image asset" in reason
        assert "OCR disabled" in reason


def test_image_asset_not_skipped_when_ocr_mode_auto(tmp_path):
    """When Tesseract is available (ocr_mode='auto'), images must parse as
    normal — the skip rule must NOT kick in."""
    sm = _make_skip_manager(tmp_path, ocr_mode="auto")
    for name in ("photo.jpg", "diagram.png", "slide.tif"):
        f = tmp_path / name
        f.write_bytes(b"binary image body")
        skip, reason = sm.should_skip(f, f.stat().st_size)
        assert skip is False, (
            f"{name} must not skip under ocr_mode=auto, got reason={reason!r}"
        )


def test_image_asset_not_skipped_when_ocr_mode_force(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="force")
    f = tmp_path / "diagram.png"
    f.write_bytes(b"binary image body")
    skip, _reason = sm.should_skip(f, f.stat().st_size)
    assert skip is False


# --- encrypted-by-filename-cue (distinct from magic-byte class) ---

def test_encrypted_filename_cue_skipped(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    f = tmp_path / "contract_encrypted.pdf"
    f.write_bytes(b"%PDF-1.7\nnot actually encrypted but name cue fires")
    skip, reason = sm.should_skip(f, f.stat().st_size)
    assert skip is True
    assert "encrypted file (filename cue:" in reason
    assert "encrypted" in reason


def test_encrypted_filename_cue_password_protected_variant(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    f = tmp_path / "Budget_FY25_PASSWORD-PROTECTED.pdf"
    f.write_bytes(b"%PDF-1.7\n")
    skip, reason = sm.should_skip(f, f.stat().st_size)
    assert skip is True
    assert "password-protected" in reason


def test_encrypted_filename_cue_case_insensitive(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    f = tmp_path / "Report_DRM-Protected_v2.docx"
    f.write_bytes(b"PK\x03\x04not really a docx")
    skip, reason = sm.should_skip(f, f.stat().st_size)
    assert skip is True
    assert "drm-protected" in reason.lower()


def test_encrypted_filename_cue_no_false_positive_on_unrelated_names(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    f = tmp_path / "SecurityReview_Q3.pdf"  # contains "security" but not "encrypted"
    f.write_bytes(b"%PDF-1.7\nplain pdf body")
    skip, _reason = sm.should_skip(f, f.stat().st_size)
    assert skip is False


def test_encrypted_filename_cue_no_false_positive_on_unencrypted(tmp_path):
    """QA finding: naive substring match caught 'unencrypted_notes.pdf'.
    Boundary-anchored match must leave it alone."""
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    for name in (
        "unencrypted_notes.pdf",
        "UNENCRYPTED_FY25.pdf",
        "final_unencrypted.pdf",
        "Report-unencrypted-v2.pdf",
        "UnEncryptedArchive.zip",  # CamelCase: still alnum-adjacent → must not match
    ):
        f = tmp_path / name
        f.write_bytes(b"body")
        skip, reason = sm.should_skip(f, f.stat().st_size)
        assert skip is False, (
            f"{name}: must NOT match encrypted-filename cue (got reason={reason!r})"
        )


def test_encrypted_filename_cue_no_false_positive_on_encryption_policy(tmp_path):
    """'encryption' (the noun) must not match the 'encrypted' (the adjective) token."""
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    for name in (
        "encryption_policy.pdf",
        "EncryptionStandards.docx",
        "encryption-guide.pdf",
    ):
        f = tmp_path / name
        f.write_bytes(b"body")
        skip, reason = sm.should_skip(f, f.stat().st_size)
        assert skip is False, (
            f"{name}: 'encryption' must not match 'encrypted' token (got {reason!r})"
        )


def test_encrypted_filename_cue_matches_real_positives(tmp_path):
    """Round up every real positive form we care about."""
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    positives = [
        "contract_encrypted.pdf",
        "encrypted_budget.pdf",
        "Report.ENCRYPTED.v2.pdf",
        "ENCRYPTED-v2.pdf",
        "Budget_FY25_PASSWORD-PROTECTED.pdf",
        "Report_DRM-Protected_v2.docx",
        "draft encrypted.pdf",  # space boundary
    ]
    for name in positives:
        f = tmp_path / name
        f.write_bytes(b"body")
        skip, reason = sm.should_skip(f, f.stat().st_size)
        assert skip is True, (
            f"{name}: expected encrypted-filename cue to fire, got skip={skip} reason={reason!r}"
        )
        assert "filename cue:" in reason


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        # True positives
        ("contract_encrypted.pdf", True),
        ("encrypted_budget.pdf", True),
        ("Report.ENCRYPTED.v2.pdf", True),
        ("ENCRYPTED-v2.pdf", True),
        ("Budget_FY25_PASSWORD-PROTECTED.pdf", True),
        ("Report_DRM-Protected_v2.docx", True),
        # False positives the old substring rule would catch
        ("unencrypted_notes.pdf", False),
        ("UNENCRYPTED_FY25.pdf", False),
        ("final_unencrypted.pdf", False),
        ("encryption_policy.pdf", False),
        ("EncryptionStandards.docx", False),
        # Unrelated names
        ("SecurityReview_Q3.pdf", False),
        ("plain_report.pdf", False),
    ],
)
def test_encrypted_filename_cue_boundary_matrix(tmp_path, name, should_fire):
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    f = tmp_path / name
    f.write_bytes(b"body")
    skip, _reason = sm.should_skip(f, f.stat().st_size)
    assert skip is should_fire, f"{name}: expected skip={should_fire}, got {skip}"


def test_encrypted_filename_cue_distinct_from_magic_byte(tmp_path):
    """Two encrypted classes must show as distinct reasons in skip_manifest."""
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    # A file with a name cue but no magic-byte encryption
    f_name = tmp_path / "quote_encrypted.pdf"
    f_name.write_bytes(b"%PDF-1.7\nno encryption dictionary present")
    # A file with a magic-byte cue (OLE2 encrypted Office)
    f_magic = tmp_path / "innocent_name.docx"
    f_magic.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1EncryptedPackage")

    for fp in (f_name, f_magic):
        sm.record_skip(fp, sm.should_skip(fp, fp.stat().st_size)[1])
    reasons = sm.get_skip_manifest()["counts_by_reason"]
    # Expect both classes present as different keys
    name_cue_keys = [k for k in reasons if "filename cue" in k]
    magic_keys = [k for k in reasons if "magic bytes" in k]
    assert name_cue_keys, f"expected a filename-cue reason class in {reasons}"
    assert magic_keys, f"expected a magic-bytes reason class in {reasons}"


def test_encrypted_magic_bytes_preferred_over_filename_cue_when_both_match(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    f = tmp_path / "contract_encrypted.pdf"
    f.write_bytes(b"%PDF-1.7\n1 0 obj\n<< /Encrypt << /Filter /Standard >> >>\n")

    skip, reason = sm.should_skip(f, f.stat().st_size)

    assert skip is True
    assert reason == "encrypted file (magic bytes)"


def test_encrypted_overlap_against_live_runtime_config(tmp_path):
    """QA pass 3 regression: reproduce the overlap case against the LIVE
    `config/config.yaml`, not an isolated test fixture. Proves the in-tree
    config actually wires `skip.skip_conditions.encrypted = true` so the
    magic-byte check fires on overlap and wins over the filename cue."""
    from src.config.schema import load_config
    config = load_config("config/config.yaml")
    config_deferred = {
        ext: "Deferred by config for this run" for ext in config.parse.defer_extensions
    }
    hasher = Hasher(str(tmp_path / "live_overlap_state.sqlite3"))
    sm = SkipManager(
        config.paths.skip_list, hasher,
        extra_deferred_exts=config_deferred,
        ocr_mode=config.parse.ocr_mode,
    )

    # File has BOTH a filename cue ("encrypted") AND a magic-byte payload
    # (a %PDF header with an /Encrypt dictionary in the first 4 KB).
    f = tmp_path / "contract_encrypted.pdf"
    f.write_bytes(b"%PDF-1.7\n1 0 obj\n<< /Encrypt << /Filter /Standard >> >>\n")

    skip, reason = sm.should_skip(f, f.stat().st_size)
    assert skip is True
    assert reason == "encrypted file (magic bytes)", (
        f"live config overlap must prefer magic bytes, got reason={reason!r}"
    )

    # And the same filename WITHOUT a magic-byte payload still reports the
    # filename cue — proving the two classes stay distinguishable.
    f2 = tmp_path / "quote_encrypted.pdf"
    f2.write_bytes(b"%PDF-1.7\nno encryption dictionary present")
    skip2, reason2 = sm.should_skip(f2, f2.stat().st_size)
    assert skip2 is True
    assert reason2.startswith("encrypted file (filename cue:"), (
        f"no-magic case should fall through to filename cue, got reason={reason2!r}"
    )


# --- manifest visibility: image skips show up as their own reason class ---

def test_image_skip_visible_in_skip_manifest(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="skip")
    files = []
    for i in range(3):
        f = tmp_path / f"photo_{i}.jpg"
        f.write_bytes(b"binary image")
        files.append(f)
    for fp in files:
        skip, reason = sm.should_skip(fp, fp.stat().st_size)
        assert skip is True
        sm.record_skip(fp, reason)
    manifest = sm.get_skip_manifest()
    assert manifest["total_skipped"] == 3
    keys = list(manifest["counts_by_reason"].keys())
    assert any("image asset" in k for k in keys), keys
    # Every entry must record its SHA-256 so restart/resume stays intact
    for entry in manifest["files"]:
        assert entry["sha256"] and len(entry["sha256"]) == 64


def test_skip_manifest_includes_legacy_v2_aliases(tmp_path):
    sm = _make_skip_manager(tmp_path, ocr_mode="auto")
    files = []
    for i in range(2):
        f = tmp_path / f"drawing_{i}.dwf"
        f.write_text("defer me", encoding="utf-8")
        files.append(f)

    for fp in files:
        skip, reason = sm.should_skip(fp, fp.stat().st_size)
        assert skip is True
        sm.record_skip(fp, reason)

    manifest = sm.get_skip_manifest()
    assert manifest["count"] == 2
    assert len(manifest["skipped_files"]) == 2
    assert manifest["skipped_files"][0]["path"] == manifest["files"][0]["path"]
    assert manifest["deferred_formats"] == [
        {"extension": "dwf", "count": 2, "reason": "Design Web Format"},
    ]


# --- ocr_mode gate matrix (explicit grid) ---

@pytest.mark.parametrize(
    ("ocr_mode", "ext", "should_skip"),
    [
        ("skip", ".jpg", True),
        ("skip", ".png", True),
        ("skip", ".tiff", True),
        ("auto", ".jpg", False),
        ("auto", ".png", False),
        ("force", ".jpg", False),
        ("force", ".tiff", False),
    ],
)
def test_image_asset_gate_matrix(tmp_path, ocr_mode, ext, should_skip):
    sm = _make_skip_manager(tmp_path, ocr_mode=ocr_mode)
    f = tmp_path / f"asset{ext}"
    f.write_bytes(b"body")
    actual, _reason = sm.should_skip(f, f.stat().st_size)
    assert actual is should_skip, (
        f"ocr_mode={ocr_mode} ext={ext}: expected skip={should_skip}, got {actual}"
    )
