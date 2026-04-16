"""Regression tests for file-state and skip-accounting behavior."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.download.hasher import Hasher
from src.download.deduplicator import Deduplicator
from src.skip.skip_manager import SkipManager
from scripts.backfill_skipped_file_state import backfill_file_state


def test_skip_manager_records_deferred_file_in_state(tmp_path: Path) -> None:
    state_db = tmp_path / "file_state.sqlite3"
    skip_yaml = tmp_path / "skip_list.yaml"
    skip_yaml.write_text(
        "deferred_formats:\n"
        "  - ext: .dwg\n"
        "    reason: deferred test\n"
        "skip_conditions:\n"
        "  zero_byte: true\n",
        encoding="utf-8",
    )
    file_path = tmp_path / "sample.dwg"
    file_path.write_text("dwg content", encoding="utf-8")

    hasher = Hasher(str(state_db))
    try:
        manager = SkipManager(skip_yaml, hasher)
        skip, reason = manager.should_skip(file_path, file_path.stat().st_size)
        assert skip is True
        manager.record_skip(file_path, reason)
        row = hasher.get_state(file_path)
        assert row is not None
        assert row["status"] == "deferred"
    finally:
        hasher.close()


def test_skip_manager_marks_deferred_by_extension_not_reason(tmp_path: Path) -> None:
    state_db = tmp_path / "file_state.sqlite3"
    skip_yaml = tmp_path / "skip_list.yaml"
    skip_yaml.write_text(
        "deferred_formats:\n"
        "  - ext: .dwg\n"
        "    reason: CAD review lane\n"
        "skip_conditions:\n"
        "  zero_byte: true\n",
        encoding="utf-8",
    )
    file_path = tmp_path / "sample.dwg"
    file_path.write_text("dwg content", encoding="utf-8")

    hasher = Hasher(str(state_db))
    try:
        manager = SkipManager(skip_yaml, hasher)
        skip, reason = manager.should_skip(file_path, file_path.stat().st_size)
        assert skip is True
        manager.record_skip(file_path, reason)
        row = hasher.get_state(file_path)
        assert row is not None
        assert row["status"] == "deferred"
    finally:
        hasher.close()


def test_deduplicator_records_duplicate_state(tmp_path: Path) -> None:
    state_db = tmp_path / "file_state.sqlite3"
    first = tmp_path / "report.txt"
    dup = tmp_path / "report_1.txt"
    content = "same content"
    first.write_text(content, encoding="utf-8")
    dup.write_text(content, encoding="utf-8")

    hasher = Hasher(str(state_db))
    try:
        dedup = Deduplicator(hasher)
        work = dedup.filter_new_and_changed([first, dup])
        assert work == [first]
        row = hasher.get_state(dup)
        assert row is not None
        assert row["status"] == "duplicate"
    finally:
        hasher.close()


def test_deduplicator_persists_hashed_state_before_success(tmp_path: Path) -> None:
    state_db = tmp_path / "file_state.sqlite3"
    file_path = tmp_path / "report.txt"
    file_path.write_text("fresh content", encoding="utf-8")

    hasher = Hasher(str(state_db))
    try:
        dedup = Deduplicator(hasher)
        work = dedup.filter_new_and_changed([file_path])
        assert work == [file_path]
        row = hasher.get_state(file_path)
        assert row is not None
        assert row["status"] == "hashed"
    finally:
        hasher.close()


def test_deduplicator_reuses_hashed_state_after_interrupted_run(tmp_path: Path) -> None:
    state_db = tmp_path / "file_state.sqlite3"
    file_path = tmp_path / "report.txt"
    file_path.write_text("fresh content", encoding="utf-8")

    hasher = Hasher(str(state_db))
    try:
        first = Deduplicator(hasher)
        work = first.filter_new_and_changed([file_path])
        assert work == [file_path]
        row = hasher.get_state(file_path)
        assert row is not None
        assert row["status"] == "hashed"

        def _unexpected_rehash(_path: Path) -> str:
            raise AssertionError("hash_file should not run again for unchanged hashed work item")

        hasher.hash_file = _unexpected_rehash  # type: ignore[assignment]

        second = Deduplicator(hasher)
        resumed = second.filter_new_and_changed([file_path])
        assert resumed == [file_path]
    finally:
        hasher.close()


def test_deduplicator_retries_previously_deferred_file(tmp_path: Path) -> None:
    state_db = tmp_path / "file_state.sqlite3"
    file_path = tmp_path / "drawing.dxf"
    file_path.write_text("0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")

    hasher = Hasher(str(state_db))
    try:
        file_hash = hasher.hash_file(file_path)
        hasher.update_hash(file_path, file_hash, status="deferred")

        dedup = Deduplicator(hasher)
        work = dedup.filter_new_and_changed([file_path])
        assert work == [file_path]
    finally:
        hasher.close()


def test_backfill_script_dry_run_reports_without_writing(tmp_path: Path) -> None:
    state_db = tmp_path / "file_state.sqlite3"
    skip_yaml = tmp_path / "skip_list.yaml"
    skip_yaml.write_text(
        "deferred_formats:\n"
        "  - ext: .dwg\n"
        "    reason: deferred test\n"
        "skip_conditions:\n"
        "  zero_byte: true\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "paths:\n"
        "  output_dir: data/output\n"
        f"  state_db: {state_db.as_posix()}\n"
        f"  skip_list: {skip_yaml.as_posix()}\n"
        "parse:\n"
        "  defer_extensions: []\n",
        encoding="utf-8",
    )
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    (source_dir / "drawing.dwg").write_text("dwg content", encoding="utf-8")
    (source_dir / "mystery.zzz").write_text("unknown", encoding="utf-8")
    (source_dir / "keep.txt").write_text("parse me", encoding="utf-8")

    summary = backfill_file_state(
        input_path=source_dir,
        config_path=cfg,
        dry_run=True,
    )

    assert summary["mode"] == "DRY RUN"
    assert summary["backfilled"] == 2
    assert summary["parseable_skipped"] == 1
    assert summary["by_status"] == {"deferred": 1, "unsupported": 1}

    hasher = Hasher(str(state_db))
    try:
        assert hasher.get_all_tracked_paths() == []
    finally:
        hasher.close()
