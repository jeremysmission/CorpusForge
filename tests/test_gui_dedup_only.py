"""Focused GUI regressions for dedup-only output and worker/status surfacing.

Plain-English summary for operators:
The GUI has a separate 'Dedup Only' mode that scans a source folder and
writes a canonical file list and a portable deduped copy, without
running the full pipeline. This file protects that mode plus the GUI's
status-bar text, the Save-Settings flow, and the pipeline-finished log
wording. If these tests fail, operators could see: wrong config path
in the status bar, a Stop button that lies about what got packaged,
the dedup-only run writing to the wrong output folder, or Save
Settings silently not saving.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["CORPUSFORGE_HEADLESS"] = "1"

from src.config.schema import load_config
from src.gui.app import CorpusForgeApp
from src.gui.dedup_only_panel import DedupOnlyPanel
from src.gui.launch_gui import DedupOnlyRunner, _save_gui_settings_override
from src.gui.safe_after import drain_ui_queue


@pytest.fixture(scope="module")
def root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_dedup_only_panel_passes_selected_output(root, tmp_path):
    """Protects against the dedup-only panel ignoring the operator's chosen output folder."""
    frame = ttk.LabelFrame(root, text="Dedup")
    frame.pack(fill=tk.BOTH, expand=True)
    captured = {}

    panel = DedupOnlyPanel(
        frame,
        root,
        on_dedup_only_start=lambda **kwargs: captured.update(kwargs),
        default_output=str(tmp_path / "dedup_out"),
    )
    panel.dedup_only_src_var.set(str(tmp_path / "source"))
    panel.dedup_only_out_var.set(str(tmp_path / "chosen_output"))

    panel._on_start_click()

    assert captured["source"] == str(tmp_path / "source")
    assert captured["output"] == str(tmp_path / "chosen_output")
    assert captured["copy_sources"] is True


def test_corpusforge_status_bar_shows_worker_count(root):
    """Protects the status bar — runtime config path, skip/defer file, and current worker count must be visible."""
    config = load_config()
    app = CorpusForgeApp(root, config=config, config_path="config/config.yaml")
    root.update_idletasks()
    assert app._status_labels["config"].cget("text") == "Runtime: config/config.yaml"
    assert "Skip/defer:" in app._status_labels["skip"].cget("text")
    assert "Pipeline workers:" in app._status_labels["workers"].cget("text")

    app.workers_var.set(20)
    app.update_worker_status(20)

    assert app._status_labels["workers"].cget("text") == "Pipeline workers: 20 logical threads"


def test_corpusforge_status_bar_defaults_to_live_runtime_config(root):
    """Protects the default status-bar text — even without an explicit config_path, GUI should show the live runtime config."""
    config = load_config()
    app = CorpusForgeApp(root, config=config)
    root.update_idletasks()
    assert app._status_labels["config"].cget("text") == "Runtime: config/config.yaml"


def test_save_settings_log_calls_out_live_runtime_config(root):
    """Protects the Save-Settings log — it must name the exact config file being written so operators are not guessing."""
    config = load_config()
    app = CorpusForgeApp(root, config=config, config_path="config/config.yaml")
    logs = []
    app._settings_panel._append_log = lambda message, level="INFO": logs.append((level, message))
    app._settings_panel._on_save_settings = lambda settings: None

    app._settings_panel._handle_save_settings()

    assert any("runtime config config/config.yaml" in message for _level, message in logs)


def test_pipeline_finished_progress_label_uses_work_total(root):
    """Protects the final progress label — shows 'X/X work files, Y discovered' so operator sees both dedup reduction and raw totals."""
    config = load_config()
    app = CorpusForgeApp(root, config=config)
    app.pipeline_finished({
        "files_found": 10,
        "files_after_dedup": 2,
        "files_parsed": 2,
        "files_skipped": 0,
        "files_failed": 0,
        "chunks_created": 5,
        "chunks_enriched": 0,
        "vectors_created": 5,
        "elapsed_seconds": 1.0,
        "skip_reasons": "",
    })

    assert app.progress_label.cget("text") == "Done (2/2 work files, 10 discovered)"


def test_pipeline_stop_ui_uses_safe_wording(root):
    """Protects the Stop button text and state — says 'Stop Safely' initially, 'Stopping...' during shutdown."""
    config = load_config()
    stop_calls = []
    app = CorpusForgeApp(root, config=config, on_stop=lambda: stop_calls.append("stop"))

    assert app.stop_btn.cget("text") == "Stop Safely"

    app._set_running(True)
    app._on_stop_click()

    assert stop_calls == ["stop"]
    assert app.stop_btn.cget("text") == "Stopping..."
    assert str(app.stop_btn.cget("state")) == str(tk.DISABLED)
    assert app._stats_panel._stat_labels["stage"].cget("text") == "Stopping"


