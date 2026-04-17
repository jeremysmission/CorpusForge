"""CorpusForge GUI entry point -- normal pipeline or recovery dedup GUI.

This file is what ``start_corpusforge.bat`` hands off to. It is the
launcher: it loads ``config/config.yaml``, picks a GPU, builds the main
window from :mod:`src.gui.app`, and wires every button to the
background worker classes defined here.

What the operator sees when this file runs:
    * The full Forge Pipeline Monitor window appears.
    * An "INFO" log line confirms the active config, supported formats,
      skip/defer counts, enrichment state, and worker count.

Pipeline stages controlled here:
    * Bulk Transfer  -> :class:`TransferRunner`
    * Dedup-only     -> :class:`DedupOnlyRunner`
    * Precheck       -> :class:`PrecheckRunner`
    * Full pipeline  -> :class:`PipelineRunner` (discover, dedup, parse,
      chunk, optional enrich/embed/extract, export)

If ``--dedup`` is passed, this launcher forwards to
:mod:`src.gui.launch_dedup_gui` instead, which opens the Recovery Dedup
window.
"""
from __future__ import annotations

import argparse
import logging, subprocess, sys, threading, tkinter as tk
from collections import Counter
from pathlib import Path
import shutil
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
    "files_found": 0, "files_after_dedup": 0, "files_parsed": 0, "files_failed": 0,
    "files_skipped": 0, "chunks_created": 0, "chunks_per_second": 0.0, "chunks_enriched": 0,
    "vectors_created": 0, "entities_extracted": 0,
    "elapsed_seconds": 0.0, "stop_requested": False, "skip_reasons": "",
}


