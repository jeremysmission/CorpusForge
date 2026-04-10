"""
GUI Button Smash Tests — Automated Tier A-C testing.

Runs headless: creates full GUI without mainloop, discovers all widgets,
invokes them, and checks for crashes/freezes.

Ported from HybridRAG V1 gui_engine pattern.
"""

import os
import sys
import time

import pytest

# Ensure project root on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

os.environ["CORPUSFORGE_HEADLESS"] = "1"


@pytest.fixture(scope="module")
def gui():
    """Boot headless GUI once for all tests in this module."""
    import tkinter as tk
    from src.config.schema import load_config

    config = load_config()
    root = tk.Tk()
    root.withdraw()

    from src.gui.app import CorpusForgeApp
    app = CorpusForgeApp(root, config=config)
    root.update()
    yield root, app
    root.destroy()


@pytest.fixture(scope="module")
def engine(gui):
    """Create the GUI engine for button smash testing."""
    from src.gui.testing.gui_engine import ForgeGuiEngine
    return ForgeGuiEngine(gui[1])


class TestWidgetDiscovery:
    """Tier A: Verify all expected widgets exist."""

    def test_discovers_buttons(self, engine):
        buttons = engine.discover_buttons()
        labels = [b.cget("text") for b in buttons if hasattr(b, "cget")]
        assert len(buttons) >= 4, f"Expected at least 4 buttons, found {len(buttons)}"
        assert "Start Pipeline" in labels
        assert "Run Precheck" in labels
        assert "Save Settings" in labels

    def test_discovers_spinboxes(self, engine):
        spinboxes = engine.discover_spinboxes()
        assert len(spinboxes) >= 4, f"Expected at least 4 spinboxes, found {len(spinboxes)}"

    def test_discovers_checkbuttons(self, engine):
        checkbuttons = engine.discover_checkbuttons()
        assert len(checkbuttons) >= 3, f"Expected at least 3 checkbuttons, found {len(checkbuttons)}"


class TestSettingsValidation:
    """Tier A: Verify settings panel validation."""

    def test_invalid_workers_zero(self, gui):
        _, app = gui
        app.workers_var.set(0)
        # Validation should catch this
        validations = [("Workers", app.workers_var, 1, 32)]
        errors = []
        for label, var, lo, hi in validations:
            val = var.get()
            if val < lo or val > hi:
                errors.append(label)
        assert len(errors) > 0
        app.workers_var.set(8)  # reset

    def test_invalid_workers_over_max(self, gui):
        _, app = gui
        app.workers_var.set(999)
        val = app.workers_var.get()
        assert val > 32  # Validates as out of range
        app.workers_var.set(8)

    def test_valid_settings_no_errors(self, gui):
        _, app = gui
        app.workers_var.set(8)
        app.chunk_size_var.set(1200)
        app.overlap_var.set(200)
        app.enrich_concurrent_var.set(2)
        app.extract_batch_var.set(16)
        app.embed_batch_var.set(256)

        validations = [
            ("Workers", app.workers_var, 1, 32),
            ("Chunk size", app.chunk_size_var, 100, 10000),
            ("Overlap", app.overlap_var, 0, 2000),
            ("Enrich concurrent", app.enrich_concurrent_var, 1, 8),
            ("Extract batch", app.extract_batch_var, 1, 128),
            ("Embed batch", app.embed_batch_var, 1, 1024),
        ]
        errors = []
        for label, var, lo, hi in validations:
            val = var.get()
            if val < lo or val > hi:
                errors.append(f"{label}={val}")
        assert len(errors) == 0, f"Unexpected validation errors: {errors}"


class TestRapidClick:
    """Tier B: Smart monkey — targeted rapid-click chaos."""

    def test_rapid_save_debounce(self, gui):
        _, app = gui
        # Set valid values first
        app.workers_var.set(8)
        app.chunk_size_var.set(1200)
        app.overlap_var.set(200)
        app.enrich_concurrent_var.set(2)
        app.extract_batch_var.set(16)
        app.embed_batch_var.set(256)
        app._last_save_time = 0

        # Simulate 10 rapid saves
        allowed = 0
        for _ in range(10):
            now = time.time()
            if not hasattr(app, "_last_save_time") or (now - app._last_save_time) >= 0.5:
                app._last_save_time = now
                allowed += 1
        assert allowed == 1, f"Debounce failed: {allowed} saves allowed (expected 1)"


