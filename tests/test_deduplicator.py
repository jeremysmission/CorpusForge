"""Tests for the Deduplicator.

Plain-English summary for operators:
The Deduplicator throws out duplicate files before they waste GPU time
in embedding. It catches two kinds of duplicates: (1) "_1", "_2" copy
suffixes that Windows creates, and (2) identical content under
different names, matched by SHA-256 hash. It also remembers what it
already indexed, so re-runs skip unchanged files. If these tests fail,
Forge could ship an export with massive duplication (V1's core
problem), re-embed the same files every night, or discard genuinely
different files that just happen to share a name pattern.
"""

import pytest

from src.download.hasher import Hasher
from src.download.deduplicator import Deduplicator


@pytest.fixture
def dedup_env(tmp_path):
    """Create a test environment with hasher and dedup instance."""
    db = str(tmp_path / "test_state.sqlite3")
    hasher = Hasher(db)
    dedup = Deduplicator(hasher)
    yield tmp_path, hasher, dedup
    hasher.close()


class TestSuffixDuplicate:
    """Test _1 suffix detection."""

    def test_basic_suffix_1(self, dedup_env):
        """Protects against 'Report_1.docx'-style Windows copy duplicates leaking into the export."""
        tmp, hasher, dedup = dedup_env
        original = tmp / "Report.docx"
        dup = tmp / "Report_1.docx"
        original.write_text("hello world")
        dup.write_text("hello world")

        result = dedup.filter_new_and_changed([original, dup])
        assert len(result) == 1
        assert result[0].name == "Report.docx"
        assert dedup.skipped_duplicate == 1

    def test_suffix_2(self, dedup_env):
        """Protects against '_2' and higher suffixes — dedup must catch them the same way as '_1'."""
        tmp, hasher, dedup = dedup_env
        original = tmp / "Manual.pdf"
        dup2 = tmp / "Manual_2.pdf"
        original.write_text("content")
        dup2.write_text("content")

        result = dedup.filter_new_and_changed([original, dup2])
        assert len(result) == 1
        assert result[0].name == "Manual.pdf"

    def test_suffix_different_content_kept(self, dedup_env):
        """Protects against over-deduping — if 'Data_1.csv' has genuinely different content, it must be kept."""
        tmp, hasher, dedup = dedup_env
        original = tmp / "Data.csv"
        different = tmp / "Data_1.csv"
        original.write_text("version A")
        different.write_text("version B, actually different")

        result = dedup.filter_new_and_changed([original, different])
        assert len(result) == 2

    def test_suffix_no_original_kept(self, dedup_env):
        """_1 file without matching original should not be skipped.

        Protects against discarding an only-copy file just because its name ends in '_1'.
        """
        tmp, hasher, dedup = dedup_env
        orphan = tmp / "Orphan_1.txt"
        orphan.write_text("no original exists")

        result = dedup.filter_new_and_changed([orphan])
        assert len(result) == 1


class TestContentHashDedup:
    """Test content-hash based duplicate detection."""

    def test_identical_files(self, dedup_env):
        """Protects hash-based dedup — two files with different names but identical content must collapse to one."""
        tmp, hasher, dedup = dedup_env
        a = tmp / "alpha.txt"
        b = tmp / "beta.txt"
        a.write_text("identical")
        b.write_text("identical")

        result = dedup.filter_new_and_changed([a, b])
        assert len(result) == 1
        assert dedup.skipped_duplicate == 1

    def test_different_files_kept(self, dedup_env):
        """Protects against over-aggressive dedup — genuinely distinct files must both survive."""
        tmp, hasher, dedup = dedup_env
        a = tmp / "one.txt"
        b = tmp / "two.txt"
        a.write_text("content A")
        b.write_text("content B")

        result = dedup.filter_new_and_changed([a, b])
        assert len(result) == 2
        assert dedup.skipped_duplicate == 0

    def test_three_copies_one_kept(self, dedup_env):
        """Protects against three-way duplicate files — only one canonical should survive and the other two counted as dupes."""
        tmp, hasher, dedup = dedup_env
        files = []
        for name in ["copy1.txt", "copy2.txt", "copy3.txt"]:
            f = tmp / name
            f.write_text("same same same")
            files.append(f)

        result = dedup.filter_new_and_changed(files)
        assert len(result) == 1
        assert dedup.skipped_duplicate == 2


