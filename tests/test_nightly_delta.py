import json
import subprocess
import sys
from pathlib import Path

import yaml

from src.download.delta_tracker import NightlyDeltaTracker


def test_delta_tracker_reuses_hashed_and_canary_matches(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    canary = source_root / "nightly_canary_note.txt"
    normal = source_root / "report.txt"
    canary.write_text("canary content", encoding="utf-8")
    normal.write_text("report content", encoding="utf-8")

    tracker = NightlyDeltaTracker(str(tmp_path / "transfer_state.sqlite3"))
    try:
        first = tracker.scan(source_root=source_root, canary_globs=["*canary*"])
        assert first.delta_files == 2
        assert first.new_files == 2
        assert any("nightly_canary_note.txt" in match for match in first.canary_matches)

        tracker.mark_mirrored(canary)

        second = tracker.scan(source_root=source_root, canary_globs=["*canary*"])
        assert second.delta_files == 1
        assert second.resumed_hashed == 1
        assert second.unchanged_files == 1
        assert second.delta_paths == [str(normal.resolve())]
    finally:
        tracker.close()


def test_run_nightly_delta_preserves_original_source_path(tmp_path: Path) -> None:
    source_root = tmp_path / "igs_source"
    source_root.mkdir()
    mirror_root = tmp_path / "mirror"
    output_root = tmp_path / "output"
    manifest_root = tmp_path / "manifests"
    log_root = tmp_path / "logs"
    stop_file = tmp_path / "stop.flag"
    transfer_state = tmp_path / "transfer_state.sqlite3"
    pipeline_state = tmp_path / "pipeline_state.sqlite3"

    canary = source_root / "nightly_canary_report.txt"
    changed = source_root / "delta_report.txt"
    canary.write_text("Nightly canary report\n\nAlpha system normal.\n", encoding="utf-8")
    changed.write_text("Initial delta report\n\nBeta system nominal.\n", encoding="utf-8")

    config_path = tmp_path / "nightly_config.yaml"
    config_payload = {
        "paths": {
            "output_dir": str(output_root),
            "state_db": str(pipeline_state),
            "landing_zone": str(mirror_root),
            "skip_list": str((Path("C:/CorpusForge/config/config.yaml")).resolve()),
        },
        "embed": {"enabled": False},
        "enrich": {"enabled": False},
        "extract": {"enabled": False},
        "pipeline": {"workers": 1, "full_reindex": False},
        "nightly_delta": {
            "enabled": True,
            "source_root": str(source_root),
            "mirror_root": str(mirror_root),
            "transfer_state_db": str(transfer_state),
            "manifest_dir": str(manifest_root),
            "pipeline_output_dir": str(output_root),
            "pipeline_state_db": str(pipeline_state),
            "pipeline_log_dir": str(log_root),
            "stop_file": str(stop_file),
            "transfer_workers": 1,
            "canary_globs": ["*canary*"],
            "require_canary": False,
            "task_name": "CorpusForge Test Nightly Delta",
            "task_start_time": "02:00",
        },
    }
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    runner = Path("C:/CorpusForge/scripts/run_nightly_delta.py")
    result = subprocess.run(
        [sys.executable, str(runner), "--config", str(config_path), "--chunk-only"],
        capture_output=True,
        text=True,
        cwd="C:/CorpusForge",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    reports = sorted(manifest_root.glob("nightly_delta_report_*.json"))
    assert reports, "expected nightly delta report artifact"
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert report["scan"]["delta_files"] == 2
    assert report["pipeline"]["export_dir"]

    export_dir = Path(report["pipeline"]["export_dir"])
    chunks = [
        json.loads(line)
        for line in (export_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert chunks, "expected chunk output from nightly delta pipeline"
    assert all(chunk["source_path"].startswith(str(source_root)) for chunk in chunks)
    assert all(str(mirror_root) not in chunk["source_path"] for chunk in chunks)

    second = subprocess.run(
        [sys.executable, str(runner), "--config", str(config_path), "--chunk-only"],
        capture_output=True,
        text=True,
        cwd="C:/CorpusForge",
        timeout=120,
    )
    assert second.returncode == 0, second.stderr or second.stdout

    reports = sorted(manifest_root.glob("nightly_delta_report_*.json"))
    second_report = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert second_report["scan"]["delta_files"] == 0

    changed.write_text("Initial delta report\n\nBeta system adjusted.\n", encoding="utf-8")
    third = subprocess.run(
        [sys.executable, str(runner), "--config", str(config_path), "--chunk-only"],
        capture_output=True,
        text=True,
        cwd="C:/CorpusForge",
        timeout=120,
    )
    assert third.returncode == 0, third.stderr or third.stdout

    reports = sorted(manifest_root.glob("nightly_delta_report_*.json"))
    third_report = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert third_report["scan"]["delta_files"] == 1
