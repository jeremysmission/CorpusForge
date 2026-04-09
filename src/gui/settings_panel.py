"""Settings panel -- pipeline configuration UI extracted from CorpusForgeApp."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from .theme import FONT, current_theme


class SettingsPanel:
    """Pipeline settings: workers, toggles, chunk params. Changes save as local overrides."""

    def __init__(self, parent: ttk.LabelFrame, root: tk.Tk, config=None,
                 config_path: str = "", on_save_settings=None,
                 append_log=None):
        self.root = root
        self._config = config
        self.config_path = config_path
        self._on_save_settings = on_save_settings
        self._append_log = append_log
        self._last_save_time = 0.0
        self._build(parent)

    def _build(self, parent):
        t = current_theme()

        # Row 0: Pipeline workers + OCR mode
        row0 = ttk.Frame(parent)
        row0.pack(fill=tk.X, pady=2)

        tk.Label(row0, text="Pipeline workers:", font=FONT, bg=t["panel_bg"],
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

        tk.Label(
            row0,
            text="logical CPU threads",
            font=FONT,
            bg=t["panel_bg"],
            fg=t["label_fg"],
            anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(0, 16))

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

        # Row 1: Toggles
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
        now = time.time()
        if (now - self._last_save_time) < 0.5:
            return
        self._last_save_time = now

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
            if self._append_log:
                self._append_log(f"Settings NOT saved — validation errors: {'; '.join(errors)}", "ERROR")
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
        if self._append_log:
            self._append_log(
                f"Settings saved to config.local.yaml overrides: workers={settings['pipeline']['workers']}, "
                f"OCR={settings['parse']['ocr_mode']}, "
                f"chunk={settings['chunk']['size']}/{settings['chunk']['overlap']}, "
                f"embed={'ON' if settings['embed']['enabled'] else 'OFF'}, "
                f"enrich={'ON' if settings['enrich']['enabled'] else 'OFF'}, "
                f"extract={'ON' if settings['extract']['enabled'] else 'OFF'}",
                "INFO",
            )

    def _handle_reset_defaults(self):
        """Reset all settings controls to base config.yaml values."""
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Reset to Defaults",
            "Reset all settings to config.yaml defaults?\n\n"
            "This does not change config files — only resets the GUI controls.\n"
            "Click Save Settings after to write config.local.yaml overrides.",
        ):
            return

        try:
            import yaml
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

            if self._append_log:
                self._append_log("Settings reset to config.yaml defaults. Click Save to write config.local.yaml overrides.", "INFO")
        except Exception as exc:
            if self._append_log:
                self._append_log(f"Failed to reset defaults: {exc}", "ERROR")