class TestIncrementalDedup:
    """Test incremental processing (second run skips indexed files)."""

    def test_second_run_skips_indexed(self, dedup_env):
        """Protects resume — a second run on unchanged files must skip them, not re-embed."""
        tmp, hasher, dedup = dedup_env
        f = tmp / "stable.txt"
        f.write_text("stable content")

        result1 = dedup.filter_new_and_changed([f])
        assert len(result1) == 1
        dedup.mark_indexed(result1)

        dedup2 = Deduplicator(hasher)
        result2 = dedup2.filter_new_and_changed([f])
        assert len(result2) == 0
        assert dedup2.skipped_unchanged == 1

    def test_modified_file_reprocessed(self, dedup_env):
        """Protects against stale exports — when a file actually changes, re-runs must pick it up again."""
        tmp, hasher, dedup = dedup_env
        f = tmp / "changing.txt"
        f.write_text("version 1")

        result1 = dedup.filter_new_and_changed([f])
        dedup.mark_indexed(result1)

        import time
        time.sleep(0.1)
        f.write_text("version 2 - changed!")

        dedup2 = Deduplicator(hasher)
        result2 = dedup2.filter_new_and_changed([f])
        assert len(result2) == 1

    def test_duplicate_remembered_across_runs(self, dedup_env):
        """Protects dedup memory across runs — a known duplicate must stay flagged even after a restart."""
        tmp, hasher, dedup = dedup_env
        a = tmp / "orig.txt"
        b = tmp / "orig_1.txt"
        a.write_text("same")
        b.write_text("same")

        dedup.filter_new_and_changed([a, b])

        dedup2 = Deduplicator(hasher)
        dedup2.filter_new_and_changed([a, b])
        assert dedup2.skipped_duplicate >= 1


class TestProgressCallback:
    """Test that on_progress callback is invoked."""

    def test_callback_called(self, dedup_env):
        """Protects the progress hook — GUI and log need live dedup updates."""
        tmp, hasher, dedup = dedup_env
        f = tmp / "file.txt"
        f.write_text("data")

        calls = []

        def on_progress(scanned, total, current, dupes):
            calls.append((scanned, total, current, dupes))

        dedup.filter_new_and_changed([f], on_progress=on_progress)
        assert len(calls) >= 2

    def test_callback_reports_total(self, dedup_env):
        """Protects the progress-total counter — operator must see the correct total, not partial numbers."""
        tmp, hasher, dedup = dedup_env
        files = []
        for i in range(5):
            f = tmp / f"file_{i}.txt"
            f.write_text(f"unique content {i}")
            files.append(f)

        calls = []

        def on_progress(scanned, total, current, dupes):
            calls.append((scanned, total))

        dedup.filter_new_and_changed(files, on_progress=on_progress)
        assert calls[-1] == (5, 5)

    def test_final_progress_counts_tail_duplicate(self, dedup_env):
        """Protects the final progress snapshot — the last duplicate at the tail of the list must be counted."""
        tmp, hasher, dedup = dedup_env
        original = tmp / "report.txt"
        duplicate = tmp / "report_1.txt"
        original.write_text("same")
        duplicate.write_text("same")

        calls = []

        def on_progress(scanned, total, current, dupes):
            calls.append((scanned, total, current, dupes))

        dedup.filter_new_and_changed([original, duplicate], on_progress=on_progress)

        assert dedup.files_scanned == 2
        assert calls[-1][:2] == (2, 2)

    def test_final_progress_counts_tail_unchanged(self, dedup_env):
        """Protects the final progress snapshot — the last 'already indexed' file must still be counted in the total."""
        tmp, hasher, dedup = dedup_env
        original = tmp / "stable.txt"
        original.write_text("stable")

        first_pass = dedup.filter_new_and_changed([original])
        dedup.mark_indexed(first_pass)

        new_file = tmp / "new.txt"
        new_file.write_text("new")
        dedup2 = Deduplicator(hasher)
        calls = []

        def on_progress(scanned, total, current, dupes):
            calls.append((scanned, total, current, dupes))

        dedup2.filter_new_and_changed([new_file, original], on_progress=on_progress)

        assert dedup2.files_scanned == 2
        assert calls[-1][:2] == (2, 2)


class TestEdgeCases:
    """Edge cases: missing files, empty files, special names."""

    def test_missing_file_skipped(self, dedup_env):
        """Protects against a vanished file crashing the dedup loop — missing files must be silently dropped."""
        tmp, hasher, dedup = dedup_env
        missing = tmp / "ghost.txt"
        result = dedup.filter_new_and_changed([missing])
        assert len(result) == 0

    def test_empty_file(self, dedup_env):
        """Protects against empty files being dropped at dedup — the skip list, not the deduper, decides empty-file policy."""
        tmp, hasher, dedup = dedup_env
        f = tmp / "empty.txt"
        f.write_text("")
        result = dedup.filter_new_and_changed([f])
        assert len(result) == 1

    def test_empty_list(self, dedup_env):
        """Protects against an empty file-list crashing dedup — a zero-file run is legal."""
        _, _, dedup = dedup_env
        result = dedup.filter_new_and_changed([])
        assert result == []
