"""Dedup-only panel -- standalone dedup scan UI component extracted from CorpusForgeApp."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog

from .theme import FONT, FONT_SMALL, current_theme


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


class DedupOnlyPanel:
    """Dedup-only pass panel -- source path, start/stop, live progress."""

    def __init__(self, parent: ttk.LabelFrame, root: tk.Tk,
                 on_dedup_only_start=None, on_dedup_only_stop=None,
                 append_log=None, default_output: str = "data/output"):
        self.root = root
        self._on_dedup_only_start = on_dedup_only_start
        self._on_dedup_only_stop = on_dedup_only_stop
        self._append_log = append_log
        self._default_output = default_output
        self._running = False
        self._build(parent)

    def _build(self, parent):
        t = current_theme()

        row0 = ttk.Frame(parent)
        row0.pack(fill=tk.X, pady=2)

        tk.Label(row0, text="Source:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], width=8, anchor=tk.W).pack(side=tk.LEFT)

        self.dedup_only_src_var = tk.StringVar(value="data/staging")
        self.dedup_only_src_entry = tk.Entry(
            row0, textvariable=self.dedup_only_src_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
            relief=tk.FLAT, bd=2,
        )
        self.dedup_only_src_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        self.browse_dedup_only_btn = ttk.Button(
            row0, text="Browse",
            command=lambda: self._browse_into(self.dedup_only_src_var, "Select Dedup Source"),
        )
        self.browse_dedup_only_btn.pack(side=tk.RIGHT)

        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=2)

        tk.Label(row1, text="Output:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], width=8, anchor=tk.W).pack(side=tk.LEFT)

        self.dedup_only_out_var = tk.StringVar(value=self._default_output)
        self.dedup_only_out_entry = tk.Entry(
            row1, textvariable=self.dedup_only_out_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
            relief=tk.FLAT, bd=2,
        )
        self.dedup_only_out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        self.browse_dedup_only_out_btn = ttk.Button(
            row1, text="Browse",
            command=lambda: self._browse_into(self.dedup_only_out_var, "Select Dedup Output Folder"),
        )
        self.browse_dedup_only_out_btn.pack(side=tk.RIGHT)

        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(2, 2))

        self.copy_deduped_sources_var = tk.BooleanVar(value=True)
        self.copy_deduped_sources_chk = ttk.Checkbutton(
            row2,
            text="Save portable deduped source copy (deduped_sources/)",
            variable=self.copy_deduped_sources_var,
        )
        self.copy_deduped_sources_chk.pack(side=tk.LEFT)

        row3 = ttk.Frame(parent)
        row3.pack(fill=tk.X, pady=(6, 2))

        self.dedup_only_start_btn = ttk.Button(
            row3, text="Run Dedup Only", style="Accent.TButton",
            command=self._on_start_click,
        )
        self.dedup_only_start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.dedup_only_stop_btn = ttk.Button(
            row3, text="Stop", style="Tertiary.TButton",
            command=self._on_stop_click, state=tk.DISABLED,
        )
        self.dedup_only_stop_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.dedup_only_progress_var = tk.DoubleVar(value=0.0)
        self.dedup_only_progress_bar = ttk.Progressbar(
            row3, variable=self.dedup_only_progress_var, maximum=100,
            mode="determinate", length=250,
        )
        self.dedup_only_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.dedup_only_status_label = tk.Label(
            row3, text="Idle", font=FONT_SMALL,
            bg=t["panel_bg"], fg=t["label_fg"],
        )
        self.dedup_only_status_label.pack(side=tk.RIGHT)

        # Dedup stats row
        row4 = ttk.Frame(parent)
        row4.pack(fill=tk.X, pady=2)

        self._dedup_only_stat_labels = {}
        for key, label_text in [
            ("scanned", "Scanned:"), ("duplicates", "Duplicates:"),
            ("unique", "Unique:"), ("current", "Current:"),
            ("elapsed", "Elapsed:"), ("eta", "ETA:"),
        ]:
            tk.Label(row4, text=label_text, font=FONT_SMALL, bg=t["panel_bg"],
                     fg=t["label_fg"]).pack(side=tk.LEFT, padx=(0, 2))
            val = tk.Label(row4, text="--", font=FONT_SMALL, bg=t["panel_bg"],
                           fg=t["fg"])
            val.pack(side=tk.LEFT, padx=(0, 10))
            self._dedup_only_stat_labels[key] = val

        row5 = ttk.Frame(parent)
        row5.pack(fill=tk.X, pady=(2, 0))
        self.dedup_only_artifact_label = tk.Label(
            row5,
            text="Artifacts: canonical_files.txt, dedup_report.json, run_report.txt, optional deduped_sources/",
            font=FONT_SMALL,
            bg=t["panel_bg"],
            fg=t["label_fg"],
            anchor=tk.W,
            wraplength=760,
        )
        self.dedup_only_artifact_label.pack(fill=tk.X)

    def _browse_into(self, var, title):
        path = filedialog.askdirectory(title=title)
        if path:
            var.set(path)

    def _on_start_click(self):
        if self._running:
            return
        self._running = True
        self.dedup_only_start_btn.configure(state=tk.DISABLED)
        self.dedup_only_stop_btn.configure(state=tk.NORMAL)
        self.dedup_only_status_label.configure(text="Starting...")
        if self._on_dedup_only_start:
            self._on_dedup_only_start(
                source=self.dedup_only_src_var.get(),
                output=self.dedup_only_out_var.get(),
                copy_sources=self.copy_deduped_sources_var.get(),
            )

    def _on_stop_click(self):
        if self._on_dedup_only_stop:
            self._on_dedup_only_stop()
        if self._append_log:
            self._append_log("Dedup-only stop requested.", "WARNING")

    def update_dedup_only_stats(self, stats: dict):
        """Update the dedup-only panel from a stats dict."""
        total = stats.get("total_files", 0)
        scanned = stats.get("files_scanned", 0)
        dupes = stats.get("duplicates_found", 0)
        unique = stats.get("unique_files")
        current = stats.get("current_file", "")

        if total > 0:
            pct = min(100.0, (scanned / total) * 100.0)
            self.dedup_only_progress_var.set(pct)

        self._dedup_only_stat_labels["scanned"].configure(text=f"{scanned}/{total}")
        self._dedup_only_stat_labels["duplicates"].configure(text=str(dupes))
        self._dedup_only_stat_labels["unique"].configure(
            text=str(unique) if unique is not None else "--"
        )

        if len(current) > 35:
            current = "..." + current[-32:]
        self._dedup_only_stat_labels["current"].configure(text=current or "--")

        elapsed = stats.get("elapsed_seconds", 0)
        self._dedup_only_stat_labels["elapsed"].configure(text=_format_elapsed(elapsed))

        if elapsed > 0 and scanned > 0 and total > scanned:
            rate = scanned / elapsed
            remaining = total - scanned
            self._dedup_only_stat_labels["eta"].configure(text=_format_elapsed(remaining / rate))
        else:
            self._dedup_only_stat_labels["eta"].configure(text="--")

        status_text = stats.get("status_text", f"{scanned}/{total}" if total else "Idle")
        self.dedup_only_status_label.configure(text=status_text)
        output_dir = stats.get("output_dir")
        portable_copy_dir = stats.get("portable_copy_dir")
        if output_dir:
            artifact_text = "Output: " + str(output_dir) + " | Artifacts: canonical_files.txt, dedup_report.json, run_report.txt"
            if portable_copy_dir:
                artifact_text += f", deduped_sources/ -> {portable_copy_dir}"
            self.dedup_only_artifact_label.configure(
                text=artifact_text
            )

    def dedup_only_finished(self, stats: dict, message: str = ""):
        """Called when dedup-only pass completes."""
        self.update_dedup_only_stats(stats)
        self._running = False
        self.dedup_only_start_btn.configure(state=tk.NORMAL)
        self.dedup_only_stop_btn.configure(state=tk.DISABLED)
        total = stats.get("total_files", 0)
        scanned = stats.get("files_scanned", 0)
        if total > 0:
            self.dedup_only_progress_var.set(min(100.0, (scanned / total) * 100.0))
        self.dedup_only_status_label.configure(text=stats.get("status_text", "Done"))
        if message and self._append_log:
            self._append_log(message, "INFO")