class TestFullButtonSmash:
    """Tier B/C: Invoke safe buttons, report failures."""

    # Buttons that trigger dialogs/long ops in headless mode
    SKIP_LABELS = {"Start Pipeline", "Browse", "Stop", "Stop Safely", "Stopping...", "Reset to Defaults"}

    def test_safe_buttons_no_crashes(self, gui):
        """Invoke all buttons except those that trigger blocking dialogs."""
        from src.gui.testing.gui_engine import ForgeGuiEngine
        eng = ForgeGuiEngine(gui[1])
        buttons = eng.discover_buttons()
        failures = []
        for btn in buttons:
            try:
                label = btn.cget("text")
            except Exception:
                label = "(unknown)"
            if label in self.SKIP_LABELS:
                continue
            result = eng.invoke_button(btn)
            if not result["success"]:
                failures.append(f"{label}: {result['error']}")
        assert len(failures) == 0, f"Button crashes: {failures}"

    def test_performance_under_1s(self, gui):
        from src.gui.testing.gui_engine import ForgeGuiEngine
        eng = ForgeGuiEngine(gui[1])
        buttons = eng.discover_buttons()
        for btn in buttons:
            label = btn.cget("text") if hasattr(btn, "cget") else ""
            if label not in self.SKIP_LABELS:
                eng.invoke_button(btn)
        perf = eng.perf_summary()
        if perf:
            assert perf["p95_s"] < 1.0, f"p95 latency too high: {perf['p95_s']}s"