def _display_repo_relative(path_value: str | Path) -> str:
    """Return a concise repo-relative path when possible."""
    path = Path(path_value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(_PROJECT_ROOT).as_posix()
    except Exception:
        return str(path)


def _discover_candidates(files: list[Path], supported: set[str], deferred: dict[str, str]) -> tuple[list[Path], Counter, Counter]:
    """Split a file list into candidates, deferred formats, and unsupported."""
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


def _merge_settings_overrides(existing: dict, overrides: dict) -> dict:
    """Merge GUI settings into the active config document."""
    merged = dict(existing or {})
    for section, values in overrides.items():
        section_values = dict(merged.get(section) or {})
        section_values.update(values)
        merged[section] = section_values
    return merged


def _save_gui_settings_override(config_file: Path, settings: dict) -> Path:
    """Persist GUI settings into the active config.yaml file."""
    import yaml

    existing = {}
    if config_file.exists():
        with open(config_file, encoding="utf-8-sig") as handle:
            existing = yaml.safe_load(handle) or {}
    merged = _merge_settings_overrides(existing, settings)
    with open(config_file, "w", encoding="utf-8") as handle:
        yaml.dump(merged, handle, default_flow_style=False, sort_keys=False)
    return config_file


class GUILogHandler(logging.Handler):
    """Bridge that pushes Python log records into the GUI log panel.

    Forge's pipeline uses the standard logging module. This handler
    catches every log record and safely forwards it to the scrolling
    Pipeline Log visible to the operator.
    """

    def __init__(self, app: CorpusForgeApp):
        super().__init__()
        self.app = app

    def emit(self, record: logging.LogRecord):
        """Format the log record and queue it for the main UI thread."""
        try:
            msg = self.format(record)
            safe_after(self.app.root, 0, self.app.append_log, msg, record.levelname)
        except Exception:
            pass


class TransferRunner:
    """Background worker for the Bulk Transfer panel.

    Copies raw files from a "From" folder into a "To" (staging) folder
    in a background thread so the window stays responsive. Progress is
    reported back into the GUI via ``safe_after``.
    """

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self._thread = None
        self._stop_event = threading.Event()

    def start(self, source: str, dest: str):
        """Start a bulk transfer in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(source, dest),
            name="CorpusForge-Transfer", daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Request a safe stop for the bulk transfer."""
        self._stop_event.set()

    def _run(self, source: str, dest: str):
        """Thread body - run BulkSyncer and route progress to the GUI."""
        from src.download.syncer import BulkSyncer
        try:
            source_path = Path(source).resolve()
            dest_path = Path(dest).resolve()
            if not source_path.exists():
                safe_after(self.app.root, 0, self.app.transfer_finished,
                           {}, f"Transfer error: source not found: {source_path}")
                return

            safe_after(self.app.root, 0, self.app.append_log,
                       f"Transfer: {source_path} -> {dest_path}", "INFO")

            def on_progress(stats):
                safe_after(self.app.root, 0, self.app.update_transfer_stats, stats.to_dict())

            syncer = BulkSyncer(
                source_dir=source_path,
                dest_dir=dest_path,
                workers=self.config.pipeline.workers,
                on_progress=on_progress,
                should_stop=self._stop_event.is_set,
            )
            result = syncer.run()
            msg = (
                f"Transfer complete: {result.files_copied} copied, "
                f"{result.files_skipped} skipped, {result.files_failed} failed "
                f"in {result.elapsed_seconds:.1f}s"
            )
            safe_after(self.app.root, 0, self.app.transfer_finished,
                       result.to_dict(), msg)
        except Exception as exc:
            logger.error("Transfer crashed: %s", exc, exc_info=True)
            safe_after(self.app.root, 0, self.app.transfer_finished,
                       {}, f"Transfer error: {exc}")

    @property
    def is_alive(self):
        """True while the transfer thread is still running."""
        return self._thread is not None and self._thread.is_alive()


class DedupOnlyRunner:
    """Background worker for the Dedup-Only panel.

    Runs only the duplicate-detection pass (no parsing, no embedding).
    It walks the source folder, hashes every file, writes a canonical
    file list, and optionally copies deduplicated sources into a
    portable folder for downstream use.
    """

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self._thread = None
        self._stop_event = threading.Event()

    def start(self, source: str, output: str, copy_sources: bool = True):
        """Start a dedup-only scan in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(source, output, copy_sources),
            name="CorpusForge-DedupOnly", daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Request a safe stop for the dedup-only scan."""
        self._stop_event.set()

    def _collect_canonical_files(self, deduplicator, scanned_files: list[Path]) -> list[Path]:
        """Return the full canonical snapshot for the scanned portion of the tree.

        This includes unchanged indexed canonicals and newly hashed canonicals,
        not just the current run's incremental work list.
        """
        canonical_files: list[Path] = []
        for file_path in scanned_files:
            state = deduplicator.hasher.get_state(file_path)
            if state and state["status"] != "duplicate":
                canonical_files.append(file_path)
        return canonical_files

    def _copy_canonical_sources(
        self,
        output_dir: Path,
        source_path: Path,
        canonical_files: list[Path],
    ) -> tuple[Path, int]:
        portable_copy_dir = output_dir / "deduped_sources"
        portable_copy_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for file_path in canonical_files:
            try:
                relative_path = file_path.resolve().relative_to(source_path)
            except Exception:
                relative_path = Path(file_path.name)
            destination = portable_copy_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, destination)
            copied += 1
        return portable_copy_dir, copied

    def _write_outputs(self, output_dir: Path, source_path: Path, canonical_files: list[Path], report: dict) -> None:
        import json

        canonical_path = output_dir / "canonical_files.txt"
        with open(canonical_path, "w", encoding="utf-8", newline="\n") as handle:
            for file_path in canonical_files:
                handle.write(str(file_path.resolve()) + "\n")

        with open(output_dir / "dedup_report.json", "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")

        lines = [
            "=" * 60,
            "  CorpusForge Dedup-Only Report",
            "=" * 60,
            "",
            f"Source:         {source_path}",
            f"Output:         {output_dir}",
            f"Files scanned:  {report['files_scanned']}",
            f"Canonical files:{report['unique_files']}",
            f"Work files:     {report['work_files']}",
            f"Duplicates:     {report['duplicates_found']}",
            f"Unchanged:      {report['unchanged_files']}",
            f"Elapsed:        {report['elapsed_seconds']:.1f}s",
            f"State DB:       {report['state_db']}",
            "",
            f"Canonical list: {canonical_path}",
            f"Portable copy:  {report['portable_copy_dir'] or '(disabled)'}",
            f"Files copied:   {report['portable_files_copied']}",
            "",
            "=" * 60,
        ]
        with open(output_dir / "run_report.txt", "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")

    def _run(self, source: str, output: str, copy_sources: bool = True):
        """Thread body - scan for duplicates and write dedup artifacts."""
        import time as _time
        from datetime import datetime
        from src.download.hasher import Hasher
        from src.download.deduplicator import Deduplicator
        hasher = None
        try:
            source_path = Path(source).expanduser().resolve()
            output_root = Path(output).expanduser().resolve()
            if not source_path.exists():
                safe_after(self.app.root, 0, self.app.dedup_only_finished,
                           {}, f"Dedup error: source not found: {source_path}")
                return
            output_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = output_root / f"dedup_only_{timestamp}"
            output_dir.mkdir(parents=True, exist_ok=True)

            safe_after(self.app.root, 0, self.app.append_log,
                       f"Dedup-only scan: {source_path}", "INFO")
            safe_after(self.app.root, 0, self.app.append_log,
                       f"Dedup-only output: {output_dir}", "INFO")

            all_files = sorted(f for f in source_path.rglob("*") if f.is_file())
            total = len(all_files)
            safe_after(self.app.root, 0, self.app.append_log,
                       f"Found {total} files to scan for duplicates.", "INFO")
            safe_after(self.app.root, 0, self.app.update_dedup_only_stats, {
                "total_files": total,
                "files_scanned": 0,
                "duplicates_found": 0,
                "unique_files": 0,
                "current_file": "",
                "elapsed_seconds": 0.0,
                "output_dir": str(output_dir),
                "status_text": "Scanning...",
            })

            hasher = Hasher(self.config.paths.state_db)
            deduplicator = Deduplicator(hasher)
            start = _time.time()

            def on_progress(scanned, total_files, current_file, dupes):
                scanned_count = min(scanned, total_files)
                stats = {
                    "total_files": total_files,
                    "files_scanned": scanned_count,
                    "duplicates_found": dupes,
                    "unique_files": max(scanned_count - dupes, 0),
                    "current_file": current_file,
                    "elapsed_seconds": _time.time() - start,
                    "output_dir": str(output_dir),
                    "portable_copy_dir": str(output_dir / "deduped_sources") if copy_sources else "",
                    "status_text": "Scanning..." if not self._stop_event.is_set() else "Stopping...",
                }
                safe_after(self.app.root, 0, self.app.update_dedup_only_stats, stats)

            work_files = deduplicator.filter_new_and_changed(
                all_files, on_progress=on_progress, should_stop=self._stop_event.is_set,
            )
            scanned = deduplicator.files_scanned
            duplicates = deduplicator.skipped_duplicate
            unchanged = deduplicator.skipped_unchanged
            elapsed = _time.time() - start
            scanned_files = all_files[:scanned]
            canonical_files = self._collect_canonical_files(deduplicator, scanned_files)
            portable_copy_dir = ""
            portable_files_copied = 0
            if copy_sources and canonical_files:
                portable_copy_path, portable_files_copied = self._copy_canonical_sources(
                    output_dir, source_path, canonical_files
                )
                portable_copy_dir = str(portable_copy_path)
            report = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source_root": str(source_path),
                "output_dir": str(output_dir),
                "files_scanned": scanned,
                "unique_files": len(canonical_files),
                "work_files": len(work_files),
                "duplicates_found": duplicates,
                "unchanged_files": unchanged,
                "elapsed_seconds": round(elapsed, 2),
                "state_db": self.config.paths.state_db,
                "portable_copy_enabled": copy_sources,
                "portable_copy_dir": portable_copy_dir,
                "portable_files_copied": portable_files_copied,
            }
            self._write_outputs(output_dir, source_path, canonical_files, report)
            stopped = self._stop_event.is_set() and scanned < total
            final_stats = {
                "total_files": total,
                "files_scanned": scanned,
                "duplicates_found": duplicates,
                "unique_files": len(canonical_files),
                "current_file": "",
                "elapsed_seconds": elapsed,
                "output_dir": str(output_dir),
                "portable_copy_dir": portable_copy_dir,
                "status_text": "Stopped" if stopped else "Done",
            }
            if stopped:
                msg = (
                    f"Dedup stopped after {scanned}/{total} files. "
                    f"Partial canonical list written to {output_dir / 'canonical_files.txt'}"
                )
                if portable_copy_dir:
                    msg += f" and partial deduped source copy saved to {portable_copy_dir}"
            else:
                msg = (
                    f"Dedup complete: {scanned} scanned, {duplicates} duplicates found, "
                    f"{len(canonical_files)} canonical files in {elapsed:.1f}s. "
                    f"Canonical list: {output_dir / 'canonical_files.txt'}"
                )
                if portable_copy_dir:
                    msg += f" | Deduped source copy: {portable_copy_dir}"
            safe_after(self.app.root, 0, self.app.dedup_only_finished, final_stats, msg)
        except Exception as exc:
            logger.error("Dedup-only crashed: %s", exc, exc_info=True)
            safe_after(self.app.root, 0, self.app.dedup_only_finished,
                       {}, f"Dedup error: {exc}")
        finally:
            if hasher is not None:
                hasher.close()

    @property
    def is_alive(self):
        """True while the dedup-only thread is still running."""
        return self._thread is not None and self._thread.is_alive()


