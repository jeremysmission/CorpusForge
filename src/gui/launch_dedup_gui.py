"""Recovery-stage dedup GUI entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config.schema import load_config, ForgeConfig
from src.dedup.document_dedup import run_document_dedup, write_index
from src.gui.dedup_app import DedupRecoveryApp
from src.gui.safe_after import drain_ui_queue, safe_after
from src.parse.dispatcher import ParseDispatcher


logger = logging.getLogger(__name__)
_DEFAULT_CONFIG = "config/config.yaml"


class GUILogHandler(logging.Handler):
    """Routes logging messages to the recovery GUI."""

    def __init__(self, app: DedupRecoveryApp):
        super().__init__()
        self.app = app

    def emit(self, record: logging.LogRecord) -> None:
        try:
            safe_after(
                self.app.root,
                0,
                self.app.append_log,
                self.format(record),
                record.levelname,
            )
        except Exception:
            pass


class DedupRunner:
    """Runs the recovery-stage dedup pass in a background thread."""

    def __init__(self, app: DedupRecoveryApp, config: ForgeConfig):
        self.app = app
        self.config = config
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(
        self,
        *,
        source: str,
        output: str,
        similarity_threshold: str,
        min_chars: str,
        workers: str,
    ) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            kwargs={
                "source": source,
                "output": output,
                "similarity_threshold": similarity_threshold,
                "min_chars": min_chars,
                "workers": workers,
            },
            name="CorpusForge-Dedup-Recovery",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self, *, source: str, output: str, similarity_threshold: str, min_chars: str, workers: str) -> None:
        try:
            threshold_value = float(similarity_threshold)
            min_chars_value = int(min_chars)
            worker_count = max(1, int(workers))
        except ValueError:
            safe_after(self.app.root, 0, self.app.run_finished, {"elapsed_seconds": 0}, "Invalid threshold, min chars, or worker value.")
            return

        source_path = Path(source).resolve()
        output_root = Path(output).resolve()
        dispatcher = ParseDispatcher(
            timeout_seconds=self.config.parse.timeout_seconds,
            max_chars=self.config.parse.max_chars_per_file,
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = output_root / f"document_dedup_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_after(self.app.root, 0, self.app.append_log, f"Scanning {source_path}", "INFO")
        safe_after(self.app.root, 0, self.app.append_log, f"Writing recovery output to {output_dir}", "INFO")

        def on_group(**progress) -> None:
            safe_after(self.app.root, 0, self.app.update_progress, **progress)
            safe_after(
                self.app.root,
                0,
                self.app.append_log,
                f"Family {progress['group_index']}/{progress['total_groups']}: "
                f"{progress['stem_key'] or '<unknown>'} ({progress['group_size']} files)",
                "INFO",
            )

        try:
            decisions, stats = run_document_dedup(
                input_path=source_path,
                dispatcher=dispatcher,
                extensions={".pdf", ".doc", ".docx"},
                similarity_threshold=threshold_value,
                min_chars=min_chars_value,
                workers=worker_count,
                on_group=on_group,
                should_stop=self._stop_event.is_set,
            )
        except Exception as exc:
            logger.error("Recovery dedup crashed: %s", exc, exc_info=True)
            safe_after(
                self.app.root,
                0,
                self.app.run_finished,
                {"elapsed_seconds": 0},
                f"Recovery dedup error: {exc}",
            )
            return

        write_index(
            decisions,
            db_path=output_dir / "document_dedup.sqlite3",
            canonical_list_path=output_dir / "canonical_files.txt",
            duplicate_jsonl_path=output_dir / "duplicate_files.jsonl",
            report_path=output_dir / "dedup_report.json",
            source_root=source_path,
            extensions=[".doc", ".docx", ".pdf"],
            similarity_threshold=threshold_value,
            min_chars=min_chars_value,
        )

        message = (
            f"Recovery dedup complete. Canonical={stats.canonical_files}, "
            f"duplicates={stats.duplicate_files}, stopped={stats.stopped}. "
            f"Use {output_dir / 'canonical_files.txt'} with run_pipeline.py --input-list."
        )
        safe_after(self.app.root, 0, self.app.run_finished, stats.__dict__, message)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CorpusForge recovery dedup GUI")
    parser.add_argument("--config", default=_DEFAULT_CONFIG, help="Path to config YAML.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    logging.basicConfig(
        level=getattr(logging, config.pipeline.log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    root = tk.Tk()
    runner = [None]

    def on_start(**kwargs) -> None:
        if runner[0] is None or not runner[0].is_alive:
            runner[0] = DedupRunner(app, config)
        runner[0].start(**kwargs)

    def on_stop() -> None:
        if runner[0]:
            runner[0].stop()

    app = DedupRecoveryApp(root=root, config_path=args.config, on_start=on_start, on_stop=on_stop)
    gui_handler = GUILogHandler(app)
    gui_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(gui_handler)

    def pump_queue() -> None:
        drain_ui_queue()
        root.after(50, pump_queue)

    pump_queue()

    def on_close() -> None:
        if runner[0]:
            runner[0].stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    app.append_log("Recovery dedup GUI ready. Pick a source folder and click Start Recovery.", "INFO")
    app.append_log("This pass only targets PDF/DOC/DOCX families before re-chunking.", "INFO")
    root.mainloop()


if __name__ == "__main__":
    main()
