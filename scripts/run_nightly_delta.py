"""
CorpusForge nightly delta runner.

Detects new or changed files on the source share, mirrors only that delta
locally, then runs the existing pipeline against the mirrored delta set while
preserving original source provenance in the export package.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import ForgeConfig, load_config
from src.download.delta_tracker import NightlyDeltaTracker
from src.download.syncer import BulkSyncer
from src.gpu_selector import apply_gpu_selection
from src.pipeline import Pipeline


logger = logging.getLogger("nightly_delta")


@dataclass
class StopController:
    """Cooperative stop controller driven by signals or a sentinel file."""

    stop_file: Path | None
    requested: bool = False
    reason: str = ""

    def install_signal_handlers(self) -> None:
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, self._handle_signal)
            except (ValueError, OSError):
                continue

    def _handle_signal(self, signum, _frame) -> None:
        if not self.requested:
            self.requested = True
            self.reason = f"signal {signum}"
            logger.warning("Nightly delta stop requested via %s.", self.reason)

    def stop_requested(self) -> bool:
        if self.requested:
            return True
        if self.stop_file and self.stop_file.exists():
            self.requested = True
            self.reason = f"stop file {self.stop_file}"
            logger.warning("Nightly delta stop requested via sentinel file: %s", self.stop_file)
        return self.requested


def _configure_logging(log_path: Path, level_name: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_path), encoding="utf-8"),
        ],
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _write_input_list(path: Path, files: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for file_path in files:
            handle.write(str(file_path) + "\n")


def _clone_pipeline_config(config: ForgeConfig) -> ForgeConfig:
    return config.model_copy(deep=True)


def _build_source_mapper(source_root: Path, mirror_root: Path):
    resolved_source = source_root.resolve()
    resolved_mirror = mirror_root.resolve()

    def mapper(mirror_path: str) -> str:
        local_path = Path(mirror_path).resolve()
        relative = local_path.relative_to(resolved_mirror)
        return str((resolved_source / relative).resolve())

    return mapper


def _resolve_pipeline_paths(config: ForgeConfig) -> tuple[Path, Path]:
    nightly = config.nightly_delta
    output_dir = Path(nightly.pipeline_output_dir) if nightly.pipeline_output_dir else Path(config.paths.output_dir)
    state_db = Path(nightly.pipeline_state_db) if nightly.pipeline_state_db else Path(config.paths.state_db)
    return output_dir.resolve(), state_db.resolve()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CorpusForge nightly delta runner")
    parser.add_argument("--config", default="config/config.yaml", help="Path to the active runtime config.")
    parser.add_argument("--dry-run", action="store_true", help="Scan only. Do not transfer or run the pipeline.")
    parser.add_argument("--transfer-only", action="store_true", help="Stop after local mirror transfer.")
    parser.add_argument("--chunk-only", action="store_true", help="Disable embed/enrich/extract for proof or workstation-safe validation.")
    parser.add_argument("--max-files", type=int, default=None, help="Optional cap for controlled proof runs.")
    parser.add_argument("--require-canary", action="store_true", help="Fail if the detected delta set contains no canary file.")
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    config = load_config(args.config)
    nightly = config.nightly_delta

    source_root = Path(nightly.source_root).resolve()
    mirror_root = Path(nightly.mirror_root).resolve()
    manifest_dir = Path(nightly.manifest_dir).resolve()
    pipeline_log_dir = Path(nightly.pipeline_log_dir).resolve()
    transfer_state_db = Path(nightly.transfer_state_db).resolve()
    stop_file = Path(nightly.stop_file).resolve() if nightly.stop_file else None
    pipeline_output_dir, pipeline_state_db = _resolve_pipeline_paths(config)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = pipeline_log_dir / f"nightly_delta_{timestamp}.log"
    _configure_logging(log_path, config.pipeline.log_level)

    stop = StopController(stop_file=stop_file)
    stop.install_signal_handlers()

    logger.info("Nightly delta source: %s", source_root)
    logger.info("Nightly delta mirror: %s", mirror_root)
    logger.info("Nightly delta transfer state: %s", transfer_state_db)
    logger.info("Nightly delta pipeline output: %s", pipeline_output_dir)
    logger.info("Nightly delta pipeline state DB: %s", pipeline_state_db)
    logger.info("Nightly delta stop file: %s", stop_file or "(disabled)")

    tracker = NightlyDeltaTracker(str(transfer_state_db))
    transfer_stats = None
    pipeline_stats = None
    mirrored_delta_files: list[Path] = []
    scan_manifest = manifest_dir / f"nightly_delta_scan_{timestamp}.json"
    transfer_manifest = manifest_dir / f"nightly_delta_transfer_{timestamp}.json"
    report_path = manifest_dir / f"nightly_delta_report_{timestamp}.json"
    input_list_path = manifest_dir / f"nightly_delta_input_{timestamp}.txt"
    exit_code = 0

    try:
        scan = tracker.scan(
            source_root=source_root,
            max_files=args.max_files or nightly.max_files,
            canary_globs=nightly.canary_globs,
            should_stop=stop.stop_requested,
        )
        _write_json(scan_manifest, scan.to_dict())
        logger.info(
            "Nightly delta scan: %d total, %d delta (%d new, %d changed, %d resumed hashed, %d unchanged, %d deleted)",
            scan.total_files,
            scan.delta_files,
            scan.new_files,
            scan.changed_files,
            scan.resumed_hashed,
            scan.unchanged_files,
            scan.deleted_files,
        )

        require_canary = args.require_canary or nightly.require_canary
        if require_canary and not scan.canary_matches:
            logger.error("Nightly delta canary gate failed: no canary files found in delta set.")
            exit_code = 1
        elif scan.delta_files == 0:
            logger.info("Nightly delta scan found no new or changed files.")
        elif args.dry_run:
            logger.info("Dry run complete. Transfer and pipeline stages skipped.")
        elif stop.stop_requested():
            logger.warning("Stop requested after scan. Transfer and pipeline stages skipped.")
            exit_code = 2
        else:
            delta_source_files = [Path(path) for path in scan.delta_paths]

            def on_file_result(src_file: Path, status: str, _nbytes: int, _err: str) -> None:
                if status in {"copied", "skipped"}:
                    tracker.mark_mirrored(src_file)
                    mirrored_delta_files.append(mirror_root / src_file.relative_to(source_root))

            syncer = BulkSyncer(
                source_dir=source_root,
                dest_dir=mirror_root,
                workers=nightly.transfer_workers,
                should_stop=stop.stop_requested,
                on_file_result=on_file_result,
            )
            transfer_stats = syncer.run_files(delta_source_files)
            _write_json(
                transfer_manifest,
                {
                    "timestamp": datetime.now().isoformat(),
                    "source_root": str(source_root),
                    "mirror_root": str(mirror_root),
                    "delta_source_files": [str(path) for path in delta_source_files],
                    "ready_mirror_files": [str(path) for path in mirrored_delta_files if path.exists()],
                    "transfer_stats": transfer_stats.to_dict(),
                },
            )
            if transfer_stats.files_failed > 0 or transfer_stats.stop_requested:
                logger.warning(
                    "Nightly delta transfer finished with %d failures; stop_requested=%s",
                    transfer_stats.files_failed,
                    transfer_stats.stop_requested,
                )
                exit_code = 2

            mirrored_delta_files = [path for path in mirrored_delta_files if path.exists()]
            _write_input_list(input_list_path, mirrored_delta_files)

            if args.transfer_only:
                logger.info("Transfer-only mode complete. Pipeline stage skipped.")
            elif mirrored_delta_files and not stop.stop_requested():
                run_config = _clone_pipeline_config(config)
                run_config.paths.output_dir = str(pipeline_output_dir)
                run_config.paths.state_db = str(pipeline_state_db)
                run_config.paths.source_dirs = [str(mirror_root)]
                if args.chunk_only:
                    run_config.embed.enabled = False
                    run_config.enrich.enabled = False
                    run_config.extract.enabled = False
                    logger.info("Chunk-only proof mode enabled for nightly delta pipeline run.")
                elif run_config.embed.enabled:
                    gpu_idx = apply_gpu_selection()
                    logger.info("Nightly delta pipeline using GPU %d via CUDA_VISIBLE_DEVICES.", gpu_idx)

                pipeline = Pipeline(run_config)
                pipeline_stats = pipeline.run(
                    mirrored_delta_files,
                    should_stop=stop.stop_requested,
                    source_path_mapper=_build_source_mapper(source_root, mirror_root),
                )
                if pipeline_stats.files_failed > 0 or pipeline_stats.stop_requested:
                    exit_code = 2
            elif not mirrored_delta_files and scan.delta_files > 0:
                logger.warning("Nightly delta transfer produced no mirror files ready for pipeline.")
                exit_code = 2

        _write_json(
            report_path,
            {
                "timestamp": datetime.now().isoformat(),
                "config_path": str(Path(args.config).resolve()),
                "dry_run": args.dry_run,
                "transfer_only": args.transfer_only,
                "chunk_only": args.chunk_only,
                "source_root": str(source_root),
                "mirror_root": str(mirror_root),
                "transfer_state_db": str(transfer_state_db),
                "pipeline_output_dir": str(pipeline_output_dir),
                "pipeline_state_db": str(pipeline_state_db),
                "stop_file": str(stop_file) if stop_file else "",
                "stop_requested": stop.requested,
                "stop_reason": stop.reason,
                "scan_manifest": str(scan_manifest),
                "transfer_manifest": str(transfer_manifest) if transfer_stats else "",
                "input_list_path": str(input_list_path) if mirrored_delta_files else "",
                "log_path": str(log_path),
                "scan": scan.to_dict(),
                "transfer": transfer_stats.to_dict() if transfer_stats else {},
                "pipeline": pipeline_stats.to_dict() if pipeline_stats else {},
                "mirrored_delta_files": [str(path) for path in mirrored_delta_files],
                "exit_code": exit_code,
            },
        )

        if pipeline_stats:
            logger.info(
                "Nightly delta pipeline complete: %d parsed, %d failed, %d skipped, %d chunks in %.1fs",
                pipeline_stats.files_parsed,
                pipeline_stats.files_failed,
                pipeline_stats.files_skipped,
                pipeline_stats.chunks_created,
                pipeline_stats.elapsed_seconds,
            )
        logger.info("Nightly delta report written to: %s", report_path)
        return exit_code
    finally:
        tracker.close()


if __name__ == "__main__":
    sys.exit(main())
