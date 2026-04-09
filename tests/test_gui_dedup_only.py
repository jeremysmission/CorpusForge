"""Focused GUI regressions for dedup-only output and worker/status surfacing."""

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


def test_corpusforge_status_bar_shows_worker_count(root):
    config = load_config()
    app = CorpusForgeApp(root, config=config)
    root.update_idletasks()
    assert "Pipeline workers:" in app._status_labels["workers"].cget("text")

    app.workers_var.set(20)
    app.update_worker_status(20)

    assert app._status_labels["workers"].cget("text") == "Pipeline workers: 20 logical threads"


def test_pipeline_finished_progress_label_uses_work_total(root):
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


def test_save_settings_writes_config_local_override(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("pipeline:\n  workers: 8\n", encoding="utf-8")

    saved_path = _save_gui_settings_override(config_file, {
        "pipeline": {"workers": 32},
        "hardware": {"embed_batch_size": 256},
    })

    assert saved_path == tmp_path / "config.local.yaml"
    assert config_file.read_text(encoding="utf-8") == "pipeline:\n  workers: 8\n"
    saved_text = saved_path.read_text(encoding="utf-8")
    assert "workers: 32" in saved_text
    assert "embed_batch_size: 256" in saved_text


def test_precheck_button_passes_current_gui_settings(root, tmp_path):
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
    assert final_stats["unique_files"] == 2
    assert final_stats["duplicates_found"] == 1

    dedup_runs = list(output_root.glob("dedup_only_*"))
    assert len(dedup_runs) == 1

    run_dir = dedup_runs[0]
    canonical = run_dir / "canonical_files.txt"
    report = run_dir / "dedup_report.json"
    run_report = run_dir / "run_report.txt"

    assert canonical.exists()
    assert report.exists()
    assert run_report.exists()

    canonical_lines = canonical.read_text(encoding="utf-8").splitlines()
    assert len(canonical_lines) == 2
    assert all(Path(line).is_absolute() for line in canonical_lines)
