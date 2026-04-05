"""CorpusForge GUI entry point -- config, window, bg pipeline, safe updates."""
from __future__ import annotations

import logging, sys, threading, tkinter as tk
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config.schema import load_config, ForgeConfig
from src.parse.dispatcher import get_supported_extensions
from src.gui.app import CorpusForgeApp
from src.gui.safe_after import safe_after, drain_ui_queue

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = "config/config.yaml"

_EMPTY_STATS = {
    "files_found": 0, "files_parsed": 0, "files_failed": 0,
    "files_skipped": 0, "chunks_created": 0, "chunks_enriched": 0,
    "vectors_created": 0, "elapsed_seconds": 0.0, "skip_reasons": "",
}


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
        self.config.paths.source_dirs = [source]
        self.config.paths.output_dir = output
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
        supported = get_supported_extensions()
        if source_path.is_file():
            files = [source_path]
        else:
            files = sorted(source_path.rglob("*"))
            files = [f for f in files if f.is_file() and f.suffix.lower() in supported]
        if self.config.pipeline.max_files:
            files = files[: self.config.pipeline.max_files]
        if not files:
            return self._finish("No supported files found in source.", "WARNING")
        safe_after(self.app.root, 0, self.app.append_log,
                   f"Found {len(files)} files to process.", "INFO")
        safe_after(self.app.root, 0, self.app.update_stats,
                   {**_EMPTY_STATS, "files_found": len(files)})
        if self._stop_event.is_set():
            return self._finish("Pipeline cancelled.", "WARNING",
                                {**_EMPTY_STATS, "files_found": len(files)})
        safe_after(self.app.root, 0, self.app.append_log,
                   "Initializing pipeline (loading models)...", "INFO")
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
    config_path = _DEFAULT_CONFIG
    config = load_config(config_path)
    logging.basicConfig(
        level=getattr(logging, config.pipeline.log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    supported_count = len(get_supported_extensions())
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
    root.mainloop()


if __name__ == "__main__":
    main()
