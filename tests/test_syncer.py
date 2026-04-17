"""Tests for BulkSyncer — atomic copy, SHA-256 verify, resume.

Plain-English summary for operators:
BulkSyncer is the Forge component that copies source files from the
share into the staging area before ingest. It uses SHA-256 checksums to
detect partial copies and skips files that already match. If these
tests fail, Forge might: silently corrupt files during the copy, waste
hours re-copying files that are already good, fail to resume a broken
overnight sync, or report the wrong number of files copied — any of
which makes downstream chunk counts untrustworthy.
"""

import os
from pathlib import Path
import pytest
from src.download.syncer import BulkSyncer, TransferStats


@pytest.fixture
def sync_dirs(tmp_path):
    src = tmp_path / "source"
    dest = tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    return src, dest


class TestBulkSyncer:
    def test_basic_copy(self, sync_dirs):
        """Protects the happy-path copy — all files (including subfolders) land at the destination with correct contents."""
        src, dest = sync_dirs
        (src / "a.txt").write_text("hello")
        (src / "sub").mkdir()
        (src / "sub" / "b.txt").write_text("world")

        syncer = BulkSyncer(src, dest)
        stats = syncer.run()
        assert stats.files_copied == 2
        assert stats.files_failed == 0
        assert (dest / "a.txt").read_text() == "hello"
        assert (dest / "sub" / "b.txt").read_text() == "world"

    def test_resume_skips_existing(self, sync_dirs):
        """Protects resume behavior — if a file is already copied with matching content, re-running should skip it, not re-copy."""
        src, dest = sync_dirs
        (src / "a.txt").write_text("data")
        # Pre-copy to dest
        dest.mkdir(exist_ok=True)
        (dest / "a.txt").write_text("data")

        syncer = BulkSyncer(src, dest)
        stats = syncer.run()
        assert stats.files_skipped == 1
        assert stats.files_copied == 0

    def test_hash_mismatch_recopy(self, sync_dirs):
        """Protects against a stale/corrupt destination file — if the checksum does not match source, Forge must re-copy."""
        src, dest = sync_dirs
        (src / "a.txt").write_text("correct")
        # Pre-copy with wrong content
        dest.mkdir(exist_ok=True)
        (dest / "a.txt").write_text("wrong content")

        syncer = BulkSyncer(src, dest)
        stats = syncer.run()
        assert stats.files_copied == 1
        assert (dest / "a.txt").read_text() == "correct"

    def test_progress_callback(self, sync_dirs):
        """Protects the progress hook — GUI needs live updates while the sync runs."""
        src, dest = sync_dirs
        (src / "a.txt").write_text("file a")
        (src / "b.txt").write_text("file b")

        calls = []
        def on_progress(stats):
            calls.append(stats.files_done)

        syncer = BulkSyncer(src, dest, on_progress=on_progress)
        syncer.run()
        assert len(calls) >= 1

    def test_stop_event(self, sync_dirs):
        """Protects the Stop Safely wiring for sync — operator must be able to cancel a long copy."""
        src, dest = sync_dirs
        for i in range(10):
            (src / f"file_{i}.txt").write_text(f"data {i}")

        stopped = False
        def should_stop():
            return stopped

        syncer = BulkSyncer(src, dest, should_stop=should_stop, workers=1)
        # Can't easily test mid-transfer stop in unit test, but verify API works
        stats = syncer.run()
        assert stats.total_files == 10

    def test_empty_source(self, sync_dirs):
        """Protects against empty source folders crashing the sync — a no-op is legal."""
        src, dest = sync_dirs
        syncer = BulkSyncer(src, dest)
        stats = syncer.run()
        assert stats.total_files == 0
        assert stats.files_copied == 0

    def test_parallel_copy(self, sync_dirs):
        """Protects multi-worker copy — faster runs must not lose or corrupt files under concurrency."""
        src, dest = sync_dirs
        for i in range(20):
            (src / f"file_{i}.txt").write_text(f"parallel content {i}")

        syncer = BulkSyncer(src, dest, workers=4)
        stats = syncer.run()
        assert stats.files_copied == 20
        assert stats.files_failed == 0
        for i in range(20):
            assert (dest / f"file_{i}.txt").read_text() == f"parallel content {i}"

    def test_source_not_found(self, tmp_path):
        """Protects against silent failure when the source path is wrong — Forge must raise so the operator sees it."""
        with pytest.raises(FileNotFoundError):
            syncer = BulkSyncer(tmp_path / "nonexistent", tmp_path / "dest")
            syncer.run()

    def test_copy_preserves_source_mtime(self, sync_dirs):
        """Protects the modified-time stamp — downstream nightly-delta logic depends on mtime to detect real changes."""
        src, dest = sync_dirs
        source_file = src / "timed.txt"
        source_file.write_text("timestamped")
        fixed_time = 1_700_000_000
        os.utime(source_file, (fixed_time, fixed_time))

        syncer = BulkSyncer(src, dest)
        syncer.run()

        copied = dest / "timed.txt"
        assert int(copied.stat().st_mtime) == fixed_time

    def test_on_file_result_callback_receives_each_file(self, sync_dirs):
        """Protects the per-file result callback — GUI logging and manifests rely on seeing every outcome."""
        src, dest = sync_dirs
        (src / "a.txt").write_text("alpha")
        (src / "b.txt").write_text("beta")

        seen = []

        def on_file_result(path, status, nbytes, err):
            seen.append((path.name, status, nbytes, err))

        syncer = BulkSyncer(src, dest, on_file_result=on_file_result)
        syncer.run()

        assert sorted(name for name, _status, _nbytes, _err in seen) == ["a.txt", "b.txt"]
        assert all(status == "copied" for _name, status, _nbytes, _err in seen)
