from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import Pipeline, RunStats


class _SkipManagerStub:
    def __init__(self, summary: str) -> None:
        self._summary = summary

    def get_reason_summary(self) -> str:
        return self._summary


def test_build_export_stats_finalizes_skip_reasons_and_elapsed() -> None:
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.skip_manager = _SkipManagerStub("2 Deferred by config for this run")

    stats = RunStats(files_skipped=2, chunks_created=5)
    start_time = time.time() - 1.25

    export_stats = Pipeline._build_export_stats(pipeline, stats, start_time)

    assert export_stats["skip_reasons"] == "2 Deferred by config for this run"
    assert export_stats["elapsed_seconds"] >= 1.0
    assert stats.skip_reasons == "2 Deferred by config for this run"
    assert stats.elapsed_seconds >= 1.0
