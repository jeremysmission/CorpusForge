"""Stats panel -- live pipeline statistics UI extracted from CorpusForgeApp."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from .theme import DARK, FONT, FONT_BOLD, current_theme


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


class StatsPanel:
    """Two-column live statistics panel with stage-aware progress."""

    def __init__(self, parent: ttk.LabelFrame, root: tk.Tk,
                 progress_var: tk.DoubleVar, progress_label: tk.Label):
        self.root = root
        self._progress_var = progress_var
        self._progress_label = progress_label
        self._start_time = None
        self._timer_id = None
        self._running = False
        self._stat_labels = {}
        self._build(parent)

    def _build(self, parent):
        t = current_theme()

        left = ttk.Frame(parent)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(parent)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_stats = [
            ("files_found", "Files in run:"),
            ("files_after_dedup", "After dedup:"),
            ("files_parsed", "Files parsed:"),
            ("files_skipped", "Files skipped:"),
            ("files_failed", "Files failed:"),
            ("chunks_created", "Chunks created:"),
            ("chunks_enriched", "Chunks enriched:"),
            ("vectors_created", "Vectors created:"),
        ]
        for key, label_text in left_stats:
            row = ttk.Frame(left)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=FONT, bg=t["panel_bg"],
                     fg=t["label_fg"], width=18, anchor=tk.W).pack(side=tk.LEFT)
            val = tk.Label(row, text="0" if key != "files_after_dedup" else "--",
                           font=FONT_BOLD, bg=t["panel_bg"], fg=t["fg"], anchor=tk.W)
            val.pack(side=tk.LEFT)
            self._stat_labels[key] = val

        right_stats = [
            ("stage", "Stage:"),
            ("stage_progress", "Stage progress:"),
            ("current_file", "Current file:"),
            ("elapsed", "Elapsed time:"),
            ("throughput", "Files/sec:"),
            ("chunks_per_second", "Chunks/sec:"),
            ("eta", "ETA:"),
            ("skip_reasons", "Skip reasons:"),
        ]
        for key, label_text in right_stats:
            row = ttk.Frame(right)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=FONT, bg=t["panel_bg"],
                     fg=t["label_fg"], width=16, anchor=tk.W).pack(side=tk.LEFT)
            val = tk.Label(row, text="--", font=FONT_BOLD, bg=t["panel_bg"],
                           fg=t["fg"], anchor=tk.W, wraplength=320, justify=tk.LEFT)
            val.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._stat_labels[key] = val

    def start_timer(self):
        self._start_time = time.time()
        self._running = True
        self._tick()

    def stop_timer(self):
        self._running = False
        if self._timer_id is not None:
            try:
                self.root.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None

    def _tick(self):
        if not self._running or self._start_time is None:
            return
        elapsed = time.time() - self._start_time
        self._stat_labels["elapsed"].configure(text=_format_elapsed(elapsed))
        self._timer_id = self.root.after(1000, self._tick)

    def update_stats(self, stats: dict):
        """Update the live stats panel from a stats dictionary."""
        total = stats.get("files_found", 0)
        after_dedup = stats.get("files_after_dedup", 0)
        parsed = stats.get("files_parsed", 0)
        failed = stats.get("files_failed", 0)
        skipped = stats.get("files_skipped", 0)
        done = parsed + failed + skipped
        work_total = after_dedup or total

        self._stat_labels["files_found"].configure(text=str(total))
        self._stat_labels["files_after_dedup"].configure(
            text=str(after_dedup) if after_dedup else "--",
        )
        self._stat_labels["files_parsed"].configure(text=str(parsed))
        self._stat_labels["files_skipped"].configure(text=str(skipped))
        self._stat_labels["files_failed"].configure(
            text=str(failed),
            fg=DARK["red"] if failed > 0 else DARK["fg"],
        )
        self._stat_labels["chunks_created"].configure(
            text=str(stats.get("chunks_created", 0)),
        )
        self._stat_labels["chunks_enriched"].configure(
            text=str(stats.get("chunks_enriched", 0)),
        )
        self._stat_labels["vectors_created"].configure(
            text=str(stats.get("vectors_created", 0)),
        )
        chunk_rate = stats.get("chunks_per_second", 0.0) or 0.0
        if chunk_rate > 0:
            self._stat_labels["chunks_per_second"].configure(
                text=f"{chunk_rate:.1f}",
            )
        else:
            self._stat_labels["chunks_per_second"].configure(text="--")

        skip_reasons = stats.get("skip_reasons", "")
        self._stat_labels["skip_reasons"].configure(
            text=skip_reasons if skip_reasons else "--",
        )

        elapsed = stats.get("elapsed_seconds", 0.0)
        if elapsed <= 0 and self._start_time:
            elapsed = time.time() - self._start_time
        if elapsed > 0:
            self._stat_labels["elapsed"].configure(text=_format_elapsed(elapsed))
            if elapsed > 0 and done > 0:
                rate = done / elapsed
                self._stat_labels["throughput"].configure(
                    text=f"{rate:.1f} files/sec",
                )
                remaining = max(work_total - done, 0)
                if rate > 0 and remaining > 0:
                    eta_sec = remaining / rate
                    self._stat_labels["eta"].configure(
                        text=_format_elapsed(eta_sec),
                    )
                else:
                    self._stat_labels["eta"].configure(text="--")

    def update_stage_progress(self, stage: str, current: int, total: int, detail: str = ""):
        stage_map = {
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
        stage_display = stage_map.get(stage, stage.replace("_", " ").title())
        detail_display = detail
        if len(detail_display) > 70:
            detail_display = detail_display[:67] + "..."
        progress_text = f"{current}/{total}" if total else "--"
        if detail_display:
            progress_text += f" - {detail_display}"
        self._stat_labels["stage"].configure(text=stage_display)
        self._stat_labels["stage_progress"].configure(text=progress_text)
        if total > 0:
            pct = min(100.0, (current / total) * 100.0)
            self._progress_var.set(pct)
            self._progress_label.configure(text=f"{stage_display} {current} / {total}")
        elif stage == "stopping":
            self._progress_label.configure(text="Stopping safely...")

    def update_current_file(self, filename: str):
        display = filename
        if len(display) > 60:
            display = "..." + display[-57:]
        self._stat_labels["current_file"].configure(text=display)

    def finalize(self, stats: dict):
        """Set final state after pipeline completes."""
        elapsed = stats.get("elapsed_seconds", 0)
        stop_requested = bool(stats.get("stop_requested"))
        self._stat_labels["elapsed"].configure(text=_format_elapsed(elapsed))
        self._stat_labels["eta"].configure(text="Stopped" if stop_requested else "Done")
        self._stat_labels["stage"].configure(text="Stopped" if stop_requested else "Done")
        self._stat_labels["stage_progress"].configure(
            text="Stopped cleanly after in-flight work" if stop_requested else "Completed"
        )
        self._stat_labels["current_file"].configure(text="--")

        total = stats.get("files_found", 0)
        work_total = stats.get("files_after_dedup", 0) or total
        parsed = stats.get("files_parsed", 0)
        failed = stats.get("files_failed", 0)
        skipped = stats.get("files_skipped", 0)
        done = parsed + failed + skipped
        if work_total > 0:
            if stop_requested:
                pct = min(100.0, (done / work_total) * 100.0)
                self._progress_var.set(pct)
                if total > work_total:
                    self._progress_label.configure(
                        text=f"Stopped ({done}/{work_total} work files, {total} discovered)"
                    )
                else:
                    self._progress_label.configure(text=f"Stopped ({done}/{work_total} work files)")
            else:
                self._progress_var.set(100.0)
                if total > work_total:
                    self._progress_label.configure(
                        text=f"Done ({done}/{work_total} work files, {total} discovered)"
                    )
                else:
                    self._progress_label.configure(text=f"Done ({done}/{work_total} work files)")