class PrecheckRunner:
    """Background worker for the Run Precheck button.

    Launches the workstation precheck tool as a subprocess so the
    operator can confirm hardware, paths, and settings are healthy
    before burning time on a long run. Output is streamed into the
    Pipeline Log panel.
    """

    def __init__(self, app: CorpusForgeApp, config_path: str):
        self.app = app
        self.config_path = config_path
        self._thread: threading.Thread | None = None

    def start(self, source: str, output: str, settings: dict):
        """Start the precheck subprocess in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            safe_after(self.app.root, 0, self.app.append_log, "Precheck already running.", "WARNING")
            return
        self._thread = threading.Thread(
            target=self._run,
            kwargs={"source": source, "output": output, "settings": settings},
            name="CorpusForge-Precheck",
            daemon=True,
        )
        self._thread.start()

    def _run(self, *, source: str, output: str, settings: dict):
        """Thread body - run the precheck CLI tool and stream its output."""
        tool_path = _PROJECT_ROOT / "tools" / "precheck_workstation_large_ingest.py"
        cmd = [
            sys.executable,
            str(tool_path),
            "--config", self.config_path,
            "--source", source,
            "--output", output,
            "--workers", str(settings["pipeline"]["workers"]),
            "--ocr-mode", settings["parse"]["ocr_mode"],
            "--embed-enabled", "1" if settings["embed"]["enabled"] else "0",
            "--enrich-enabled", "1" if settings["enrich"]["enabled"] else "0",
            "--extract-enabled", "1" if settings["extract"]["enabled"] else "0",
            "--embed-batch-size", str(settings["hardware"]["embed_batch_size"]),
        ]
        safe_after(
            self.app.root,
            0,
            self.app.append_log,
            (
                f"Running workstation precheck against runtime config "
                f"{_display_repo_relative(self.config_path)} "
                f"(workers={settings['pipeline']['workers']}, "
                f"run defers stay in YAML)..."
            ),
            "INFO",
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(_PROJECT_ROOT),
                timeout=120,
            )
        except Exception as exc:
            safe_after(self.app.root, 0, self.app.append_log, f"Precheck error: {exc}", "ERROR")
            return

        combined = []
        if proc.stdout:
            combined.append(proc.stdout.rstrip())
        if proc.stderr:
            combined.append(proc.stderr.rstrip())
        for block in combined:
            for line in block.splitlines():
                level = "ERROR" if "RESULT: FAIL" in line else "INFO"
                safe_after(self.app.root, 0, self.app.append_log, line, level)

        if proc.returncode == 0:
            safe_after(self.app.root, 0, self.app.append_log, "Precheck complete: PASS", "INFO")
        else:
            safe_after(self.app.root, 0, self.app.append_log, f"Precheck complete: FAIL (exit {proc.returncode})", "ERROR")


class PipelineRunner:
    """Background worker for the Start Pipeline button.

    Owns the full Forge ingest run (discover, dedup, parse, chunk,
    optional enrich/embed/extract, export) on a background thread.
    Progress, stage transitions, and final stats are pushed back into
    the GUI through ``safe_after``. Stop Safely sets a threading.Event
    that the pipeline polls, so the run bails out cleanly.
    """

    def __init__(self, app: CorpusForgeApp, config: ForgeConfig):
        self.app = app
        self.config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, source: str, output: str):
        """Start a full pipeline run in a background thread."""
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
        """Request a safe stop - Stop Safely button wires here."""
        # The pipeline checks _stop_event between files/stages and
        # honors the request without losing finished work.
        self._stop_event.set()

    def _finish(self, msg, level="INFO", stats=None):
        """Log a final message and notify the GUI that the run is over."""
        safe_after(self.app.root, 0, self.app.append_log, msg, level)
        safe_after(self.app.root, 0, self.app.pipeline_finished, stats or dict(_EMPTY_STATS))

    def _run(self):
        """Thread body - wraps _do_run with crash reporting."""
        try:
            self._do_run()
        except Exception as exc:
            logger.error("Pipeline crashed: %s", exc, exc_info=True)
            self._finish(f"Pipeline error: {exc}", "ERROR")

    def _do_run(self):
        """Execute the full Forge pipeline and stream progress to the GUI."""
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
        safe_after(self.app.root, 0, self.app.update_stage_progress,
                   "discover", 0, 0, f"Walking {source_path} (CPU/IO, no GPU yet)...")
        if source_path.is_file():
            discovered = [source_path]
            discover_stopped = False
        else:
            # Cooperative discovery: iterate rglob so a Stop Safely pressed while
            # we walk a 700GB tree actually bails early instead of enumerating
            # the whole disk. Stop is checked every 500 entries.
            discovered = []
            discover_stopped = False
            _STOP_POLL = 500
            _PROGRESS_POLL = 2000
            for idx, entry in enumerate(source_path.rglob("*")):
                if idx % _STOP_POLL == 0 and self._stop_event.is_set():
                    discover_stopped = True
                    break
                try:
                    if entry.is_file():
                        discovered.append(entry)
                except OSError:
                    continue
                if idx and idx % _PROGRESS_POLL == 0:
                    safe_after(self.app.root, 0, self.app.update_stage_progress,
                               "discover", len(discovered), 0,
                               f"Walked {idx} entries, {len(discovered)} files so far...")
            discovered.sort()
        if discover_stopped:
            safe_after(self.app.root, 0, self.app.update_stage_progress,
                       "stopping", 0, 0,
                       f"Stop honored during discovery after {len(discovered)} files.")
            return self._finish(
                f"Discovery stopped by operator after {len(discovered)} files. "
                f"No work was admitted; hashed state is unchanged.",
                "WARNING",
                {**_EMPTY_STATS, "files_found": len(discovered), "stop_requested": True},
            )
        safe_after(self.app.root, 0, self.app.update_stage_progress,
                   "discover", len(discovered), len(discovered),
                   f"Found {len(discovered)} files on disk.")
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
            return self._finish("Pipeline cancelled before processing began.", "WARNING",
                                {**_EMPTY_STATS, "files_found": len(files), "stop_requested": True})
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

        def on_stats_update(stats_snapshot):
            if isinstance(self.app, CorpusForgeApp):
                safe_after(self.app.root, 0, self.app.update_stats, stats_snapshot)
            else:
                self.app.update_stats(stats_snapshot)

        def on_stage_progress(stage, current, total, detail):
            msg = f"[{stage}] {current}/{total}"
            if detail:
                msg += f" — {detail}"
            safe_after(self.app.root, 0, self.app.append_log, msg, "INFO")
            safe_after(self.app.root, 0, self.app.update_stage_progress,
                       stage, current, total, detail)

        stats = pipeline.run(
            files,
            on_file_start=on_file_start,
            on_stage_progress=on_stage_progress,
            on_stats_update=on_stats_update,
            should_stop=self._stop_event.is_set,
        )
        if stats.stop_requested and not stats.export_dir and stats.checkpoint_dir:
            safe_after(
                self.app.root,
                0,
                self.app.append_log,
                f"Chunk checkpoint preserved at {stats.checkpoint_dir}. Re-run the same source/output to resume before export.",
                "WARNING",
            )
        if isinstance(self.app, CorpusForgeApp):
            safe_after(self.app.root, 0, self.app.pipeline_finished, stats.to_dict())
        else:
            self.app.pipeline_finished(stats.to_dict())

    @property
    def is_alive(self):
        """True while the pipeline thread is still running."""
        return self._thread is not None and self._thread.is_alive()


def _count_skip_list(config):
    """Return how many formats live in the static skip list YAML."""
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
    """Launch the Forge GUI. This is the function start_corpusforge.bat calls."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=_DEFAULT_CONFIG, help="Path to config YAML.")
    parser.add_argument("--dedup", action="store_true", help="Launch the dedup-only recovery GUI.")
    args, _unknown = parser.parse_known_args()

    if args.dedup:
        from src.gui.launch_dedup_gui import main as dedup_main
        sys.argv = [
            sys.argv[0],
            "--config",
            args.config,
            *_unknown,
        ]
        dedup_main()
        return

    config_path = args.config
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
    transfer_runner = [None]
    dedup_only_runner = [None]
    precheck_runner = [None]

    def on_start(source, output):
        if runner[0] is None or not runner[0].is_alive:
            runner[0] = PipelineRunner(app, config)
        runner[0].start(source, output)

    def on_stop():
        if runner[0]:
            runner[0].stop()

    def on_transfer_start(source, dest):
        if transfer_runner[0] is None or not transfer_runner[0].is_alive:
            transfer_runner[0] = TransferRunner(app, config)
        transfer_runner[0].start(source, dest)

    def on_transfer_stop():
        if transfer_runner[0]:
            transfer_runner[0].stop()

    def on_dedup_only_start(source, output, copy_sources=True):
        if dedup_only_runner[0] is None or not dedup_only_runner[0].is_alive:
            dedup_only_runner[0] = DedupOnlyRunner(app, config)
        dedup_only_runner[0].start(source, output, copy_sources=copy_sources)

    def on_dedup_only_stop():
        if dedup_only_runner[0]:
            dedup_only_runner[0].stop()

    def on_precheck(source, output, settings):
        if precheck_runner[0] is None:
            precheck_runner[0] = PrecheckRunner(app, config_path)
        precheck_runner[0].start(source, output, settings)

    def on_save_settings(settings):
        """Write GUI settings to the active config file and update live config."""
        config_file = Path(config_path)
        if not config_file.is_absolute():
            config_file = (_PROJECT_ROOT / config_file).resolve()
        try:
            saved_path = _save_gui_settings_override(config_file, settings)
            # Update live config object
            config.pipeline.workers = settings["pipeline"]["workers"]
            config.parse.ocr_mode = settings["parse"]["ocr_mode"]
            config.chunk.size = settings["chunk"]["size"]
            config.chunk.overlap = settings["chunk"]["overlap"]
            config.embed.enabled = settings["embed"]["enabled"]
            config.enrich.enabled = settings["enrich"]["enabled"]
            config.enrich.max_concurrent = settings["enrich"]["max_concurrent"]
            config.extract.enabled = settings["extract"]["enabled"]
            config.extract.batch_size = settings["extract"]["batch_size"]
            config.hardware.embed_batch_size = settings["hardware"]["embed_batch_size"]
            app.update_worker_status(settings["pipeline"]["workers"])
            logger.info("Settings saved to %s", saved_path)
        except Exception as exc:
            logger.error("Failed to save settings: %s", exc)
            app.append_log(f"ERROR saving settings: {exc}", "ERROR")

    app = CorpusForgeApp(
        root=root, config_path=config_path, config=config,
        supported_formats=supported_count, skip_list_count=skip_count,
        enrichment_enabled=config.enrich.enabled,
        on_start=on_start, on_stop=on_stop,
        on_save_settings=on_save_settings, on_precheck=on_precheck,
        on_transfer_start=on_transfer_start,
        on_transfer_stop=on_transfer_stop,
        on_dedup_only_start=on_dedup_only_start,
        on_dedup_only_stop=on_dedup_only_stop,
    )
    gui_handler = GUILogHandler(app)
    gui_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(gui_handler)

    # Every 50ms the main thread drains the thread-safe queue so any
    # update a background worker enqueued via safe_after is applied.
    def pump_queue():
        """Pull any pending GUI updates off the safe_after queue."""
        drain_ui_queue()
        root.after(50, pump_queue)
    pump_queue()

    def on_close():
        if runner[0]:
            runner[0].stop()
        if transfer_runner[0]:
            transfer_runner[0].stop()
        if dedup_only_runner[0]:
            dedup_only_runner[0].stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    app.append_log("CorpusForge GUI ready. Configure paths and click Start.", "INFO")
    app.append_log(
        f"Runtime config: {_display_repo_relative(config_path)} | "
        f"Skip/defer source: {_display_repo_relative(config.paths.skip_list)} | "
        f"{supported_count} formats | {skip_count} static defers | "
        f"{len(config.parse.defer_extensions)} run defers | "
        f"Enrichment: {'ON' if config.enrich.enabled else 'OFF'} | "
        f"Pipeline workers: {config.pipeline.workers} logical threads",
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
