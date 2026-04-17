"""Transfer panel -- bulk file transfer UI component extracted from CorpusForgeApp.

This is the "Bulk Transfer" group in the main Forge window. An
operator uses it to copy raw source files from a shared drive or
exchange folder into a local staging folder before running the
pipeline. The transfer is a straight file copy - no parsing or
chunking happens here. It controls one preparatory stage: staging.
The copy itself runs in a background thread
(:class:`TransferRunner` in ``launch_gui.py``); this panel only
displays progress (files copied, MB transferred, speed, ETA).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog

from .theme import FONT, FONT_SMALL, current_theme
from .safe_after import safe_after


def _format_elapsed(seconds: float) -> str:
    """Format a seconds count as a human-readable H:MM:SS or M:SS string."""
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


class TransferPanel:
    """The Bulk Transfer panel - copy raw source files into staging.

    Lets the operator pick a "From" folder and a "To" (staging)
    folder, then click "Start Transfer". A background worker performs
    the copy; this panel shows files copied, MB transferred, speed,
    and ETA while the copy is running.
    """

    def __init__(self, parent: ttk.LabelFrame, root: tk.Tk,
                 on_transfer_start=None, on_transfer_stop=None,
                 append_log=None):
        self.root = root
        self._on_transfer_start = on_transfer_start
        self._on_transfer_stop = on_transfer_stop
        self._append_log = append_log
        self._running = False
        self._build(parent)

    def _build(self, parent):
        """Assemble the From/To pickers, action buttons, and stat row."""
        t = current_theme()

        row0 = ttk.Frame(parent)
        row0.pack(fill=tk.X, pady=2)

        tk.Label(row0, text="From:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], width=8, anchor=tk.W).pack(side=tk.LEFT)

        self.transfer_src_var = tk.StringVar(value="")
        self.transfer_src_entry = tk.Entry(
            row0, textvariable=self.transfer_src_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
            relief=tk.FLAT, bd=2,
        )
        self.transfer_src_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        self.browse_transfer_src_btn = ttk.Button(
            row0, text="Browse", command=self._browse_transfer_source,
        )
        self.browse_transfer_src_btn.pack(side=tk.RIGHT)

        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=2)

        tk.Label(row1, text="To:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], width=8, anchor=tk.W).pack(side=tk.LEFT)

        self.transfer_dest_var = tk.StringVar(value="data/staging")
        self.transfer_dest_entry = tk.Entry(
            row1, textvariable=self.transfer_dest_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
            relief=tk.FLAT, bd=2,
        )
        self.transfer_dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        self.browse_transfer_dest_btn = ttk.Button(
            row1, text="Browse", command=self._browse_transfer_dest,
        )
        self.browse_transfer_dest_btn.pack(side=tk.RIGHT)

        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(6, 2))

        self.transfer_start_btn = ttk.Button(
            row2, text="Start Transfer", style="Accent.TButton",
            command=self._on_start_click,
        )
        self.transfer_start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.transfer_stop_btn = ttk.Button(
            row2, text="Stop", style="Tertiary.TButton",
            command=self._on_stop_click, state=tk.DISABLED,
        )
        self.transfer_stop_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.transfer_progress_var = tk.DoubleVar(value=0.0)
        self.transfer_progress_bar = ttk.Progressbar(
            row2, variable=self.transfer_progress_var, maximum=100,
            mode="determinate", length=250,
        )
        self.transfer_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.transfer_status_label = tk.Label(
            row2, text="Idle", font=FONT_SMALL,
            bg=t["panel_bg"], fg=t["label_fg"],
        )
        self.transfer_status_label.pack(side=tk.RIGHT)

        # Transfer stats row
        row3 = ttk.Frame(parent)
        row3.pack(fill=tk.X, pady=2)

        self._transfer_stat_labels = {}
        for key, label_text in [
            ("files", "Files:"), ("bytes", "Transferred:"),
            ("speed", "Speed:"), ("eta", "ETA:"), ("current", "Current:"),
        ]:
            tk.Label(row3, text=label_text, font=FONT_SMALL, bg=t["panel_bg"],
                     fg=t["label_fg"]).pack(side=tk.LEFT, padx=(0, 2))
            val = tk.Label(row3, text="--", font=FONT_SMALL, bg=t["panel_bg"],
                           fg=t["fg"])
            val.pack(side=tk.LEFT, padx=(0, 10))
            self._transfer_stat_labels[key] = val

    def _browse_transfer_source(self):
        """Open a folder picker for the transfer source (From) folder."""
        path = filedialog.askdirectory(title="Select Transfer Source")
        if path:
            self.transfer_src_var.set(path)

    def _browse_transfer_dest(self):
        """Open a folder picker for the transfer destination (To) folder."""
        path = filedialog.askdirectory(title="Select Transfer Destination")
        if path:
            self.transfer_dest_var.set(path)

    def _on_start_click(self):
        """Handle the Start Transfer button - begin a bulk file copy."""
        if self._running:
            return
        self._running = True
        self.transfer_start_btn.configure(state=tk.DISABLED)
        self.transfer_stop_btn.configure(state=tk.NORMAL)
        if self._on_transfer_start:
            self._on_transfer_start(
                source=self.transfer_src_var.get(),
                dest=self.transfer_dest_var.get(),
            )

    def _on_stop_click(self):
        """Handle the Stop button - ask the transfer thread to exit cleanly."""
        if self._on_transfer_stop:
            self._on_transfer_stop()
        if self._append_log:
            self._append_log("Transfer stop requested.", "WARNING")

    def update_transfer_stats(self, stats: dict):
        """Update the transfer panel from a TransferStats dict."""
        total = stats.get("total_files", 0)
        done = stats.get("files_copied", 0) + stats.get("files_skipped", 0) + stats.get("files_failed", 0)

        if total > 0:
            pct = min(100.0, (done / total) * 100.0)
            self.transfer_progress_var.set(pct)

        self._transfer_stat_labels["files"].configure(
            text=f"{done}/{total} ({stats.get('files_copied', 0)} new, {stats.get('files_skipped', 0)} skip)"
        )

        bt = stats.get("bytes_transferred", 0)
        bt_total = stats.get("bytes_total", 0)
        self._transfer_stat_labels["bytes"].configure(
            text=f"{bt / 1024**2:.0f} / {bt_total / 1024**2:.0f} MB"
        )

        elapsed = stats.get("elapsed_seconds", 0)
        if elapsed > 0 and done > 0:
            speed_mb = bt / elapsed / 1024**2
            self._transfer_stat_labels["speed"].configure(text=f"{speed_mb:.1f} MB/s")
            remaining = total - done
            rate = done / elapsed
            if rate > 0 and remaining > 0:
                eta = _format_elapsed(remaining / rate)
                self._transfer_stat_labels["eta"].configure(text=eta)
            else:
                self._transfer_stat_labels["eta"].configure(text="--")
        current = stats.get("current_file", "")
        if len(current) > 35:
            current = "..." + current[-32:]
        self._transfer_stat_labels["current"].configure(text=current or "--")

        self.transfer_status_label.configure(text=f"{done}/{total}")

    def transfer_finished(self, stats: dict, message: str = ""):
        """Called when bulk transfer completes."""
        self.update_transfer_stats(stats)
        self._running = False
        self.transfer_start_btn.configure(state=tk.NORMAL)
        self.transfer_stop_btn.configure(state=tk.DISABLED)
        self.transfer_progress_var.set(100.0)
        self.transfer_status_label.configure(text="Done")
        if message and self._append_log:
            self._append_log(message, "INFO")
