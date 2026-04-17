"""
Nightly delta ingest orchestrator for the stationary work desktop.

What it does for the operator:
  The "one button" nightly ingest. Three steps, in order:

    1. Scan the source share and build a JSON manifest of new or changed files.
    2. Copy ONLY those new/changed files into the local mirror folder on C:.
    3. Hand the mirrored file list to run_pipeline.py via --input-list.

  Safety feature: if --require-canary is set (or the config enables it),
  the run is aborted unless a known "canary" file is present in the delta
  -- proof that the scanner is actually seeing the upstream share.

When to run it:
  - From a Windows scheduled task every night
  - Manually, after a known upstream update
  - With --skip-pipeline to preview what would be copied, without running
    Forge

Inputs:
  --config         Base config YAML (default config/config.yaml).
  --source-root    Override upstream source root (defaults to config).
  --mirror-root    Override local mirror root (defaults to config).
  --manifest-dir   Override manifest/report directory.
  --max-files      Optional scan cap for proof / test runs.
  --skip-pipeline  Stop after the local copy; do not run the pipeline.
  --require-canary Fail if no canary file appears in the delta set.

Outputs:
  - Timestamped manifest JSON (what files are new/changed)
  - Input-list .txt (paths fed to run_pipeline.py)
  - Runtime config YAML used for this pipeline run
  - Nightly report JSON (status + transfer + pipeline outcome)
  - Log file under the configured pipeline log dir

Exit codes:
  0 = success (or no delta)
  1 = pipeline failed
  2 = transfer partial failure
  3 = canary required but missing -- operator must investigate the share

Usage:
  python scripts/nightly_delta_ingest.py --config config/config.yaml
  python scripts/nightly_delta_ingest.py --config config/config.yaml --max-files 25 --skip-pipeline
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_delta_manifest import build_delta_manifest, write_manifest
from src.config.schema import load_config
from src.download.syncer import BulkSyncer


def _run_id() -> str:
    """Return a timestamp string used as the unique run id (YYYYMMDD_HHMMSS)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_lines(path: Path, lines: list[str]) -> Path:
    """Write a list of strings as one-per-line to the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _load_raw_config(config_path: Path) -> dict:
    """Load the config YAML as a plain Python dict (not a validated ForgeConfig)."""
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8-sig") as f:
        return yaml.safe_load(f) or {}


def _write_runtime_config(
    *,
    base_config_path: Path,
    runtime_config_path: Path,
    mirror_root: Path,
    pipeline_output_dir: Path,
    pipeline_state_db: Path,
) -> Path:
    """Write a one-off config YAML for this run, redirecting source/output/state paths to the nightly mirror."""
    raw = _load_raw_config(base_config_path)
    paths = raw.setdefault("paths", {})
    paths["source_dirs"] = [str(mirror_root)]
    paths["landing_zone"] = str(mirror_root)
    paths["output_dir"] = str(pipeline_output_dir)
    paths["state_db"] = str(pipeline_state_db)
    runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_config_path.write_text(
        yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )
    return runtime_config_path


def run_nightly_delta_ingest(
    *,
    config_path: Path,
    source_root: Path | None = None,
    mirror_root: Path | None = None,
    manifest_dir: Path | None = None,
    max_files: int | None = None,
    require_canary: bool | None = None,
    skip_pipeline: bool = False,
) -> dict:
    """Do one end-to-end nightly delta: scan -> copy -> (optionally) run the pipeline. Returns a report dict."""
    config = load_config(config_path)
    nightly = config.nightly_delta
    run_id = _run_id()

    source_root = Path(source_root or nightly.source_root).resolve()
    mirror_root = Path(mirror_root or nightly.mirror_root).resolve()
    manifest_dir = Path(manifest_dir or nightly.manifest_dir).resolve()
    pipeline_output_dir = Path(nightly.pipeline_output_dir).resolve() / f"export_{run_id}"
    pipeline_state_db = Path(nightly.pipeline_state_db).resolve()
    pipeline_log_dir = Path(nightly.pipeline_log_dir).resolve()
    pipeline_log_path = pipeline_log_dir / f"nightly_delta_pipeline_{run_id}.log"
    runtime_config_path = manifest_dir / f"nightly_delta_runtime_config_{run_id}.yaml"
    manifest_path = manifest_dir / f"nightly_delta_manifest_{run_id}.json"
    input_list_path = manifest_dir / f"nightly_delta_input_{run_id}.txt"
    report_path = manifest_dir / f"nightly_delta_report_{run_id}.json"

    effective_max_files = max_files if max_files is not None else nightly.max_files
    effective_require_canary = nightly.require_canary if require_canary is None else require_canary

    manifest = build_delta_manifest(
        source_root,
        mirror_root,
        canary_globs=nightly.canary_globs,
        max_files=effective_max_files,
    )
    write_manifest(manifest, manifest_path)

    summary = manifest["summary"]
    delta_entries = manifest["entries"]
    if effective_require_canary and summary["canary_matches"] == 0:
        report = {
            "run_id": run_id,
            "status": "failed_no_canary",
            "config_path": str(config_path.resolve()),
            "manifest_path": str(manifest_path),
            "summary": summary,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    delta_source_files = [Path(entry["source_path"]) for entry in delta_entries]
    delta_mirror_files = [Path(entry["mirror_path"]) for entry in delta_entries]

    transfer_stats_dict = {
        "total_files": len(delta_source_files),
        "files_copied": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "bytes_transferred": 0,
        "bytes_total": 0,
        "current_file": "",
        "elapsed_seconds": 0.0,
        "error_count": 0,
    }
    pipeline_exit_code: int | None = None
    pipeline_command: list[str] = []

    if delta_source_files:
        syncer = BulkSyncer(
            source_dir=source_root,
            dest_dir=mirror_root,
            workers=nightly.transfer_workers,
        )
        transfer_stats = syncer.run_files(delta_source_files)
        transfer_stats_dict = transfer_stats.to_dict()
        transfer_stats_dict["errors"] = transfer_stats.errors
        _write_lines(input_list_path, [str(path) for path in delta_mirror_files])
    else:
        _write_lines(input_list_path, [])

    if delta_source_files and transfer_stats_dict["files_failed"] == 0 and not skip_pipeline:
        _write_runtime_config(
            base_config_path=config_path.resolve(),
            runtime_config_path=runtime_config_path,
            mirror_root=mirror_root,
            pipeline_output_dir=pipeline_output_dir,
            pipeline_state_db=pipeline_state_db,
        )
        pipeline_log_dir.mkdir(parents=True, exist_ok=True)
        pipeline_command = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "run_pipeline.py"),
            "--input-list",
            str(input_list_path),
            "--config",
            str(runtime_config_path),
            "--log-file",
            str(pipeline_log_path),
        ]
        pipeline_exit_code = subprocess.run(
            pipeline_command,
            cwd=str(PROJECT_ROOT),
            check=False,
        ).returncode

    report = {
        "run_id": run_id,
        "status": "success",
        "config_path": str(config_path.resolve()),
        "source_root": str(source_root),
        "mirror_root": str(mirror_root),
        "manifest_path": str(manifest_path),
        "input_list_path": str(input_list_path),
        "runtime_config_path": str(runtime_config_path) if pipeline_command else None,
        "pipeline_log_path": str(pipeline_log_path) if pipeline_command else None,
        "summary": summary,
        "transfer": transfer_stats_dict,
        "pipeline": {
            "skipped": skip_pipeline or not delta_source_files,
            "exit_code": pipeline_exit_code,
            "command": pipeline_command,
            "output_dir": str(pipeline_output_dir) if pipeline_command else None,
            "state_db": str(pipeline_state_db) if pipeline_command else None,
        },
    }
    if pipeline_exit_code not in (None, 0, 2):
        report["status"] = "pipeline_failed"
    if transfer_stats_dict["files_failed"] > 0:
        report["status"] = "transfer_partial"
    if delta_source_files and effective_require_canary and summary["canary_matches"] == 0:
        report["status"] = "failed_no_canary"
    if not delta_source_files:
        report["status"] = "no_delta"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    """Parse CLI flags, run the nightly ingest, print a summary line, and return an exit code."""
    parser = argparse.ArgumentParser(description="Run the nightly delta ingest lane")
    parser.add_argument("--config", default="config/config.yaml", help="Path to base config YAML")
    parser.add_argument("--source-root", help="Override source root for this run")
    parser.add_argument("--mirror-root", help="Override local mirror root for this run")
    parser.add_argument("--manifest-dir", help="Override manifest/report directory for this run")
    parser.add_argument("--max-files", type=int, help="Optional scan limit for proof runs")
    parser.add_argument("--skip-pipeline", action="store_true", help="Stop after manifest + copy")
    parser.add_argument(
        "--require-canary",
        action="store_true",
        help="Fail if no canary file appears in the detected delta set",
    )
    args = parser.parse_args()

    report = run_nightly_delta_ingest(
        config_path=Path(args.config),
        source_root=Path(args.source_root) if args.source_root else None,
        mirror_root=Path(args.mirror_root) if args.mirror_root else None,
        manifest_dir=Path(args.manifest_dir) if args.manifest_dir else None,
        max_files=args.max_files,
        require_canary=True if args.require_canary else None,
        skip_pipeline=args.skip_pipeline,
    )

    summary = report["summary"]
    print(
        "Nightly delta ingest: "
        f"status={report['status']} "
        f"delta={summary['delta_files']} "
        f"new={summary['new_files']} "
        f"changed={summary['changed_files']} "
        f"canary={summary['canary_matches']}"
    )
    print(f"Manifest: {report['manifest_path']}")
    print(f"Input list: {report['input_list_path']}")
    if report["pipeline"]["output_dir"]:
        print(f"Pipeline output: {report['pipeline']['output_dir']}")
    if report["pipeline"]["state_db"]:
        print(f"Pipeline state DB: {report['pipeline']['state_db']}")

    if report["status"] == "failed_no_canary":
        return 3
    if report["status"] == "transfer_partial":
        return 2
    if report["status"] == "pipeline_failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