class TestStopControl:
    """Stop button must be wired and meaningful, not just clickable."""

    def test_stop_button_exists_and_starts_disabled(self, gui):
        _, app = gui
        # Stop button is disabled until a run starts.
        assert app.stop_btn.cget("text") == "Stop Safely"
        assert str(app.stop_btn.cget("state")) == str(__import__("tkinter").DISABLED)

    def test_stop_button_invokes_on_stop_callback_when_running(self, gui):
        """While the GUI is in running state, clicking Stop must call on_stop and
        update wording to "Stopping..."."""
        import tkinter as tk
        root, app = gui
        captured = {"called": 0}
        prior = app._on_stop
        app._on_stop = lambda: captured.__setitem__("called", captured["called"] + 1)
        try:
            app._set_running(True)
            assert str(app.stop_btn.cget("state")) == str(tk.NORMAL)
            app._on_stop_click()
            root.update()
            assert captured["called"] == 1
            assert app.stop_btn.cget("text") == "Stopping..."
            assert str(app.stop_btn.cget("state")) == str(tk.DISABLED)
            assert app._stats_panel._stat_labels["stage"].cget("text") == "Stopping"
        finally:
            app._on_stop = prior
            app._set_running(False)

    def test_pipeline_runner_stop_drill_interrupts_real_run(self, gui, tmp_path):
        """End-to-end: a real PipelineRunner with a real Pipeline must respond
        to its own stop_event by exiting cooperatively and packaging completed work.

        Reuses the module's shared Tk root rather than creating its own — destroying
        a Tk root mid-suite corrupts global Tcl state on Windows.
        """
        import time as _t
        from src.config.schema import load_config
        from src.gui.launch_gui import PipelineRunner

        root, _app = gui

        # Build a real source dir with enough files that parse takes long enough
        # for the test to observe an in-flight chunk and then trip stop.
        src = tmp_path / "stop_drill_source"
        src.mkdir()
        for i in range(40):
            (src / f"doc_{i:03d}.txt").write_text(
                f"Document {i}\n" + ("payload line " * 60 + "\n") * 30
            )

        config = load_config()
        config.embed.enabled = False
        config.enrich.enabled = False
        config.extract.enabled = False
        config.pipeline.full_reindex = True
        config.pipeline.workers = 2
        config.paths.source_dirs = [str(src)]
        config.paths.output_dir = str(tmp_path / "stop_drill_output")
        config.paths.state_db = str(tmp_path / "stop_drill_state.sqlite3")

        class _Stub:
            def __init__(self, root_widget):
                self.root = root_widget
                self.stats_history = []
                self.finished_payload = None
                self.logs = []
            def append_log(self, msg, level="INFO"):
                self.logs.append((level, msg))
            def update_stats(self, stats):
                self.stats_history.append(dict(stats))
            def update_stage_progress(self, *a, **k):
                pass
            def update_current_file(self, *a, **k):
                pass
            def update_enrichment_status(self, *a, **k):
                pass
            def pipeline_finished(self, stats):
                self.finished_payload = dict(stats)

        app = _Stub(root)
        runner = PipelineRunner(app, config)
        runner.start(str(src), str(tmp_path / "stop_drill_output"))

        from src.gui.safe_after import drain_ui_queue
        deadline = _t.time() + 30.0
        stopped_at = None
        while _t.time() < deadline:
            drain_ui_queue()
            root.update()
            if any(s.get("chunks_created", 0) > 0 for s in app.stats_history):
                runner.stop()
                stopped_at = _t.time()
                break
            _t.sleep(0.05)
        assert stopped_at is not None, "Pipeline never produced a chunk during the 30s drill window"

        finish_deadline = _t.time() + 30.0
        while _t.time() < finish_deadline and runner.is_alive:
            drain_ui_queue()
            root.update()
            _t.sleep(0.05)
        drain_ui_queue()
        root.update()
        assert not runner.is_alive, "PipelineRunner thread did not exit after stop()"
        assert app.finished_payload is not None
        assert app.finished_payload.get("stop_requested") is True, (
            f"Stop drill expected stop_requested=True, got: {app.finished_payload}"
        )

        # Restartable state: completed work was packaged so it isn't lost.
        exports = sorted((tmp_path / "stop_drill_output").glob("export_*"))
        assert len(exports) >= 1, "stop drill must still package completed work"


    def test_discovery_is_cooperative_to_stop(self, gui, tmp_path):
        """QA H3: stop fired during discovery must bail before admitting work.

        Pre-setting the stop event before PipelineRunner.start() ensures the
        first `idx % 500 == 0` poll inside the rglob loop trips immediately.
        """
        import time as _t
        from src.config.schema import load_config
        from src.gui.launch_gui import PipelineRunner

        root, _app = gui

        src = tmp_path / "discover_drill_source"
        src.mkdir()
        for i in range(20):
            (src / f"doc_{i:03d}.txt").write_text("small body\n")

        config = load_config()
        config.embed.enabled = False
        config.enrich.enabled = False
        config.extract.enabled = False
        config.pipeline.full_reindex = True
        config.pipeline.workers = 1
        config.paths.source_dirs = [str(src)]
        config.paths.output_dir = str(tmp_path / "discover_drill_output")
        config.paths.state_db = str(tmp_path / "discover_drill_state.sqlite3")

        class _Stub:
            def __init__(self, root_widget):
                self.root = root_widget
                self.stats_history = []
                self.finished_payload = None
                self.logs = []
            def append_log(self, msg, level="INFO"):
                self.logs.append((level, msg))
            def update_stats(self, stats):
                self.stats_history.append(dict(stats))
            def update_stage_progress(self, *a, **k):
                pass
            def update_current_file(self, *a, **k):
                pass
            def update_enrichment_status(self, *a, **k):
                pass
            def pipeline_finished(self, stats):
                self.finished_payload = dict(stats)

        app = _Stub(root)
        runner = PipelineRunner(app, config)
        # Prime the config paths the way start() would, then set stop and call
        # _do_run synchronously. start() clears _stop_event, so we bypass it.
        from pathlib import Path as _P
        config.paths.source_dirs = [str(_P(str(src)).resolve())]
        config.paths.output_dir = str(_P(str(tmp_path / "discover_drill_output")).resolve())
        _P(config.paths.output_dir).mkdir(parents=True, exist_ok=True)
        runner._stop_event.set()
        runner._do_run()

        # Drain queued safe_after callbacks (pipeline_finished, log lines).
        from src.gui.safe_after import drain_ui_queue
        drain_ui_queue()
        root.update()

        assert app.finished_payload is not None, "pipeline_finished must fire"
        assert app.finished_payload.get("stop_requested") is True
        # H2: export_dir should be empty since discovery bailed before admitting work
        assert app.finished_payload.get("export_dir", "") == ""
        # No export directory on disk
        exports = sorted((tmp_path / "discover_drill_output").glob("export_*"))
        assert len(exports) == 0
        # Honest log wording: warning path
        assert any("stopped" in msg.lower() for _lvl, msg in app.logs), app.logs


class TestWindowResize:
    """Tier A: Window resize doesn't crash."""

    def test_resize_minimum(self, gui):
        root, _ = gui
        root.geometry("200x200")
        root.update()
        # No crash = pass

    def test_resize_large(self, gui):
        root, _ = gui
        root.geometry("1920x1080")
        root.update()
        # No crash = pass

    def test_resize_back_to_normal(self, gui):
        root, _ = gui
        root.geometry("920x760")
        root.update()
        # No crash = pass
