"""Regression: deferred extensions inside archives must be skipped at extract time.

Sprint 6.6 leaked ~100K SAO chunks into the production export because
``parse.defer_extensions`` was only honored at the top filesystem layer.
``ArchiveParser`` extracted ZIP members and parsed them in-place, bypassing
the defer rule entirely. This test pins the fix so the leak cannot reappear.

Plain-English summary for operators:
The skip list tells Forge which file types to defer (skip for this run,
handle later). Before this fix, those rules worked for loose files on
disk but NOT for files hidden inside .zip or .tar.gz archives. Result:
a big production run quietly shipped ~100,000 chunks of deferred
content into the export. If these tests fail, Forge could again leak
deferred file types into an export the operator thought was clean.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from src.parse.parsers.archive_parser import ArchiveParser


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _write_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def _write_tar(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_zip_whole_archive_deferred_by_name(tmp_path: Path) -> None:
    """Sprint 6.6 production case: an archive named ``*.SAO.zip`` must be
    deferred entirely, even though its top-level extension is ``.zip``.

    Production member files are typically ``*.SAO.XML`` (extension is .XML,
    not .sao), so member-level extension matching alone would miss them.
    The archive's own basename has ``sao`` as a dot-segment, so the whole
    archive is rejected at parse() entry.
    """
    archive = _write_zip(
        tmp_path / "AS00Q_2015338141500.SAO.zip",
        {
            "AS00Q_2015338141500.SAO.XML": b"DELETE_ME ionogram XML payload",
            "AS00Q_2015338141500.SAO": b"DELETE_ME raw SAO payload",
        },
    )

    parser = ArchiveParser(deferred_exts={".sao", ".rsf"})
    doc = parser.parse(archive)

    assert doc.text == "", (
        "Whole-archive defer failed: SAO archive produced text. "
        f"Got text: {doc.text!r}"
    )
    assert doc.parse_quality == 0.0


def test_zip_deferred_member_inside_normal_archive_is_skipped(tmp_path: Path) -> None:
    """A SAO-named member inside a normally-named archive must be skipped
    while sibling allowed members still parse.

    Note: matching is segment-based, so both ``foo.SAO`` (token at end)
    and ``foo.SAO.XML`` (token mid-name) are caught.
    """
    archive = _write_zip(
        tmp_path / "mixed_bundle.zip",
        {
            "report.SAO.XML": b"DELETE_ME sao xml payload",
            "raw.SAO": b"DELETE_ME raw sao payload",
            "notes.txt": b"KEEP_ME real document content",
        },
    )

    parser = ArchiveParser(deferred_exts={".sao", ".rsf"})
    doc = parser.parse(archive)

    assert "DELETE_ME" not in doc.text, (
        "Member-level defer failed: SAO content leaked. "
        f"Got text: {doc.text!r}"
    )
    assert "KEEP_ME" in doc.text, (
        "Allowed .txt member should still be parsed. "
        f"Got text: {doc.text!r}"
    )


def test_zip_without_defer_still_parses_everything(tmp_path: Path) -> None:
    """Backward compat: with no defer set, all members parse as before."""
    archive = _write_zip(
        tmp_path / "mixed.zip",
        {
            "data.sao": b"sao content alpha",
            "notes.txt": b"text content beta",
        },
    )

    parser = ArchiveParser()  # no deferred_exts
    doc = parser.parse(archive)

    assert "alpha" in doc.text
    assert "beta" in doc.text


def test_zip_defer_does_not_over_match_substrings(tmp_path: Path) -> None:
    """Segment-based defer must NOT match substrings inside a single segment.

    The token ``sao`` is a defer entry. ``report_sao.log`` and ``bigsao.txt``
    have ``sao`` as part of a single segment, not as a dot-segment of their
    own — they must still be parsed. ``foo.SAO.zip`` and ``foo.SAO.XML``
    have ``sao`` AS a dot-segment and must be deferred.
    """
    archive = _write_zip(
        tmp_path / "edge.zip",
        {
            "real.sao": b"sao must be excluded",
            "report.sao.xml": b"sao xml must be excluded",
            "report_sao.log": b"sao-named log must be kept",
            "bigsao.txt": b"bigsao filename must be kept",
            "doc.txt": b"plain text must be kept",
        },
    )

    parser = ArchiveParser(deferred_exts={".sao"})
    doc = parser.parse(archive)

    # Excluded
    assert "sao must be excluded" not in doc.text
    assert "sao xml must be excluded" not in doc.text
    # Kept
    assert "sao-named log must be kept" in doc.text
    assert "bigsao filename must be kept" in doc.text
    assert "plain text must be kept" in doc.text


def test_zip_defer_normalizes_extension_format(tmp_path: Path) -> None:
    """Deferred ext list accepts ``sao`` (no dot) and ``.SAO`` (uppercase)."""
    archive = _write_zip(
        tmp_path / "case.zip",
        {
            "upper.SAO": b"upper case SAO must be skipped",
            "lower.sao": b"lower case sao must be skipped",
            "keep.txt": b"keep this",
        },
    )

    parser = ArchiveParser(deferred_exts={"sao"})  # no leading dot
    doc = parser.parse(archive)

    assert "must be skipped" not in doc.text
    assert "keep this" in doc.text


def test_tar_gz_deferred_member_is_skipped(tmp_path: Path) -> None:
    """Same defer policy applies to tar/tgz archives."""
    archive = _write_tar(
        tmp_path / "bundle.tar.gz",
        {
            "ionogram_a.rsf": b"DELETE_ME rsf content",
            "summary.txt": b"KEEP_ME summary",
        },
    )

    parser = ArchiveParser(deferred_exts={".rsf"})
    doc = parser.parse(archive)

    assert "DELETE_ME" not in doc.text
    assert "KEEP_ME" in doc.text


def test_dispatcher_propagates_defer_to_archive(tmp_path: Path) -> None:
    """Smoke test: building the parser map with extra_deferred_exts must
    instantiate ArchiveParser with that defer set, so the leak fix flows
    end-to-end through the production code path (not just direct construction).
    """
    from src.parse.dispatcher import _build_parser_map, reset_parser_map

    reset_parser_map()
    parser_map = _build_parser_map(
        skip_list_path="config/skip_list.yaml",
        extra_deferred_exts={".sao", ".rsf"},
    )
    archive = parser_map[".zip"]
    assert isinstance(archive, ArchiveParser)
    assert ".sao" in archive._deferred_exts
    assert ".rsf" in archive._deferred_exts
    assert "sao" in archive._deferred_tokens
    assert "rsf" in archive._deferred_tokens

    # End-to-end through the dispatcher's ArchiveParser instance:
    # an archive whose own name has ``.SAO.`` as a dot-segment is fully
    # deferred. This is the exact production case Run 5 leaked through.
    archive_path = _write_zip(
        tmp_path / "AS00Q_via_dispatcher.SAO.zip",
        {
            "AS00Q_via_dispatcher.SAO.XML": b"DELETE_ME ionogram payload",
        },
    )
    doc = archive.parse(archive_path)
    assert doc.text == ""
    assert doc.parse_quality == 0.0

    reset_parser_map()