def test_stats_panel_shows_chunk_rate_and_stage_mapping(root):
    """Protects the live stats panel — chunk rate is shown, stage labels map to operator-friendly text like 'Parse (CPU/IO)'."""
    config = load_config()
    app = CorpusForgeApp(root, config=config)

    app.update_stats({
        "files_found": 10,
        "files_after_dedup": 4,
        "files_parsed": 2,
        "files_skipped": 0,
        "files_failed": 0,
        "chunks_created": 80,
        "chunks_per_second": 22.5,
        "chunks_enriched": 0,
        "vectors_created": 0,
        "elapsed_seconds": 4.0,
        "skip_reasons": "",
    })
    app.update_stage_progress("parse", 2, 4, "alpha.txt | CPU/IO parse | 80 chunks | 22.5 chunks/sec")

    assert app._stats_panel._stat_labels["chunks_per_second"].cget("text") == "22.5"
    assert app._stats_panel._stat_labels["stage"].cget("text") == "Parse (CPU/IO)"


def test_stats_panel_stage_label_map_covers_all_stages(root):
    """Every stage emitted by Pipeline + launch_gui should map to an operator-friendly label.

    Protects against any pipeline stage showing up as a raw name like 'dedup' — the GUI must translate to a friendly label like 'Dedup (CPU/IO)'.
    """
    config = load_config()
    app = CorpusForgeApp(root, config=config)
    expected = {
        "discover": "Discover (CPU/IO)",
        "dedup": "Dedup (CPU/IO)",
        "parse": "Parse (CPU/IO)",
        "chunk": "Chunk (CPU)",
        "enrich": "Enrich (Ollama)",
        "embed": "Embed (GPU)",
        "extract": "Extract (CPU)",
        "export": "Export (CPU/IO)",
        "stopping": "Stopping",
    }
    for raw, friendly in expected.items():
        app.update_stage_progress(raw, 0, 1, "test detail")
        assert app._stats_panel._stat_labels["stage"].cget("text") == friendly, (
            f"stage {raw!r} should render as {friendly!r}"
        )


def test_pipeline_finished_log_distinguishes_packaged_from_empty_stop(root):
    """QA H2: pipeline_finished must NOT claim work was packaged on a stop that
    produced no export. The honest wording must say so, and a real export_dir
    must swap back to the 'packaged at ...' line.

    Protects truthful Stop messaging — operator must not see 'work packaged' when nothing was written; must see a real export path when one exists.
    """
    config = load_config()
    app = CorpusForgeApp(root, config=config)

    logs = []
    orig_append = app.append_log
    def capture(msg, level="INFO"):
        logs.append((level, msg))
        orig_append(msg, level)
    app.append_log = capture

    try:
        # Case 1: stopped with no export
        app._set_running(True)
        app.pipeline_finished({
            "files_found": 10, "files_after_dedup": 0, "files_parsed": 0,
            "files_skipped": 0, "files_failed": 0, "chunks_created": 0,
            "chunks_enriched": 0, "vectors_created": 0, "elapsed_seconds": 1.0,
            "export_dir": "", "stop_requested": True, "skip_reasons": "",
        })
        empty_log = next((m for lvl, m in logs if "stopped cleanly" in m), None)
        assert empty_log is not None
        assert "No export was written" in empty_log
        assert "packaged at" not in empty_log

        # Case 2: stopped WITH an export dir
        logs.clear()
        app._set_running(True)
        app.pipeline_finished({
            "files_found": 10, "files_after_dedup": 5, "files_parsed": 5,
            "files_skipped": 0, "files_failed": 0, "chunks_created": 50,
            "chunks_enriched": 0, "vectors_created": 50, "elapsed_seconds": 2.0,
            "export_dir": "C:/tmp/export_20260409_1234", "stop_requested": True,
            "skip_reasons": "",
        })
        packaged_log = next((m for lvl, m in logs if "stopped cleanly" in m), None)
        assert packaged_log is not None
        assert "packaged at C:/tmp/export_20260409_1234" in packaged_log
        assert "No export was written" not in packaged_log
    finally:
        app.append_log = orig_append


def test_stats_panel_chunks_per_second_blank_when_zero(root):
    """Protects against a misleading '0.0 chunks/sec' display — shown as '--' before any chunks exist."""
    config = load_config()
    app = CorpusForgeApp(root, config=config)
    app.update_stats({
        "files_found": 1, "files_after_dedup": 1, "files_parsed": 0,
        "files_skipped": 0, "files_failed": 0, "chunks_created": 0,
        "chunks_per_second": 0.0, "chunks_enriched": 0, "vectors_created": 0,
        "elapsed_seconds": 0.0, "skip_reasons": "",
    })
    assert app._stats_panel._stat_labels["chunks_per_second"].cget("text") == "--"


