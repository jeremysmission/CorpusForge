# ============================================================================
# CorpusForge -- Main GUI Application (src/gui/app.py)
# ============================================================================
# Tkinter GUI for monitoring and controlling the CorpusForge pipeline.
# Panels: Pipeline Control, Live Stats, Log Output, Status Bar.
# Thread-safe: all widget updates routed through safe_after.
# ============================================================================

from __future__ import annotations

import logging
import time
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from typing import Optional

from .theme import (
    DARK, FONT, FONT_BOLD, FONT_TITLE, FONT_SECTION, FONT_SMALL,
    FONT_MONO, apply_ttk_styles, current_theme,
)
from .safe_after import safe_after

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
        self._on_transfer_start = on_transfer_start
        self._on_transfer_stop = on_transfer_stop
        self._on_dedup_only_start = on_dedup_only_start
        self._on_dedup_only_stop = on_dedup_only_stop
        self._running = False
        self._transfer_running = False
        self._dedup_only_running = False
        self._start_time: Optional[float] = None
        self._timer_id: Optional[str] = None

        self._setup_window()
        apply_ttk_styles(DARK)
        self._build_ui()
        self._update_status_bar()

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

        # Main container
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # Title
        title_lbl = tk.Label(
            main, text="CorpusForge Pipeline Monitor",
            font=FONT_TITLE, bg=t["bg"], fg=t["accent"],
        )
        title_lbl.pack(anchor=tk.W, pady=(0, 8))

        # -- Transfer Panel --
        transfer_frame = ttk.LabelFrame(main, text="Bulk Transfer", padding=8)
        transfer_frame.pack(fill=tk.X, pady=(0, 6))

        self._build_transfer_panel(transfer_frame, t)

        # -- Pipeline Control Panel --
        ctrl_frame = ttk.LabelFrame(main, text="Pipeline Control", padding=8)
        ctrl_frame.pack(fill=tk.X, pady=(0, 6))

        self._build_control_panel(ctrl_frame, t)

        # -- Settings Panel --
        settings_frame = ttk.LabelFrame(main, text="Settings", padding=8)
        settings_frame.pack(fill=tk.X, pady=(0, 6))

        self._build_settings_panel(settings_frame, t)

        # -- Dedup-Only Panel --
        dedup_only_frame = ttk.LabelFrame(main, text="Dedup-Only Pass", padding=8)
        dedup_only_frame.pack(fill=tk.X, pady=(0, 6))

        self._build_dedup_only_panel(dedup_only_frame, t)

        # -- Live Stats Panel --
        stats_frame = ttk.LabelFrame(main, text="Live Stats", padding=8)
        stats_frame.pack(fill=tk.X, pady=(0, 6))

        self._build_stats_panel(stats_frame, t)

        # -- Log Panel --
        log_frame = ttk.LabelFrame(main, text="Pipeline Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self._build_log_panel(log_frame, t)

        # -- Status Bar --
        self._build_status_bar(main, t)

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

        self.stop_btn = ttk.Button(
            row2, text="Stop", style="Tertiary.TButton",
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

    def _build_settings_panel(self, parent, t):
        """Pipeline settings: workers, toggles, chunk params. Changes saved to config."""
        # Row 0: Workers + OCR mode
        row0 = ttk.Frame(parent)
        row0.pack(fill=tk.X, pady=2)

        tk.Label(row0, text="Workers:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], anchor=tk.W).pack(side=tk.LEFT)

        workers_default = 8
        if self._config is not None:
            workers_default = self._config.pipeline.workers
        self.workers_var = tk.IntVar(value=workers_default)
        self.workers_spin = tk.Spinbox(
            row0, from_=1, to=32, textvariable=self.workers_var,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2, width=4,
            buttonbackground=t["panel_bg"],
        )
        self.workers_spin.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(row0, text="OCR:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], anchor=tk.W).pack(side=tk.LEFT)

        ocr_default = "auto"
        if self._config is not None:
            ocr_default = self._config.parse.ocr_mode
        self.ocr_var = tk.StringVar(value=ocr_default)
        self.ocr_combo = ttk.Combobox(
            row0, textvariable=self.ocr_var, values=["skip", "auto", "force"],
            state="readonly", width=6,
        )
        self.ocr_combo.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(row0, text="Chunk size:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], anchor=tk.W).pack(side=tk.LEFT)

        chunk_size_default = 1200
        if self._config is not None:
            chunk_size_default = self._config.chunk.size
        self.chunk_size_var = tk.IntVar(value=chunk_size_default)
        self.chunk_size_spin = tk.Spinbox(
            row0, from_=100, to=10000, increment=100,
            textvariable=self.chunk_size_var,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2, width=6,
            buttonbackground=t["panel_bg"],
        )
        self.chunk_size_spin.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(row0, text="Overlap:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], anchor=tk.W).pack(side=tk.LEFT)

        overlap_default = 200
        if self._config is not None:
            overlap_default = self._config.chunk.overlap
        self.overlap_var = tk.IntVar(value=overlap_default)
        self.overlap_spin = tk.Spinbox(
            row0, from_=0, to=2000, increment=50,
            textvariable=self.overlap_var,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2, width=5,
            buttonbackground=t["panel_bg"],
        )
        self.overlap_spin.pack(side=tk.LEFT, padx=(4, 0))

        # Row 1: Toggles + Save button
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=(4, 2))

        embed_default = True
        enrich_default = True
        extract_default = False
        if self._config is not None:
            embed_default = self._config.embed.enabled
            enrich_default = self._config.enrich.enabled
            extract_default = self._config.extract.enabled

        self.embed_var = tk.BooleanVar(value=embed_default)
        self.embed_chk = ttk.Checkbutton(
            row1, text="Embedding", variable=self.embed_var,
        )
        self.embed_chk.pack(side=tk.LEFT, padx=(0, 12))

        self.enrich_var = tk.BooleanVar(value=enrich_default)
        self.enrich_chk = ttk.Checkbutton(
            row1, text="Enrichment", variable=self.enrich_var,
        )
        self.enrich_chk.pack(side=tk.LEFT, padx=(0, 12))

        self.extract_var = tk.BooleanVar(value=extract_default)
        self.extract_chk = ttk.Checkbutton(
            row1, text="Entity Extraction", variable=self.extract_var,
        )
        self.extract_chk.pack(side=tk.LEFT, padx=(0, 12))

        # Row 2: Batch/concurrency controls
        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(4, 2))

        enrich_concurrent_default = 2
        extract_batch_default = 16
        embed_batch_default = 256
        if self._config is not None:
            enrich_concurrent_default = self._config.enrich.max_concurrent
            extract_batch_default = self._config.extract.batch_size
            embed_batch_default = self._config.hardware.embed_batch_size

        tk.Label(row2, text="Enrich concurrent:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], anchor=tk.W).pack(side=tk.LEFT)
        self.enrich_concurrent_var = tk.IntVar(value=enrich_concurrent_default)
        tk.Spinbox(
            row2, from_=1, to=8, textvariable=self.enrich_concurrent_var,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2, width=3,
            buttonbackground=t["panel_bg"],
        ).pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(row2, text="Extract batch:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], anchor=tk.W).pack(side=tk.LEFT)
        self.extract_batch_var = tk.IntVar(value=extract_batch_default)
        tk.Spinbox(
            row2, from_=1, to=128, textvariable=self.extract_batch_var,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2, width=4,
            buttonbackground=t["panel_bg"],
        ).pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(row2, text="Embed batch:", font=FONT, bg=t["panel_bg"],
                 fg=t["label_fg"], anchor=tk.W).pack(side=tk.LEFT)
        self.embed_batch_var = tk.IntVar(value=embed_batch_default)
        tk.Spinbox(
            row2, from_=1, to=1024, increment=32, textvariable=self.embed_batch_var,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2, width=5,
            buttonbackground=t["panel_bg"],
        ).pack(side=tk.LEFT, padx=(4, 12))

        self.save_settings_btn = ttk.Button(
            row2, text="Save Settings", style="Tertiary.TButton",
            command=self._handle_save_settings,
        )
        self.save_settings_btn.pack(side=tk.RIGHT)

        self.reset_defaults_btn = ttk.Button(
            row2, text="Reset to Defaults",
            command=self._handle_reset_defaults,
        )
        self.reset_defaults_btn.pack(side=tk.RIGHT, padx=(0, 6))

    def _handle_save_settings(self):
        """Collect current settings, validate, and invoke the save callback."""
        # Debounce: ignore rapid clicks within 500ms
        now = time.time()
        if hasattr(self, "_last_save_time") and (now - self._last_save_time) < 0.5:
            return
        self._last_save_time = now
        # Validate all numeric fields — reject invalid values with error dialog
        validations = [
            ("Workers", self.workers_var, 1, 32),
            ("Chunk size", self.chunk_size_var, 100, 10000),
            ("Overlap", self.overlap_var, 0, 2000),
            ("Enrich concurrent", self.enrich_concurrent_var, 1, 8),
            ("Extract batch", self.extract_batch_var, 1, 128),
            ("Embed batch", self.embed_batch_var, 1, 1024),
        ]
        errors = []
        for label, var, lo, hi in validations:
            try:
                val = var.get()
                if val < lo or val > hi:
                    errors.append(f"{label}: must be {lo}-{hi} (got {val})")
            except (tk.TclError, ValueError):
                errors.append(f"{label}: invalid number")

        if errors:
            from tkinter import messagebox
            messagebox.showerror(
                "Invalid Settings",
                "Fix these before saving:\n\n" + "\n".join(errors),
            )
            self.append_log(f"Settings NOT saved — validation errors: {'; '.join(errors)}", "ERROR")
            return

        settings = {
            "pipeline": {"workers": self.workers_var.get()},
            "parse": {"ocr_mode": self.ocr_var.get()},
            "chunk": {
                "size": self.chunk_size_var.get(),
                "overlap": self.overlap_var.get(),
            },
            "embed": {"enabled": self.embed_var.get()},
            "enrich": {
                "enabled": self.enrich_var.get(),
                "max_concurrent": self.enrich_concurrent_var.get(),
            },
            "extract": {
                "enabled": self.extract_var.get(),
                "batch_size": self.extract_batch_var.get(),
            },
            "hardware": {"embed_batch_size": self.embed_batch_var.get()},
        }
        if self._on_save_settings:
            self._on_save_settings(settings)
        self.append_log(
            f"Settings saved: workers={settings['pipeline']['workers']}, "
            f"OCR={settings['parse']['ocr_mode']}, "
            f"chunk={settings['chunk']['size']}/{settings['chunk']['overlap']}, "
            f"embed={'ON' if settings['embed']['enabled'] else 'OFF'}, "
            f"enrich={'ON' if settings['enrich']['enabled'] else 'OFF'}, "
            f"extract={'ON' if settings['extract']['enabled'] else 'OFF'}",
            "INFO",
        )

    def _handle_reset_defaults(self):
        """Reset all settings controls to base config.yaml values (ignoring local overrides)."""
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Reset to Defaults",
            "Reset all settings to config.yaml defaults?\n\n"
            "This does not change config files — only resets the GUI controls.\n"
            "Click Save Settings after to persist.",
        ):
            return

        # Read base config only (no local overrides)
        try:
            import yaml
            from pathlib import Path
            config_path = Path(self.config_path) if self.config_path else Path("config/config.yaml")
            if not config_path.is_absolute():
                from src.config.schema import PROJECT_ROOT
                config_path = PROJECT_ROOT / config_path
            with open(config_path, encoding="utf-8-sig") as f:
                raw = yaml.safe_load(f) or {}

            self.workers_var.set(raw.get("pipeline", {}).get("workers", 8))
            self.ocr_var.set(raw.get("parse", {}).get("ocr_mode", "auto"))
            self.chunk_size_var.set(raw.get("chunk", {}).get("size", 1200))
            self.overlap_var.set(raw.get("chunk", {}).get("overlap", 200))
            self.embed_var.set(raw.get("embed", {}).get("enabled", True))
            self.enrich_var.set(raw.get("enrich", {}).get("enabled", True))
            self.extract_var.set(raw.get("extract", {}).get("enabled", False))
            self.enrich_concurrent_var.set(raw.get("enrich", {}).get("max_concurrent", 2))
            self.extract_batch_var.set(raw.get("extract", {}).get("batch_size", 16))
            self.embed_batch_var.set(raw.get("hardware", {}).get("embed_batch_size", 256))

            self.append_log("Settings reset to config.yaml defaults. Click Save to persist.", "INFO")
        except Exception as exc:
            self.append_log(f"Failed to reset defaults: {exc}", "ERROR")

    def _build_transfer_panel(self, parent, t):
        """Bulk Transfer: source path, start/stop, live progress."""
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
            command=self._on_transfer_start_click,
        )
        self.transfer_start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.transfer_stop_btn = ttk.Button(
            row2, text="Stop", style="Tertiary.TButton",
            command=self._on_transfer_stop_click, state=tk.DISABLED,
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

    def _build_dedup_only_panel(self, parent, t):
        """Dedup-only mode: run dedup without embed/enrich/extract."""
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
        row1.pack(fill=tk.X, pady=(6, 2))

        self.dedup_only_start_btn = ttk.Button(
            row1, text="Run Dedup Only", style="Accent.TButton",
            command=self._on_dedup_only_start_click,
        )
        self.dedup_only_start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.dedup_only_stop_btn = ttk.Button(
            row1, text="Stop", style="Tertiary.TButton",
            command=self._on_dedup_only_stop_click, state=tk.DISABLED,
        )
        self.dedup_only_stop_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.dedup_only_progress_var = tk.DoubleVar(value=0.0)
        self.dedup_only_progress_bar = ttk.Progressbar(
            row1, variable=self.dedup_only_progress_var, maximum=100,
            mode="determinate", length=250,
        )
        self.dedup_only_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.dedup_only_status_label = tk.Label(
            row1, text="Idle", font=FONT_SMALL,
            bg=t["panel_bg"], fg=t["label_fg"],
        )
        self.dedup_only_status_label.pack(side=tk.RIGHT)

        # Dedup stats row
        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=2)

        self._dedup_only_stat_labels = {}
        for key, label_text in [
            ("scanned", "Scanned:"), ("duplicates", "Duplicates:"),
            ("current", "Current:"), ("elapsed", "Elapsed:"), ("eta", "ETA:"),
        ]:
            tk.Label(row2, text=label_text, font=FONT_SMALL, bg=t["panel_bg"],
                     fg=t["label_fg"]).pack(side=tk.LEFT, padx=(0, 2))
            val = tk.Label(row2, text="--", font=FONT_SMALL, bg=t["panel_bg"],
                           fg=t["fg"])
            val.pack(side=tk.LEFT, padx=(0, 10))
            self._dedup_only_stat_labels[key] = val

    def _build_stats_panel(self, parent, t):
        """Two-column grid of live statistics."""
        # Left column
        left = ttk.Frame(parent)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Right column
        right = ttk.Frame(parent)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Stat labels -- left column
        self._stat_labels = {}
        left_stats = [
            ("files_scanned", "Files scanned:"),
            ("files_parsed", "Files parsed:"),
            ("files_skipped", "Files skipped:"),
            ("files_failed", "Files failed:"),
            ("chunks_created", "Chunks created:"),
            ("chunks_enriched", "Chunks enriched:"),
        ]
        for key, label_text in left_stats:
            row = ttk.Frame(left)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=FONT, bg=t["panel_bg"],
                     fg=t["label_fg"], width=18, anchor=tk.W).pack(side=tk.LEFT)
            val = tk.Label(row, text="0", font=FONT_BOLD, bg=t["panel_bg"],
                           fg=t["fg"], anchor=tk.W)
            val.pack(side=tk.LEFT)
            self._stat_labels[key] = val

        # Right column stats
        right_stats = [
            ("current_file", "Current file:"),
            ("elapsed", "Elapsed time:"),
            ("throughput", "Throughput:"),
            ("eta", "ETA:"),
            ("skip_reasons", "Skip reasons:"),
            ("vectors_created", "Vectors created:"),
        ]
        for key, label_text in right_stats:
            row = ttk.Frame(right)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=FONT, bg=t["panel_bg"],
                     fg=t["label_fg"], width=16, anchor=tk.W).pack(side=tk.LEFT)
            val = tk.Label(row, text="--", font=FONT_BOLD, bg=t["panel_bg"],
                           fg=t["fg"], anchor=tk.W, wraplength=320)
            val.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._stat_labels[key] = val

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

    def _browse_transfer_source(self):
        path = filedialog.askdirectory(title="Select Transfer Source")
        if path:
            self.transfer_src_var.set(path)

    def _browse_transfer_dest(self):
        path = filedialog.askdirectory(title="Select Transfer Destination")
        if path:
            self.transfer_dest_var.set(path)

    def _browse_into(self, var, title):
        path = filedialog.askdirectory(title=title)
        if path:
            var.set(path)

    def _on_transfer_start_click(self):
        if self._transfer_running:
            return
        self._transfer_running = True
        self.transfer_start_btn.configure(state=tk.DISABLED)
        self.transfer_stop_btn.configure(state=tk.NORMAL)
        if self._on_transfer_start:
            self._on_transfer_start(
                source=self.transfer_src_var.get(),
                dest=self.transfer_dest_var.get(),
            )

    def _on_transfer_stop_click(self):
        if self._on_transfer_stop:
            self._on_transfer_stop()
        self.append_log("Transfer stop requested.", "WARNING")

    def _on_dedup_only_start_click(self):
        if self._dedup_only_running:
            return
        self._dedup_only_running = True
        self.dedup_only_start_btn.configure(state=tk.DISABLED)
        self.dedup_only_stop_btn.configure(state=tk.NORMAL)
        if self._on_dedup_only_start:
            self._on_dedup_only_start(source=self.dedup_only_src_var.get())

    def _on_dedup_only_stop_click(self):
        if self._on_dedup_only_stop:
            self._on_dedup_only_stop()
        self.append_log("Dedup-only stop requested.", "WARNING")

    def _on_start_click(self):
        if self._running:
            return

        # Ollama health probe — if enrichment is enabled, verify Ollama is ready
        if self.enrich_var.get():
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
                        self.enrich_var.set(False)
                if choice is True:  # Yes = Continue without
                    self.enrich_var.set(False)
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
        self.append_log("Pipeline stop requested by user.", "WARNING")

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _set_running(self, running: bool):
        self._running = running
        if running:
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.browse_src_btn.configure(state=tk.DISABLED)
            self.browse_out_btn.configure(state=tk.DISABLED)
            self.source_entry.configure(state=tk.DISABLED)
            self.output_entry.configure(state=tk.DISABLED)
            self._start_time = time.time()
            self._start_elapsed_timer()
        else:
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)
            self.browse_src_btn.configure(state=tk.NORMAL)
            self.browse_out_btn.configure(state=tk.NORMAL)
            self.source_entry.configure(state=tk.NORMAL)
            self.output_entry.configure(state=tk.NORMAL)
            self._stop_elapsed_timer()

    def _start_elapsed_timer(self):
        """Update elapsed time label every second while running."""
        if not self._running or self._start_time is None:
            return
        elapsed = time.time() - self._start_time
        self._stat_labels["elapsed"].configure(text=_format_elapsed(elapsed))
        self._timer_id = self.root.after(1000, self._start_elapsed_timer)

    def _stop_elapsed_timer(self):
        if self._timer_id is not None:
            try:
                self.root.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None

    # ------------------------------------------------------------------
    # Public update methods (called via safe_after from bg thread)
    # ------------------------------------------------------------------

    def update_stats(self, stats: dict):
        """Update the live stats panel from a stats dictionary."""
        total = stats.get("files_found", 0)
        parsed = stats.get("files_parsed", 0)
        failed = stats.get("files_failed", 0)
        skipped = stats.get("files_skipped", 0)
        done = parsed + failed + skipped

        self._stat_labels["files_scanned"].configure(text=str(total))
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

        skip_reasons = stats.get("skip_reasons", "")
        self._stat_labels["skip_reasons"].configure(
            text=skip_reasons if skip_reasons else "--",
        )

        # Progress bar
        if total > 0:
            pct = min(100.0, (done / total) * 100.0)
            self.progress_var.set(pct)
            self.progress_label.configure(text=f"{done} / {total}")

        # Throughput and ETA
        if self._start_time:
            elapsed = time.time() - self._start_time
            if elapsed > 0 and done > 0:
                rate = done / elapsed
                self._stat_labels["throughput"].configure(
                    text=f"{rate:.1f} files/sec",
                )
                remaining = total - done
                if rate > 0 and remaining > 0:
                    eta_sec = remaining / rate
                    self._stat_labels["eta"].configure(
                        text=_format_elapsed(eta_sec),
                    )
                else:
                    self._stat_labels["eta"].configure(text="--")

    def update_current_file(self, filename: str):
        """Update the current file being processed."""
        display = filename
        if len(display) > 60:
            display = "..." + display[-57:]
        self._stat_labels["current_file"].configure(text=display)

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

        # Bytes
        bt = stats.get("bytes_transferred", 0)
        bt_total = stats.get("bytes_total", 0)
        self._transfer_stat_labels["bytes"].configure(
            text=f"{bt / 1024**2:.0f} / {bt_total / 1024**2:.0f} MB"
        )

        # Speed + ETA
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
        self._transfer_running = False
        self.transfer_start_btn.configure(state=tk.NORMAL)
        self.transfer_stop_btn.configure(state=tk.DISABLED)
        self.transfer_progress_var.set(100.0)
        self.transfer_status_label.configure(text="Done")
        if message:
            self.append_log(message, "INFO")

    def update_dedup_only_stats(self, stats: dict):
        """Update the dedup-only panel from a stats dict."""
        total = stats.get("total_files", 0)
        scanned = stats.get("files_scanned", 0)
        dupes = stats.get("duplicates_found", 0)
        current = stats.get("current_file", "")

        if total > 0:
            pct = min(100.0, (scanned / total) * 100.0)
            self.dedup_only_progress_var.set(pct)

        self._dedup_only_stat_labels["scanned"].configure(text=f"{scanned}/{total}")
        self._dedup_only_stat_labels["duplicates"].configure(text=str(dupes))

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

        self.dedup_only_status_label.configure(text=f"{scanned}/{total}")

    def dedup_only_finished(self, stats: dict, message: str = ""):
        """Called when dedup-only pass completes."""
        self.update_dedup_only_stats(stats)
        self._dedup_only_running = False
        self.dedup_only_start_btn.configure(state=tk.NORMAL)
        self.dedup_only_stop_btn.configure(state=tk.DISABLED)
        self.dedup_only_progress_var.set(100.0)
        self.dedup_only_status_label.configure(text="Done")
        if message:
            self.append_log(message, "INFO")

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
        elapsed = stats.get("elapsed_seconds", 0)
        self._stat_labels["elapsed"].configure(text=_format_elapsed(elapsed))
        self._stat_labels["eta"].configure(text="Done")
        self._stat_labels["current_file"].configure(text="--")

        # Final progress
        total = stats.get("files_found", 0)
        parsed = stats.get("files_parsed", 0)
        failed = stats.get("files_failed", 0)
        skipped = stats.get("files_skipped", 0)
        done = parsed + failed + skipped
        if total > 0:
            self.progress_var.set(100.0)
            self.progress_label.configure(text=f"{done} / {total}")

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


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _format_elapsed(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"
