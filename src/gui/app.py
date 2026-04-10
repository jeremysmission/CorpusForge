# ============================================================================
# CorpusForge -- Main GUI Application (src/gui/app.py)
# ============================================================================
# Tkinter GUI for monitoring and controlling the CorpusForge pipeline.
# Panels: Pipeline Control, Live Stats, Log Output, Status Bar.
# Thread-safe: all widget updates routed through safe_after.
# ============================================================================

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, filedialog

from .theme import (
    DARK, FONT, FONT_TITLE, FONT_SMALL,
    FONT_MONO, apply_ttk_styles, current_theme,
)
from .safe_after import safe_after
from .transfer_panel import TransferPanel
from .dedup_only_panel import DedupOnlyPanel
from .settings_panel import SettingsPanel
from .stats_panel import StatsPanel

logger = logging.getLogger(__name__)

# Maximum log lines retained in the text widget
_MAX_LOG_LINES = 2000


class CorpusForgeApp:
    """Main CorpusForge GUI window."""

    def __init__(
        self,
        root: tk.Tk,
        config_path: str = "",
        config=None,
        supported_formats: int = 0,
        skip_list_count: int = 0,
        enrichment_enabled: bool = False,
        on_start=None,
        on_stop=None,
        on_save_settings=None,
        on_precheck=None,
        on_transfer_start=None,
        on_transfer_stop=None,
        on_dedup_only_start=None,
        on_dedup_only_stop=None,
    ):
        self.root = root
        self.config_path = config_path
        self._config = config
        self.supported_formats = supported_formats
        self.skip_list_count = skip_list_count
        self.enrichment_enabled = enrichment_enabled
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_save_settings = on_save_settings
        self._on_precheck = on_precheck
        self._on_transfer_start = on_transfer_start
        self._on_transfer_stop = on_transfer_stop
        self._on_dedup_only_start = on_dedup_only_start
        self._on_dedup_only_stop = on_dedup_only_stop
        self._running = False
        self._mousewheel_bound = False

        self._setup_window()
        apply_ttk_styles(DARK)
        self._build_ui()
        self._update_status_bar()

    # ------------------------------------------------------------------
    # Settings var delegation (tests and _on_start_click access these)
    # ------------------------------------------------------------------

    @property
    def workers_var(self):
        return self._settings_panel.workers_var

    @property
    def chunk_size_var(self):
        return self._settings_panel.chunk_size_var

    @property
    def overlap_var(self):
        return self._settings_panel.overlap_var

    @property
    def ocr_var(self):
        return self._settings_panel.ocr_var

    @property
    def embed_var(self):
        return self._settings_panel.embed_var

    @property
    def enrich_var(self):
        return self._settings_panel.enrich_var

    @property
    def extract_var(self):
        return self._settings_panel.extract_var

    @property
    def enrich_concurrent_var(self):
        return self._settings_panel.enrich_concurrent_var

    @property
    def extract_batch_var(self):
        return self._settings_panel.extract_batch_var

    @property
    def embed_batch_var(self):
        return self._settings_panel.embed_batch_var

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self):
        t = current_theme()
        self.root.title("CorpusForge Pipeline Monitor")
        self.root.geometry("920x760")
        self.root.minsize(760, 600)
        self.root.configure(bg=t["bg"])
        # Set window icon if available
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        t = current_theme()

        shell = ttk.Frame(self.root)
        shell.pack(fill=tk.BOTH, expand=True)

        content_shell = ttk.Frame(shell)
        content_shell.pack(fill=tk.BOTH, expand=True)

        self._scroll_canvas = tk.Canvas(
            content_shell,
            bg=t["bg"],
            highlightthickness=0,
            bd=0,
        )
        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._scrollbar = ttk.Scrollbar(
            content_shell,
            orient=tk.VERTICAL,
            command=self._scroll_canvas.yview,
        )
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)

        main = ttk.Frame(self._scroll_canvas, padding=10)
        self._scroll_window = self._scroll_canvas.create_window(
            (0, 0), window=main, anchor=tk.NW
        )
        main.bind("<Configure>", self._on_scroll_content_configure)
        self._scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self._scroll_canvas.bind("<Enter>", self._bind_mousewheel)
        self._scroll_canvas.bind("<Leave>", self._unbind_mousewheel)

        # Title
        title_lbl = tk.Label(
            main, text="CorpusForge Pipeline Monitor",
            font=FONT_TITLE, bg=t["bg"], fg=t["accent"],
        )
        title_lbl.pack(anchor=tk.W, pady=(0, 8))

        # -- Transfer Panel --
        transfer_frame = ttk.LabelFrame(main, text="Bulk Transfer", padding=8)
        transfer_frame.pack(fill=tk.X, pady=(0, 6))

        self._transfer_panel = TransferPanel(
            transfer_frame, self.root,
            on_transfer_start=self._on_transfer_start,
            on_transfer_stop=self._on_transfer_stop,
            append_log=self.append_log,
        )

        # -- Pipeline Control Panel --
        ctrl_frame = ttk.LabelFrame(main, text="Pipeline Control", padding=8)
        ctrl_frame.pack(fill=tk.X, pady=(0, 6))

        self._build_control_panel(ctrl_frame, t)

        # -- Settings Panel --
        settings_frame = ttk.LabelFrame(main, text="Settings", padding=8)
        settings_frame.pack(fill=tk.X, pady=(0, 6))

        self._settings_panel = SettingsPanel(
            settings_frame, self.root, config=self._config,
            config_path=self.config_path,
            on_save_settings=self._on_save_settings,
            append_log=self.append_log,
        )

        # -- Dedup-Only Panel --
        dedup_only_frame = ttk.LabelFrame(main, text="Dedup-Only Pass", padding=8)
        dedup_only_frame.pack(fill=tk.X, pady=(0, 6))

        self._dedup_only_panel = DedupOnlyPanel(
            dedup_only_frame, self.root,
            on_dedup_only_start=self._on_dedup_only_start,
            on_dedup_only_stop=self._on_dedup_only_stop,
            append_log=self.append_log,
            default_output=self._config.paths.output_dir if self._config is not None else "data/output",
        )

        # -- Live Stats Panel --
        stats_frame = ttk.LabelFrame(main, text="Live Stats", padding=8)
        stats_frame.pack(fill=tk.X, pady=(0, 6))

        self._stats_panel = StatsPanel(
            stats_frame, self.root,
            progress_var=self.progress_var,
            progress_label=self.progress_label,
        )

        # -- Log Panel --
        log_frame = ttk.LabelFrame(main, text="Pipeline Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self._build_log_panel(log_frame, t)

        # -- Status Bar --
        self._build_status_bar(shell, t)

    def _build_control_panel(self, parent, t):
        """Source/output paths, start/stop buttons, progress bar."""
        # Row 0: Source folder
        row0 = ttk.Frame(parent)
        row0.pack(fill=tk.X, pady=2)

        tk.Label(row0, text="Source:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], width=8, anchor=tk.W).pack(side=tk.LEFT)

        self.source_var = tk.StringVar(value="data/source")
        self.source_entry = tk.Entry(
            row0, textvariable=self.source_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
            relief=tk.FLAT, bd=2,
        )
        self.source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        self.browse_src_btn = ttk.Button(
            row0, text="Browse", command=self._browse_source,
        )
        self.browse_src_btn.pack(side=tk.RIGHT)

        # Row 1: Output folder
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=2)

        tk.Label(row1, text="Output:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], width=8, anchor=tk.W).pack(side=tk.LEFT)

        self.output_var = tk.StringVar(value="data/output")
        self.output_entry = tk.Entry(
            row1, textvariable=self.output_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
            relief=tk.FLAT, bd=2,
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        self.browse_out_btn = ttk.Button(
            row1, text="Browse", command=self._browse_output,
        )
        self.browse_out_btn.pack(side=tk.RIGHT)

        # Row 2: Buttons + progress bar
        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(6, 2))

        self.start_btn = ttk.Button(
            row2, text="Start Pipeline", style="Accent.TButton",
            command=self._on_start_click,
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.precheck_btn = ttk.Button(
            row2, text="Run Precheck", style="Tertiary.TButton",
            command=self._on_precheck_click,
        )
        self.precheck_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(
            row2, text="Stop Safely", style="Tertiary.TButton",
            command=self._on_stop_click, state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            row2, variable=self.progress_var, maximum=100,
            mode="determinate", length=300,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.progress_label = tk.Label(
            row2, text="0 / 0", font=FONT_SMALL,
            bg=t["panel_bg"], fg=t["label_fg"],
        )
        self.progress_label.pack(side=tk.RIGHT)

    # _build_stats_panel extracted to StatsPanel

    def _build_log_panel(self, parent, t):
        """Scrolling text area for pipeline log output."""
        log_container = ttk.Frame(parent)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_container, font=FONT_MONO, bg=t["bg"], fg=t["fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2,
            wrap=tk.WORD, state=tk.DISABLED, height=12,
        )
        scrollbar = ttk.Scrollbar(
            log_container, orient=tk.VERTICAL, command=self.log_text.yview,
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Color tags for log levels
        self.log_text.tag_configure("INFO", foreground=t["fg"])
        self.log_text.tag_configure("WARNING", foreground=t["orange"])
        self.log_text.tag_configure("ERROR", foreground=t["red"])
        self.log_text.tag_configure("DEBUG", foreground=t["gray"])

    def _build_status_bar(self, parent, t):
        """Bottom status bar with config info."""
        bar = tk.Frame(parent, bg=t["panel_bg"], height=28)
        bar.pack(fill=tk.X, pady=(2, 0))

        self._status_labels = {}
        items = [
            ("config", f"Config: {self.config_path}"),
            ("formats", f"Formats: {self.supported_formats}"),
            ("skip", f"Skip list: {self.skip_list_count} deferred"),
            ("workers", f"Pipeline workers: {self._current_worker_count()} logical threads"),
            ("enrich", f"Enrichment: {'enabled' if self.enrichment_enabled else 'disabled'}"),
        ]
        for key, text in items:
            lbl = tk.Label(
                bar, text=text, font=FONT_SMALL, bg=t["panel_bg"],
                fg=t["label_fg"], padx=12,
            )
            lbl.pack(side=tk.LEFT)
            self._status_labels[key] = lbl

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _browse_source(self):
        path = filedialog.askdirectory(title="Select Source Folder")
        if path:
            self.source_var.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_var.set(path)

    def _on_start_click(self):
        if self._running:
            return

        # Ollama health probe — if enrichment is enabled, verify Ollama is ready
        if self._settings_panel.enrich_var.get():
            from src.enrichment.contextual_enricher import probe_enrichment
            ollama_url = "http://127.0.0.1:11434"
            model = "phi4:14b-q4_K_M"
            if self._config is not None:
                ollama_url = self._config.enrich.ollama_url
                model = self._config.enrich.model

            self.append_log("Probing Ollama for enrichment readiness...", "INFO")
            probe = probe_enrichment(
                ollama_url=ollama_url, model=model, auto_start=True,
            )
            if not probe.ready:
                from tkinter import messagebox
                choice = messagebox.askyesnocancel(
                    "Enrichment Unavailable",
                    f"Ollama enrichment is not ready:\n{probe.status_text}\n\n"
                    "Yes = Continue without enrichment\n"
                    "No = Retry probe\n"
                    "Cancel = Abort",
                )
                if choice is None:  # Cancel
                    return
                if choice is False:  # No = Retry
                    probe = probe_enrichment(
                        ollama_url=ollama_url, model=model, auto_start=True,
                        start_timeout=30,
                    )
                    if not probe.ready:
                        messagebox.showwarning(
                            "Still Unavailable",
                            f"Ollama still not ready: {probe.status_text}\n\n"
                            "Continuing without enrichment.",
                        )
                        self._settings_panel.enrich_var.set(False)
                if choice is True:  # Yes = Continue without
                    self._settings_panel.enrich_var.set(False)
            else:
                self.append_log(
                    f"Ollama ready: {model}"
                    + (" (auto-started)" if probe.auto_started else ""),
                    "INFO",
                )

        self._set_running(True)
        if self._on_start:
            self._on_start(
                source=self.source_var.get(),
                output=self.output_var.get(),
            )

    def _on_stop_click(self):
        if self._on_stop:
            self._on_stop()
        self.stop_btn.configure(state=tk.DISABLED, text="Stopping...")
        self.update_stage_progress(
            "stopping",
            0,
            0,
            "Finishing in-flight file/stage, then packaging completed work.",
        )
        self.append_log(
            "Safe stop requested. CorpusForge will not admit new files, will finish in-flight work, then package completed output.",
            "WARNING",
        )

    def _on_precheck_click(self):
        if self._on_precheck:
            self._on_precheck(
                source=self.source_var.get(),
                output=self.output_var.get(),
                settings=self._collect_current_settings(),
            )

    def _on_scroll_content_configure(self, _event=None):
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _on_scroll_canvas_configure(self, event):
        self._scroll_canvas.itemconfigure(self._scroll_window, width=event.width)

    def _bind_mousewheel(self, _event=None):
        if not self._mousewheel_bound:
            self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
            self._mousewheel_bound = True

    def _unbind_mousewheel(self, _event=None):
        if self._mousewheel_bound:
            self.root.unbind_all("<MouseWheel>")
            self._mousewheel_bound = False

    def _on_mousewheel(self, event):
        self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _set_running(self, running: bool):
        self._running = running
        if running:
            self.start_btn.configure(state=tk.DISABLED)
            self.precheck_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL, text="Stop Safely")
            self.browse_src_btn.configure(state=tk.DISABLED)
            self.browse_out_btn.configure(state=tk.DISABLED)
            self.source_entry.configure(state=tk.DISABLED)
            self.output_entry.configure(state=tk.DISABLED)
            self._stats_panel.start_timer()
        else:
            self.start_btn.configure(state=tk.NORMAL)
            self.precheck_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED, text="Stop Safely")
            self.browse_src_btn.configure(state=tk.NORMAL)
            self.browse_out_btn.configure(state=tk.NORMAL)
            self.source_entry.configure(state=tk.NORMAL)
            self.output_entry.configure(state=tk.NORMAL)
            self._stats_panel.stop_timer()

    # ------------------------------------------------------------------
    # Public update methods (called via safe_after from bg thread)
    # ------------------------------------------------------------------

    def update_stats(self, stats: dict):
        self._stats_panel.update_stats(stats)

    def update_stage_progress(self, stage: str, current: int, total: int, detail: str = ""):
        self._stats_panel.update_stage_progress(stage, current, total, detail)

    def update_current_file(self, filename: str):
        self._stats_panel.update_current_file(filename)

    def update_transfer_stats(self, stats: dict):
        self._transfer_panel.update_transfer_stats(stats)

    def transfer_finished(self, stats: dict, message: str = ""):
        self._transfer_panel.transfer_finished(stats, message)

    def update_dedup_only_stats(self, stats: dict):
        self._dedup_only_panel.update_dedup_only_stats(stats)

    def dedup_only_finished(self, stats: dict, message: str = ""):
        self._dedup_only_panel.dedup_only_finished(stats, message)

    def append_log(self, message: str, level: str = "INFO"):
        """Append a line to the log panel with color coding."""
        tag = level if level in ("INFO", "WARNING", "ERROR", "DEBUG") else "INFO"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", tag)

        # Trim old lines
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > _MAX_LOG_LINES:
            self.log_text.delete("1.0", f"{line_count - _MAX_LOG_LINES}.0")

        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def pipeline_finished(self, stats: dict):
        """Called when pipeline completes (success or error)."""
        self.update_stats(stats)
        self._set_running(False)
        self._stats_panel.finalize(stats)

        elapsed = stats.get("elapsed_seconds", 0)
        parsed = stats.get("files_parsed", 0)
        failed = stats.get("files_failed", 0)
        skipped = stats.get("files_skipped", 0)
        if stats.get("stop_requested"):
            export_dir = stats.get("export_dir") or ""
            if export_dir:
                self.append_log(
                    f"Pipeline stopped cleanly: {parsed} parsed, {failed} failed, "
                    f"{skipped} skipped in {elapsed:.1f}s. "
                    f"Completed work was packaged at {export_dir}; remaining files stay resumable.",
                    "WARNING",
                )
            else:
                self.append_log(
                    f"Pipeline stopped cleanly: {parsed} parsed, {failed} failed, "
                    f"{skipped} skipped in {elapsed:.1f}s. "
                    f"No export was written (stop fired before any packageable work was ready); "
                    f"hashed files stay resumable on the next run.",
                    "WARNING",
                )
        else:
            self.append_log(
                f"Pipeline complete: {parsed} parsed, {failed} failed, "
                f"{skipped} skipped in {elapsed:.1f}s",
                "INFO",
            )

    def _update_status_bar(self):
        """Refresh status bar labels with current config info."""
        t = current_theme()
        enrich_text = "enabled" if self.enrichment_enabled else "disabled"
        enrich_fg = t["green"] if self.enrichment_enabled else t["gray"]

        self._status_labels["config"].configure(
            text=f"Config: {self.config_path}",
        )
        self._status_labels["formats"].configure(
            text=f"Formats: {self.supported_formats}",
        )
        self._status_labels["skip"].configure(
            text=f"Skip list: {self.skip_list_count} deferred",
        )
        self._status_labels["workers"].configure(
            text=f"Pipeline workers: {self._current_worker_count()} logical threads",
        )
        self._status_labels["enrich"].configure(
            text=f"Enrichment: {enrich_text}", fg=enrich_fg,
        )

    def update_enrichment_status(self, status: str, color: str = "gray"):
        """Update the enrichment status indicator in the status bar.

        Args:
            status: Human-readable status text (e.g. "ready", "Ollama not running")
            color: Theme color key — "green", "orange", "red", "gray"
        """
        t = current_theme()
        fg = t.get(color, t["gray"])
        self._status_labels["enrich"].configure(
            text=f"Enrichment: {status}", fg=fg,
        )

    def update_worker_status(self, workers: int | None = None):
        """Refresh the worker indicator after a settings change."""
        if workers is not None and self._config is not None:
            self._config.pipeline.workers = workers
        self._update_status_bar()

    def _current_worker_count(self) -> int:
        if hasattr(self, "_settings_panel"):
            try:
                return int(self._settings_panel.workers_var.get())
            except Exception:
                pass
        if self._config is not None:
            return int(self._config.pipeline.workers)
        return 0

    def _collect_current_settings(self) -> dict:
        return {
            "pipeline": {"workers": int(self.workers_var.get())},
            "parse": {"ocr_mode": str(self.ocr_var.get())},
            "embed": {"enabled": bool(self.embed_var.get())},
            "enrich": {"enabled": bool(self.enrich_var.get())},
            "extract": {"enabled": bool(self.extract_var.get())},
            "hardware": {"embed_batch_size": int(self.embed_batch_var.get())},
        }
