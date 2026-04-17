"""Standalone desktop app for the dedup recovery stage.

This window is the one an operator sees after running
``launch_dedup_gui.py``. It is a simpler, one-purpose cousin of the
main Forge window: the operator picks a source folder, sets a
similarity threshold and minimum character count, and clicks Start
Recovery. Forge walks the tree, groups near-duplicate PDF/DOC/DOCX
files into "families", picks a canonical file for each family, and
writes ``canonical_files.txt`` + a SQLite audit trail.

This file only controls one pipeline stage: the recovery dedup pass.
It does not parse text, chunk, enrich, or embed. Its canonical list is
the input for a follow-up chunking run.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog, ttk

from .theme import (
    DARK,
    FONT,
    FONT_BOLD,
    FONT_MONO,
    FONT_SMALL,
    FONT_TITLE,
    apply_ttk_styles,
    current_theme,
)


_MAX_LOG_LINES = 2000


class DedupRecoveryApp:
    """The Recovery Dedup window - a one-purpose cleanup UI.

    Holds the controls (source/output pickers, similarity threshold,
    worker count), a live Recovery Stats panel, and a Recovery Log.
    Start Recovery is wired to a background thread that scans the tree
    and writes the canonical/duplicate artifacts. The window itself
    does not do the scanning - it only shows progress.
    """

    def __init__(self, root: tk.Tk, config_path: str, on_start=None, on_stop=None):
        self.root = root
        self.config_path = config_path
        self._on_start = on_start
        self._on_stop = on_stop
        self._running = False
        self._start_time: float | None = None
        self._timer_id = None

        self._setup_window()
        apply_ttk_styles(DARK)
        self._build_ui()

    def _setup_window(self) -> None:
        """Set the Recovery Dedup window title, size, and colors."""
        t = current_theme()
        self.root.title("CorpusForge Recovery Dedup")
        self.root.geometry("980x780")
        self.root.minsize(820, 620)
        self.root.configure(bg=t["bg"])

    def _build_ui(self) -> None:
        """Assemble the control panel, stats, log, and status bar."""
        t = current_theme()
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            main,
            text="CorpusForge Recovery Dedup",
            font=FONT_TITLE,
            bg=t["bg"],
            fg=t["accent"],
        )
        title.pack(anchor=tk.W, pady=(0, 4))

        subtitle = tk.Label(
            main,
            text=(
                "Recovery stage for PDF/DOC/DOCX near-duplicate cleanup before re-chunking. "
                "Builds a canonical file list and a duplicate audit trail."
            ),
            font=FONT_SMALL,
            bg=t["bg"],
            fg=t["label_fg"],
            wraplength=900,
            justify=tk.LEFT,
        )
        subtitle.pack(anchor=tk.W, pady=(0, 8))

        ctrl = ttk.LabelFrame(main, text="Recovery Control", padding=8)
        ctrl.pack(fill=tk.X, pady=(0, 6))
        self._build_control_panel(ctrl, t)

        stats = ttk.LabelFrame(main, text="Recovery Stats", padding=8)
        stats.pack(fill=tk.X, pady=(0, 6))
        self._build_stats_panel(stats, t)

        log_frame = ttk.LabelFrame(main, text="Recovery Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self._build_log_panel(log_frame, t)

        status = tk.Frame(main, bg=t["panel_bg"], height=28)
        status.pack(fill=tk.X)
        self.status_var = tk.StringVar(
            value=f"Config: {self.config_path} | Focus: PDF/DOC/DOCX | Output: canonical_files.txt + sqlite index"
        )
        tk.Label(
            status,
            textvariable=self.status_var,
            font=FONT_SMALL,
            bg=t["panel_bg"],
            fg=t["label_fg"],
            padx=12,
        ).pack(side=tk.LEFT)

    def _build_control_panel(self, parent, t) -> None:
        """Build the source/output/threshold/workers row and action buttons."""
        row0 = ttk.Frame(parent)
        row0.pack(fill=tk.X, pady=2)
        tk.Label(row0, text="Source:", font=FONT, bg=t["panel_bg"], fg=t["label_fg"], width=9, anchor=tk.W).pack(side=tk.LEFT)
        self.source_var = tk.StringVar(value="data/source")
        self.source_entry = tk.Entry(
            row0,
            textvariable=self.source_var,
            font=FONT,
            bg=t["input_bg"],
            fg=t["input_fg"],
            insertbackground=t["fg"],
            relief=tk.FLAT,
            bd=2,
        )
        self.source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        self.source_btn = ttk.Button(row0, text="Browse", command=self._browse_source)
        self.source_btn.pack(side=tk.RIGHT)

        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="Output:", font=FONT, bg=t["panel_bg"], fg=t["label_fg"], width=9, anchor=tk.W).pack(side=tk.LEFT)
        self.output_var = tk.StringVar(value="data/dedup")
        self.output_entry = tk.Entry(
            row1,
            textvariable=self.output_var,
            font=FONT,
            bg=t["input_bg"],
            fg=t["input_fg"],
            insertbackground=t["fg"],
            relief=tk.FLAT,
            bd=2,
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        self.output_btn = ttk.Button(row1, text="Browse", command=self._browse_output)
        self.output_btn.pack(side=tk.RIGHT)

        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Threshold:", font=FONT, bg=t["panel_bg"], fg=t["label_fg"], width=9, anchor=tk.W).pack(side=tk.LEFT)
        self.threshold_var = tk.StringVar(value="0.90")
        self.threshold_entry = tk.Entry(
            row2,
            textvariable=self.threshold_var,
            width=8,
            font=FONT,
            bg=t["input_bg"],
            fg=t["input_fg"],
            insertbackground=t["fg"],
            relief=tk.FLAT,
            bd=2,
        )
        self.threshold_entry.pack(side=tk.LEFT, padx=(4, 12))
        tk.Label(row2, text="Min chars:", font=FONT, bg=t["panel_bg"], fg=t["label_fg"]).pack(side=tk.LEFT)
        self.min_chars_var = tk.StringVar(value="200")
        self.min_chars_entry = tk.Entry(
            row2,
            textvariable=self.min_chars_var,
            width=8,
            font=FONT,
            bg=t["input_bg"],
            fg=t["input_fg"],
            insertbackground=t["fg"],
            relief=tk.FLAT,
            bd=2,
        )
        self.min_chars_entry.pack(side=tk.LEFT, padx=(4, 12))
        tk.Label(row2, text="Workers:", font=FONT, bg=t["panel_bg"], fg=t["label_fg"]).pack(side=tk.LEFT)
        self.workers_var = tk.StringVar(value="4")
        self.workers_entry = tk.Entry(
            row2,
            textvariable=self.workers_var,
            width=6,
            font=FONT,
            bg=t["input_bg"],
            fg=t["input_fg"],
            insertbackground=t["fg"],
            relief=tk.FLAT,
            bd=2,
        )
        self.workers_entry.pack(side=tk.LEFT, padx=(4, 0))

        row3 = ttk.Frame(parent)
        row3.pack(fill=tk.X, pady=(6, 2))
        self.start_btn = ttk.Button(row3, text="Start Recovery", style="Accent.TButton", command=self._on_start_click)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(row3, text="Stop After Current Family", style="Tertiary.TButton", command=self._on_stop_click, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 12))
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(row3, variable=self.progress_var, maximum=100, mode="determinate", length=300)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.progress_label = tk.Label(row3, text="0 / 0 families", font=FONT_SMALL, bg=t["panel_bg"], fg=t["label_fg"])
        self.progress_label.pack(side=tk.RIGHT)

    def _build_stats_panel(self, parent, t) -> None:
        """Build the two-column Recovery Stats panel."""
        left = ttk.Frame(parent)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = ttk.Frame(parent)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._stat_labels = {}
        left_items = [
            ("files_seen", "Files seen:"),
            ("candidate_groups", "Candidate groups:"),
            ("singleton_files", "Singleton skips:"),
            ("groups_processed", "Groups processed:"),
        ]
        right_items = [
            ("canonical_files", "Canonical files:"),
            ("duplicate_files", "Duplicate files:"),
            ("current_group", "Current family:"),
            ("elapsed", "Elapsed:"),
        ]

        for key, label_text in left_items:
            row = ttk.Frame(left)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=FONT, bg=t["panel_bg"], fg=t["label_fg"], width=18, anchor=tk.W).pack(side=tk.LEFT)
            value = tk.Label(row, text="0", font=FONT_BOLD, bg=t["panel_bg"], fg=t["fg"], anchor=tk.W)
            value.pack(side=tk.LEFT)
            self._stat_labels[key] = value

        for key, label_text in right_items:
            row = ttk.Frame(right)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=FONT, bg=t["panel_bg"], fg=t["label_fg"], width=18, anchor=tk.W).pack(side=tk.LEFT)
            value = tk.Label(row, text="--", font=FONT_BOLD, bg=t["panel_bg"], fg=t["fg"], anchor=tk.W, wraplength=320)
            value.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._stat_labels[key] = value

    def _build_log_panel(self, parent, t) -> None:
        """Build the scrolling Recovery Log text area."""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            container,
            font=FONT_MONO,
            bg=t["bg"],
            fg=t["fg"],
            insertbackground=t["fg"],
            relief=tk.FLAT,
            bd=2,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=12,
        )
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("INFO", foreground=t["fg"])
        self.log_text.tag_configure("WARNING", foreground=t["orange"])
        self.log_text.tag_configure("ERROR", foreground=t["red"])

    def _browse_source(self) -> None:
        """Open a folder picker so the operator can pick the source folder."""
        path = filedialog.askdirectory(title="Select Source Folder")
        if path:
            self.source_var.set(path)

    def _browse_output(self) -> None:
        """Open a folder picker for the recovery export folder."""
        path = filedialog.askdirectory(title="Select Recovery Output Folder")
        if path:
            self.output_var.set(path)

    def _on_start_click(self) -> None:
        """Handle Start Recovery - begin a recovery dedup run."""
        if self._running:
            return
        self._set_running(True)
        if self._on_start:
            self._on_start(
                source=self.source_var.get(),
                output=self.output_var.get(),
                similarity_threshold=self.threshold_var.get(),
                min_chars=self.min_chars_var.get(),
                workers=self.workers_var.get(),
            )

    def _on_stop_click(self) -> None:
        """Handle the Stop button - finish the current family, then exit."""
        if self._on_stop:
            self._on_stop()
        self.append_log("Recovery stop requested. Current family will finish first.", "WARNING")

    def _set_running(self, running: bool) -> None:
        """Lock or unlock controls and start/stop the elapsed-time ticker."""
        self._running = running
        state = tk.DISABLED if running else tk.NORMAL
        self.start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        for widget in (
            self.source_entry,
            self.output_entry,
            self.threshold_entry,
            self.min_chars_entry,
            self.workers_entry,
        ):
            widget.configure(state=state)
        self.source_btn.configure(state=state)
        self.output_btn.configure(state=state)
        if running:
            self._start_time = time.time()
            self._tick_elapsed()
        else:
            if self._timer_id is not None:
                try:
                    self.root.after_cancel(self._timer_id)
                except Exception:
                    pass
                self._timer_id = None

    def _tick_elapsed(self) -> None:
        """Update the Elapsed label once per second while the run is active."""
        if not self._running or self._start_time is None:
            return
        elapsed = int(time.time() - self._start_time)
        self._stat_labels["elapsed"].configure(text=_format_elapsed(elapsed))
        self._timer_id = self.root.after(1000, self._tick_elapsed)

    def update_progress(self, *, group_index: int, total_groups: int, stem_key: str, group_size: int) -> None:
        """Update the progress bar and the 'Current family' readout."""
        pct = 0.0 if total_groups <= 0 else min(100.0, (group_index / total_groups) * 100.0)
        self.progress_var.set(pct)
        self.progress_label.configure(text=f"{group_index} / {total_groups} families")
        current = stem_key or "<unknown>"
        if len(current) > 60:
            current = "..." + current[-57:]
        self._stat_labels["current_group"].configure(text=f"{current} ({group_size} files)")

    def update_stats(self, stats: dict) -> None:
        """Refresh the Recovery Stats panel from a stats dict."""
        self._stat_labels["files_seen"].configure(text=str(stats.get("files_seen", 0)))
        self._stat_labels["candidate_groups"].configure(text=str(stats.get("candidate_groups", 0)))
        self._stat_labels["singleton_files"].configure(text=str(stats.get("singleton_files", 0)))
        self._stat_labels["groups_processed"].configure(text=str(stats.get("groups_processed", 0)))
        self._stat_labels["canonical_files"].configure(text=str(stats.get("canonical_files", 0)))
        self._stat_labels["duplicate_files"].configure(text=str(stats.get("duplicate_files", 0)))

    def append_log(self, message: str, level: str = "INFO") -> None:
        """Add a line (color-coded by level) to the Recovery Log panel."""
        tag = level if level in ("INFO", "WARNING", "ERROR") else "INFO"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", tag)
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > _MAX_LOG_LINES:
            self.log_text.delete("1.0", f"{line_count - _MAX_LOG_LINES}.0")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def run_finished(self, stats: dict, message: str) -> None:
        """Called when the recovery dedup run completes (success or abort)."""
        self.update_stats(stats)
        self._set_running(False)
        self.progress_var.set(100.0 if stats.get("candidate_groups", 0) else 0.0)
        self._stat_labels["elapsed"].configure(text=_format_elapsed(int(stats.get("elapsed_seconds", 0))))
        self.append_log(message, "INFO")


def _format_elapsed(seconds: int) -> str:
    """Format a seconds count as a human-readable H:MM:SS or M:SS string."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
