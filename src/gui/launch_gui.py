"""CorpusForge GUI entry point -- normal pipeline or recovery dedup GUI."""
from __future__ import annotations

import logging, sys, threading, tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import messagebox

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config.schema import load_config, ForgeConfig
from src.parse.dispatcher import get_supported_extensions
from src.gui.app import CorpusForgeApp
from src.gui.safe_after import safe_after, drain_ui_queue
from src.skip.skip_manager import load_deferred_extension_map
from src.enrichment.contextual_enricher import probe_enrichment

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = "config/config.yaml"

_EMPTY_STATS = {
    "files_found": 0, "files_parsed": 0, "files_failed": 0,
    "files_skipped": 0, "chunks_created": 0, "chunks_enriched": 0,
    "vectors_created": 0, "elapsed_seconds": 0.0, "skip_reasons": "",
}


def _discover_candidates(files: list[Path], supported: set[str], deferred: dict[str, str]) -> tuple[list[Path], Counter, Counter]:
    candidates: list[Path] = []
    deferred_counts: Counter = Counter()
    unsupported_counts: Counter = Counter()

    for file_path in files:
        ext = file_path.suffix.lower()
        if ext in deferred:
            candidates.append(file_path)
            deferred_counts[ext or "[no extension]"] += 1
        elif ext in supported:
            candidates.append(file_path)
        else:
            unsupported_counts[ext or "[no extension]"] += 1

    return candidates, deferred_counts, unsupported_counts


class GUILogHandler(logging.Handler):
    """Routes logging output to the GUI log panel via safe_after."""

    def __init__(self, app: CorpusForgeApp):
        super().__init__()
        self.app = app

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            safe_after(self.app.root, 0, self.app.append_log, msg, record.levelname)
        except Exception:
            pass


