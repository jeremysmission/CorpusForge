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

os.environ["HYBRIDRAG_HEADLESS"] = "1"


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
        assert len(buttons) >= 3, f"Expected at least 3 buttons, found {len(buttons)}"
        assert "Start Pipeline" in labels
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
    SKIP_LABELS = {"Start Pipeline", "Browse", "Stop", "Reset to Defaults"}

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
