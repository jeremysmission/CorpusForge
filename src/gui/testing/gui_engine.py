"""
CorpusForge GUI Testing -- Behavioral Engine

Ported from HybridRAG V1 (src/gui/testing/gui_engine.py).
Discovers all clickable widgets, invokes them safely, captures state
snapshots before/after each action, diffs file system and core state,
and tracks per-action performance metrics including p95.

Plain-English view: this file is the "virtual operator". Given a
headless Forge window (see :mod:`gui_boot`), it walks the widget tree,
finds every button/spinbox/checkbox, clicks each one, and records
whether anything crashed and how long each click took. It is only
used by automated tests and never runs during a normal Forge session.
"""

from __future__ import annotations

import hashlib
import statistics
import time
import traceback
import tkinter as tk
from pathlib import Path
from typing import Any


class ForgeGuiEngine:
    """The virtual operator - drives the Forge GUI from automated tests.

    Given a headless Forge app, this engine discovers every button,
    spinbox, and checkbox, safely invokes each one, and records a
    report of crashes, timings, and file-system changes. It is only
    used by the automated test harness; operators never run it.
    """

    def __init__(self, app):
        self.app = app
        self.root = app.root if hasattr(app, "root") else app
        self._times: list[float] = []

    # ------------------------------------------------------------------
    # Widget discovery
    # ------------------------------------------------------------------
    def discover_buttons(self) -> list[tk.Widget]:
        """Walk the widget tree and return all Button/TButton instances."""
        found: list[tk.Widget] = []

        def walk(widget: tk.Widget) -> None:
            for child in widget.winfo_children():
                cls_name = child.winfo_class()
                if cls_name in ("Button", "TButton"):
                    found.append(child)
                walk(child)

        walk(self.root)
        return found

    def discover_spinboxes(self) -> list[tk.Widget]:
        """Walk the widget tree and return all Spinbox instances."""
        found: list[tk.Widget] = []

        def walk(widget: tk.Widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Spinbox):
                    found.append(child)
                walk(child)

        walk(self.root)
        return found

    def discover_checkbuttons(self) -> list[tk.Widget]:
        """Walk the widget tree and return all Checkbutton instances."""
        found: list[tk.Widget] = []

        def walk(widget: tk.Widget) -> None:
            for child in widget.winfo_children():
                cls_name = child.winfo_class()
                if cls_name in ("Checkbutton", "TCheckbutton"):
                    found.append(child)
                walk(child)

        walk(self.root)
        return found

    # ------------------------------------------------------------------
    # Safe invocation
    # ------------------------------------------------------------------
    def invoke_button(self, button: tk.Widget) -> dict[str, Any]:
        """Invoke a button and return timing + error info."""
        start = time.perf_counter()
        success = True
        error = None
        trace = None
        try:
            button.invoke()
            self.root.update()
        except Exception as e:
            success = False
            error = str(e)
            trace = traceback.format_exc()
        elapsed = time.perf_counter() - start
        self._times.append(elapsed)
        return {
            "success": success,
            "error": error,
            "trace": trace,
            "elapsed_s": round(elapsed, 4),
        }

    def rapid_click(self, button: tk.Widget, count: int = 20) -> dict[str, Any]:
        """Click a button rapidly N times. Return crash count."""
        crashes = 0
        for _ in range(count):
            try:
                button.invoke()
                self.root.update_idletasks()
            except Exception:
                crashes += 1
        try:
            self.root.update()
        except Exception:
            crashes += 1
        return {"clicks": count, "crashes": crashes}

    # ------------------------------------------------------------------
    # State snapshots
    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Capture current file system state of output directory."""
        data: dict[str, str] = {}
        base = Path("data/output")
        if base.exists():
            for f in sorted(base.glob("export_*"))[-3:]:
                if f.is_dir():
                    for child in f.iterdir():
                        if child.is_file():
                            try:
                                data[str(child)] = hashlib.md5(child.read_bytes()).hexdigest()
                            except Exception:
                                data[str(child)] = "unreadable"
        return {"files": data}

    @staticmethod
    def diff(before: dict, after: dict) -> dict[str, Any]:
        """Compute file state differences."""
        changes: list[dict[str, str]] = []
        bf, af = before["files"], after["files"]
        for path, h in af.items():
            if path not in bf:
                changes.append({"type": "created", "path": path})
            elif bf[path] != h:
                changes.append({"type": "modified", "path": path})
        for path in bf:
            if path not in af:
                changes.append({"type": "deleted", "path": path})
        return {"file_changes": changes}

    # ------------------------------------------------------------------
    # Performance summary
    # ------------------------------------------------------------------
    def perf_summary(self) -> dict[str, Any]:
        """Return timing statistics for all invocations."""
        if not self._times:
            return {}
        return {
            "count": len(self._times),
            "avg_s": round(statistics.mean(self._times), 4),
            "p95_s": round(sorted(self._times)[int(len(self._times) * 0.95)], 4),
            "max_s": round(max(self._times), 4),
        }

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------
    def run_all(self) -> dict[str, Any]:
        """Discover and invoke every button. Return full report."""
        results: list[dict[str, Any]] = []

        for btn in self.discover_buttons():
            try:
                label = btn.cget("text")
            except Exception:
                label = "(unknown)"
            before = self.snapshot()
            inv = self.invoke_button(btn)
            after = self.snapshot()
            results.append({
                "widget": "button",
                "label": label,
                "invoke": inv,
                "diff": self.diff(before, after),
            })

        failures = [r for r in results if not r["invoke"]["success"]]
        return {
            "total_actions": len(results),
            "failures": len(failures),
            "performance": self.perf_summary(),
            "results": results,
        }