class PipelineRunner:
    """Manages pipeline execution in a background thread."""

    def __init__(self, app: CorpusForgeApp, config: ForgeConfig):
        self.app = app
        self.config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, source: str, output: str):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        source_path = Path(source).expanduser().resolve()
        output_path = Path(output).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        self.config.paths.source_dirs = [str(source_path)]
        self.config.paths.output_dir = str(output_path)
        self._thread = threading.Thread(
            target=self._run, name="CorpusForge-Pipeline", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _finish(self, msg, level="INFO", stats=None):
        safe_after(self.app.root, 0, self.app.append_log, msg, level)
        safe_after(self.app.root, 0, self.app.pipeline_finished, stats or dict(_EMPTY_STATS))

    def _run(self):
        try:
            self._do_run()
        except Exception as exc:
            logger.error("Pipeline crashed: %s", exc, exc_info=True)
            self._finish(f"Pipeline error: {exc}", "ERROR")

    def _do_run(self):
        from src.pipeline import Pipeline
        source_path = Path(self.config.paths.source_dirs[0])
        if not source_path.exists():
            return self._finish(f"Source not found: {source_path}", "ERROR")

        # Pre-run enrichment check — fail loud before burning parse time
        if self.config.enrich.enabled:
            safe_after(self.app.root, 0, self.app.append_log,
                       "Checking enrichment readiness (Ollama + model)...", "INFO")
            probe = probe_enrichment(
                ollama_url=self.config.enrich.ollama_url,
                model=self.config.enrich.model,
                auto_start=True,
            )
            if probe.ready:
                safe_after(self.app.root, 0, self.app.update_enrichment_status,
                           "ready", "green")
                if probe.auto_started:
                    safe_after(self.app.root, 0, self.app.append_log,
                               "Ollama auto-started successfully.", "INFO")
            else:
                safe_after(self.app.root, 0, self.app.update_enrichment_status,
                           probe.status_text, "red")
                return self._finish(
                    f"Enrichment pre-flight failed: {probe.status_text}. "
                    f"Disable enrichment or fix the issue.", "ERROR")

        supported = get_supported_extensions(self.config.paths.skip_list)
        deferred = load_deferred_extension_map(self.config.paths.skip_list)
        deferred.update({ext: "Deferred by config for this run" for ext in self.config.parse.defer_extensions})
        if source_path.is_file():
            discovered = [source_path]
        else:
            discovered = sorted(f for f in source_path.rglob("*") if f.is_file())
        files, deferred_counts, unsupported_counts = _discover_candidates(discovered, supported, deferred)
        if self.config.pipeline.max_files:
            files = files[: self.config.pipeline.max_files]
        if not files:
            return self._finish("No supported files found in source.", "WARNING")
        if deferred_counts:
            top = ", ".join(f"{ext}={count}" for ext, count in deferred_counts.most_common(6))
            safe_after(
                self.app.root,
                0,
                self.app.append_log,
                f"Deferred formats will be hashed and listed in skip_manifest: {top}",
                "WARNING",
            )
        if unsupported_counts:
            top = ", ".join(f"{ext}={count}" for ext, count in unsupported_counts.most_common(6))
            safe_after(
                self.app.root,
                0,
                self.app.append_log,
                f"Unsupported extensions excluded from this run: {top}",
                "WARNING",
            )
        safe_after(self.app.root, 0, self.app.append_log,
                   f"Found {len(files)} files to process.", "INFO")
        safe_after(self.app.root, 0, self.app.update_stats,
                   {**_EMPTY_STATS, "files_found": len(files)})
        if self._stop_event.is_set():
            return self._finish("Pipeline cancelled.", "WARNING",
                                {**_EMPTY_STATS, "files_found": len(files)})
        stages = []
        if self.config.enrich.enabled:
            stages.append("enrichment")
        if self.config.embed.enabled:
            stages.append("embedding")
        if self.config.extract.enabled:
            stages.append("extraction")
        if stages:
            safe_after(self.app.root, 0, self.app.append_log,
                       f"Initializing pipeline (stages: parse, chunk, {', '.join(stages)})...", "INFO")
        else:
            safe_after(self.app.root, 0, self.app.append_log,
                       "Initializing pipeline (chunk-only mode — no AI models)...", "INFO")
        pipeline = Pipeline(self.config)
        safe_after(self.app.root, 0, self.app.append_log, "Running...", "INFO")

        def on_file_start(file_path, file_index, total_files):
            name = Path(file_path).name
            safe_after(self.app.root, 0, self.app.update_current_file, name)
            safe_after(self.app.root, 0, self.app.update_stats, {
                **_EMPTY_STATS,
                "files_found": total_files,
                "files_parsed": file_index,
            })

        stats = pipeline.run(files, on_file_start=on_file_start)
        safe_after(self.app.root, 0, self.app.pipeline_finished, stats.to_dict())

    @property
    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()


def _count_skip_list(config):
    try:
        import yaml
        p = Path(config.paths.skip_list)
        if p.exists():
            with open(p, encoding="utf-8-sig") as f:
                return len((yaml.safe_load(f) or {}).get("deferred_formats", []))
    except Exception:
        pass
    return 0


def main():
    if "--dedup" in sys.argv[1:]:
        from src.gui.launch_dedup_gui import main as dedup_main
        sys.argv = [sys.argv[0], *[arg for arg in sys.argv[1:] if arg != "--dedup"]]
        dedup_main()
        return

    config_path = _DEFAULT_CONFIG
    config = load_config(config_path)
    logging.basicConfig(
        level=getattr(logging, config.pipeline.log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Auto-select least-used GPU before any CUDA operations
    from src.gpu_selector import apply_gpu_selection
    gpu_idx = apply_gpu_selection()
    supported_count = len(get_supported_extensions(config.paths.skip_list))
    skip_count = _count_skip_list(config)
    root = tk.Tk()
    runner = [None]

    def on_start(source, output):
        if runner[0] is None or not runner[0].is_alive:
            runner[0] = PipelineRunner(app, config)
        runner[0].start(source, output)

    def on_stop():
        if runner[0]:
            runner[0].stop()

    app = CorpusForgeApp(
        root=root, config_path=config_path,
        supported_formats=supported_count, skip_list_count=skip_count,
        enrichment_enabled=config.enrich.enabled,
        on_start=on_start, on_stop=on_stop,
    )
    gui_handler = GUILogHandler(app)
    gui_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(gui_handler)

    def pump_queue():
        drain_ui_queue()
        root.after(50, pump_queue)
    pump_queue()

    def on_close():
        if runner[0]:
            runner[0].stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    app.append_log("CorpusForge GUI ready. Configure paths and click Start.", "INFO")
    app.append_log(
        f"Config: {config_path} | {supported_count} formats | "
        f"{skip_count} deferred | Enrichment: {'ON' if config.enrich.enabled else 'OFF'}",
        "INFO")

    # Startup enrichment probe — update status bar with actual Ollama state
    if config.enrich.enabled:
        def _startup_probe():
            probe = probe_enrichment(
                ollama_url=config.enrich.ollama_url,
                model=config.enrich.model,
                auto_start=True,
            )
            if probe.ready:
                safe_after(root, 0, app.update_enrichment_status, "ready", "green")
                msg = "Enrichment ready"
                if probe.auto_started:
                    msg += " (Ollama auto-started)"
                safe_after(root, 0, app.append_log, msg, "INFO")
            elif probe.ollama_running and not probe.model_available:
                safe_after(root, 0, app.update_enrichment_status,
                           probe.status_text, "orange")
                safe_after(root, 0, app.append_log,
                           f"WARNING: {probe.status_text}", "WARNING")
            else:
                safe_after(root, 0, app.update_enrichment_status,
                           probe.status_text, "red")
                safe_after(root, 0, app.append_log,
                           f"WARNING: {probe.status_text}", "WARNING")

        threading.Thread(target=_startup_probe, daemon=True,
                         name="enrichment-probe").start()

    root.mainloop()


if __name__ == "__main__":
    main()
