# Nightly Delta Operations

**Date:** 2026-04-09  
**Repo:** `C:\CorpusForge`  
**Purpose:** detect nightly source-share deltas, mirror only the delta to local storage, then run the existing CorpusForge pipeline on that mirrored delta set.

## Delivered Artifacts

- `src/download/delta_tracker.py`
  Source-side delta tracker backed by `transfer_state_db`. Reuses the existing hasher schema and status contract:
  - `hashed` = detected and fingerprinted, waiting for a successful mirror step
  - `mirrored` = copied or already present in the local mirror and safe to skip on the next scan
- `src/download/syncer.py`
  Transfer stop support tightened for nightly use. The copy layer now preserves source mtimes so mirrored delta files keep stable chunk IDs when the export writes original source provenance.
- `scripts/run_nightly_delta.py`
  Headless orchestrator for scan -> transfer -> pipeline -> report.
- `scripts/install_nightly_delta_task.py`
  Emits or installs the Windows Task Scheduler task for the nightly lane.
- `config/config.yaml` and `src/config/schema.py`
  Active runtime wiring for the nightly lane.

## Active Config Keys

Nightly settings live under `nightly_delta` in `C:\CorpusForge\config\config.yaml`.

- `source_root`
  Upstream source tree to scan.
- `mirror_root`
  Local C: mirror that receives only the detected delta files.
- `transfer_state_db`
  SQLite state DB for source-side `hashed`/`mirrored` tracking.
- `manifest_dir`
  Location for scan, transfer, input-list, and summary JSON artifacts.
- `pipeline_output_dir`
  Export root used by the standard CorpusForge pipeline run.
- `pipeline_state_db`
  Pipeline state DB used by the pipeline stage.
- `pipeline_log_dir`
  Log directory for the nightly runner.
- `stop_file`
  Sentinel file checked between stages for clean stop behavior.
- `transfer_workers`
  Parallel file-copy worker count.
- `canary_globs`
  Filename globs surfaced separately in the delta reports.
- `require_canary`
  Optional fail-closed gate for development proofs.
- `task_name`
  Scheduled task name used by the installer helper.
- `task_start_time`
  Daily task start time in `HH:MM`.

## Runtime Behavior

`scripts/run_nightly_delta.py` is the accepted entry point for this lane.

1. Scan `nightly_delta.source_root` with `NightlyDeltaTracker`.
2. Write `nightly_delta_scan_<timestamp>.json`.
3. Mirror only `delta_paths` into `nightly_delta.mirror_root`.
4. Write `nightly_delta_transfer_<timestamp>.json`.
5. Write `nightly_delta_input_<timestamp>.txt` with the mirrored delta subset.
6. Run `Pipeline.run()` on that mirrored subset.
7. Preserve original source provenance in exported chunks via `source_path_mapper`, so chunk `source_path` points at the upstream source tree, not the local mirror.
8. Write `nightly_delta_report_<timestamp>.json`.

Clean stop behavior:

- Ctrl+C, `SIGTERM`, or `SIGBREAK` triggers a cooperative stop.
- Creating `nightly_delta.stop_file` triggers the same cooperative stop at the next stage boundary.
- Copy tasks already running are allowed to finish; queued work is not expanded once stop is requested.
- The existing pipeline stop semantics remain unchanged.

## Proof Run

Proof root used for this lane:

- `C:\CorpusForge\data\nightly_delta_proof_20260409`

Proof config:

- `C:\CorpusForge\data\nightly_delta_proof_20260409\config.nightly_delta_proof.yaml`

Exact proof command:

```powershell
C:\CorpusForge\.venv\Scripts\python.exe `
  C:\CorpusForge\scripts\run_nightly_delta.py `
  --config C:\CorpusForge\data\nightly_delta_proof_20260409\config.nightly_delta_proof.yaml `
  --chunk-only
```

Proof source subset:

- `C:\CorpusForge\data\nightly_delta_proof_20260409\igs_source\nightly_canary_alpha.txt`
- `C:\CorpusForge\data\nightly_delta_proof_20260409\igs_source\delta_report.txt`

Observed results from the saved per-pass reports:

- Pass 1, report `nightly_delta_report_20260409_193522.json`
  - scan: `2 total`, `2 delta`, `2 new`, `0 changed`, `1 canary`
  - transfer: `2 copied`, `0 failed`
  - pipeline: `2 parsed`, `2 chunks`, `0 vectors`, `exit_code=0`
- Pass 2 after editing `delta_report.txt`, report `nightly_delta_report_20260409_193524.json`
  - scan: `2 total`, `1 delta`, `0 new`, `1 changed`, `1 unchanged`
  - transfer: `1 copied`, `0 failed`
  - pipeline: `1 parsed`, `1 chunk`, `0 vectors`, `exit_code=0`
- Pass 3 with no further source change, report `nightly_delta_report_20260409_193604.json`
  - scan: `2 total`, `0 delta`, `2 unchanged`
  - transfer: skipped
  - pipeline: skipped
  - `exit_code=0`

Proof artifacts:

- `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_scan_20260409_193522.json`
- `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_transfer_20260409_193522.json`
- `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_input_20260409_193522.txt`
- `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_report_20260409_193522.json`
- `C:\CorpusForge\data\nightly_delta_proof_20260409\nightly_delta_task.generated.xml`

Source-provenance proof:

- Exported chunk `source_path` points at `C:\CorpusForge\data\nightly_delta_proof_20260409\igs_source\delta_report.txt`
- The mirrored path `C:\CorpusForge\data\nightly_delta_proof_20260409\mirror\...` is not written into exported chunks

Known proof caveat:

- Packager export directories are minute-granular today. Pass 1 and Pass 2 both wrote to `export_20260409_1935`.
- The authoritative per-pass results for this lane are the nightly report JSON files plus `output\run_history.jsonl`.
- This lane does not change packager timestamp resolution.

## Scheduled Task Helper

Emit XML only:

```powershell
C:\CorpusForge\.venv\Scripts\python.exe `
  C:\CorpusForge\scripts\install_nightly_delta_task.py `
  --config C:\CorpusForge\data\nightly_delta_proof_20260409\config.nightly_delta_proof.yaml `
  --emit-xml C:\CorpusForge\data\nightly_delta_proof_20260409\nightly_delta_task.generated.xml
```

Install on the workstation:

```powershell
C:\CorpusForge\.venv\Scripts\python.exe `
  C:\CorpusForge\scripts\install_nightly_delta_task.py `
  --config C:\CorpusForge\config\config.yaml `
  --install `
  --force
```

The proof lane validated XML generation only. It did not install the scheduled task on the workstation.

## Validation Coverage

Focused tests:

```powershell
C:\CorpusForge\.venv\Scripts\python.exe -m pytest `
  tests\test_config.py `
  tests\test_syncer.py `
  tests\test_file_state_accounting.py `
  tests\test_pipeline_e2e.py `
  tests\test_nightly_delta.py
```

Automated GUI regression:

```powershell
C:\CorpusForge\.venv\Scripts\python.exe -m pytest `
  tests\test_gui_button_smash.py `
  tests\test_gui_dedup_only.py
```

GUI note:

- This lane did not modify GUI files.
- Because no GUI path changed in this lane, the mandatory Tier A-D plus non-author human button smash gate was not triggered for signoff.
- Automated GUI regression was still run to confirm stop/telemetry behavior remained intact.

OCR note:

- `where.exe tesseract` -> not found
- `where.exe pdftoppm` -> not found
- This lane is validated as text-first only. No OCR or scanned-document claims are made for this workstation.