def test_save_settings_writes_config_yaml(tmp_path):
    """Protects Save Settings — operator's edits must actually land in config.yaml on disk."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("pipeline:\n  workers: 8\n", encoding="utf-8")

    saved_path = _save_gui_settings_override(config_file, {
        "pipeline": {"workers": 32},
        "hardware": {"embed_batch_size": 256},
    })

    assert saved_path == config_file
    saved_text = saved_path.read_text(encoding="utf-8")
    assert "workers: 32" in saved_text
    assert "embed_batch_size: 256" in saved_text


def test_precheck_button_passes_current_gui_settings(root, tmp_path):
    """Protects the precheck hand-off — clicking Run Precheck must pass the GUI's current values (not stale defaults) to the precheck tool."""
    config = load_config()
    captured = {}
    app = CorpusForgeApp(
        root,
        config=config,
        on_precheck=lambda **kwargs: captured.update(kwargs),
    )
    app.source_var.set(str(tmp_path / "source"))
    app.output_var.set(str(tmp_path / "output"))
    app.workers_var.set(32)
    app.ocr_var.set("auto")
    app.embed_var.set(True)
    app.enrich_var.set(False)
    app.extract_var.set(False)
    app.embed_batch_var.set(256)

    app._on_precheck_click()

    assert captured["source"] == str(tmp_path / "source")
    assert captured["output"] == str(tmp_path / "output")
    assert captured["settings"]["pipeline"]["workers"] == 32
    assert captured["settings"]["parse"]["ocr_mode"] == "auto"
    assert captured["settings"]["embed"]["enabled"] is True
    assert captured["settings"]["enrich"]["enabled"] is False
    assert captured["settings"]["extract"]["enabled"] is False
    assert captured["settings"]["hardware"]["embed_batch_size"] == 256


def test_dedup_only_runner_writes_selected_output_artifacts(root, tmp_path):
    """Protects the dedup-only run outputs — canonical list, dedup report, run report, and portable deduped copy must all be written."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "report.txt").write_text("same content")
    (source_dir / "report_1.txt").write_text("same content")
    (source_dir / "notes.txt").write_text("unique content")

    output_root = tmp_path / "dedup_output"
    config = load_config()
    config.paths.state_db = str(tmp_path / "state.sqlite3")

    class _AppStub:
        def __init__(self, root_widget):
            self.root = root_widget
            self.logs = []
            self.stats = []
            self.finished = None

        def append_log(self, message, level="INFO"):
            self.logs.append((level, message))

        def update_dedup_only_stats(self, stats):
            self.stats.append(stats)

        def dedup_only_finished(self, stats, message=""):
            self.finished = (stats, message)

    app = _AppStub(root)
    runner = DedupOnlyRunner(app, config)
    runner._run(str(source_dir), str(output_root))
    drain_ui_queue()
    root.update()

    assert app.finished is not None
    final_stats, final_message = app.finished
    assert "canonical_files.txt" in final_message
    assert "Deduped source copy:" in final_message
    assert final_stats["unique_files"] == 2
    assert final_stats["duplicates_found"] == 1

    dedup_runs = list(output_root.glob("dedup_only_*"))
    assert len(dedup_runs) == 1

    run_dir = dedup_runs[0]
    canonical = run_dir / "canonical_files.txt"
    report = run_dir / "dedup_report.json"
    run_report = run_dir / "run_report.txt"
    portable_copy = run_dir / "deduped_sources"

    assert canonical.exists()
    assert report.exists()
    assert run_report.exists()
    assert portable_copy.exists()

    canonical_lines = canonical.read_text(encoding="utf-8").splitlines()
    assert len(canonical_lines) == 2
    assert all(Path(line).is_absolute() for line in canonical_lines)
    assert (portable_copy / "report.txt").exists()
    assert (portable_copy / "notes.txt").exists()
    assert not (portable_copy / "report_1.txt").exists()


def test_dedup_only_runner_canonical_snapshot_includes_indexed_unchanged(root, tmp_path):
    """Protects the canonical list — files already indexed in state must still show up in the canonical snapshot on re-runs."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    report = source_dir / "report.txt"
    duplicate = source_dir / "report_1.txt"
    notes = source_dir / "notes.txt"
    report.write_text("same content")
    duplicate.write_text("same content")
    notes.write_text("unique content")

    output_root = tmp_path / "dedup_output"
    config = load_config()
    config.paths.state_db = str(tmp_path / "state.sqlite3")

    from src.download.hasher import Hasher
    hasher = Hasher(config.paths.state_db)
    hasher.update_hash(report, hasher.hash_file(report), status="indexed")
    hasher.update_hash(duplicate, hasher.hash_file(duplicate), status="duplicate")
    hasher.update_hash(notes, hasher.hash_file(notes), status="indexed")
    hasher.close()

    class _AppStub:
        def __init__(self, root_widget):
            self.root = root_widget
            self.logs = []
            self.stats = []
            self.finished = None

        def append_log(self, message, level="INFO"):
            self.logs.append((level, message))

        def update_dedup_only_stats(self, stats):
            self.stats.append(stats)

        def dedup_only_finished(self, stats, message=""):
            self.finished = (stats, message)

    app = _AppStub(root)
    runner = DedupOnlyRunner(app, config)
    runner._run(str(source_dir), str(output_root), copy_sources=False)
    drain_ui_queue()
    root.update()

    assert app.finished is not None
    final_stats, _message = app.finished
    assert final_stats["unique_files"] == 2

    run_dir = next(output_root.glob("dedup_only_*"))
    canonical_lines = (run_dir / "canonical_files.txt").read_text(encoding="utf-8").splitlines()
    assert len(canonical_lines) == 2
    assert str(report.resolve()) in canonical_lines
    assert str(notes.resolve()) in canonical_lines
