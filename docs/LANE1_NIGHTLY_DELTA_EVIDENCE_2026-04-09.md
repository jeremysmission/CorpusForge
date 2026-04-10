# Lane 1 Nightly Delta Evidence

**Date:** 2026-04-09  
**Repo:** `C:\CorpusForge`  
**Branch:** `master`  
**Scope:** scheduler/delta ops lane for nightly source-share detection, local delta mirror, and normal CorpusForge pipeline execution on the mirrored delta subset.

## Delivered Files

Accepted lane entry points are `C:\CorpusForge\scripts\run_nightly_delta.py` and `C:\CorpusForge\scripts\install_nightly_delta_task.py`.

- `C:\CorpusForge\src\download\delta_tracker.py`
- `C:\CorpusForge\src\download\syncer.py`
- `C:\CorpusForge\src\pipeline.py`
- `C:\CorpusForge\src\config\schema.py`
- `C:\CorpusForge\config\config.yaml`
- `C:\CorpusForge\scripts\run_nightly_delta.py`
- `C:\CorpusForge\scripts\install_nightly_delta_task.py`
- `C:\CorpusForge\tests\test_config.py`
- `C:\CorpusForge\tests\test_syncer.py`
- `C:\CorpusForge\tests\test_nightly_delta.py`
- `C:\CorpusForge\docs\NIGHTLY_DELTA_OPERATIONS_2026-04-09.md`
- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`

## Hardware And Tooling

- workstation: `ASUS / System Product Name`
- GPUs present:
  - `GPU 0: NVIDIA GeForce RTX 3090`
  - `GPU 1: NVIDIA GeForce RTX 3090`
- proof GPU assignment: none
  - proof runs used `--chunk-only`, so no CUDA stage was entered and no GPU selection was needed
- OCR prerequisites:
  - `where.exe tesseract` -> not found
  - `where.exe pdftoppm` -> not found
  - this lane is documented as text-first only on this workstation; no OCR or scanned-document coverage is claimed

## Final Config State

Active nightly config is now a single `nightly_delta` block in `C:\CorpusForge\config\config.yaml`.

- `source_root = ProductionSource/verified/source/verified/IGS`
- `mirror_root = data/nightly_delta/source_mirror`
- `transfer_state_db = data/nightly_delta/source_transfer_state.sqlite3`
- `manifest_dir = data/nightly_delta/manifests`
- `pipeline_output_dir = data/production_output`
- `pipeline_state_db = data/production_state_run6.sqlite3`
- `pipeline_log_dir = logs/nightly_delta`
- `stop_file = data/nightly_delta/nightly_delta.stop`
- `task_name = CorpusForge Nightly Delta`
- `task_start_time = 02:00`

The duplicate `nightly_delta` block that previously existed in `config.yaml` was removed so operators have one authoritative runtime block.

## Exact Commands Run

Repo state and environment:

```powershell
git -C C:\CorpusForge status --short
git -C C:\CorpusForge branch --show-current
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model | Format-List
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader
where.exe tesseract
where.exe pdftoppm
```

Focused validation:

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

Proof run commands:

```powershell
C:\CorpusForge\.venv\Scripts\python.exe `
  C:\CorpusForge\scripts\run_nightly_delta.py `
  --config C:\CorpusForge\data\nightly_delta_proof_20260409\config.nightly_delta_proof.yaml `
  --chunk-only

C:\CorpusForge\.venv\Scripts\python.exe `
  C:\CorpusForge\scripts\install_nightly_delta_task.py `
  --config C:\CorpusForge\data\nightly_delta_proof_20260409\config.nightly_delta_proof.yaml `
  --emit-xml C:\CorpusForge\data\nightly_delta_proof_20260409\nightly_delta_task.generated.xml
```

Sanitizer:

```powershell
C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\sanitize_before_push.py
```

## Proof Dataset And Artifacts

Proof root:

- `C:\CorpusForge\data\nightly_delta_proof_20260409`

Proof source subset:

- `C:\CorpusForge\data\nightly_delta_proof_20260409\igs_source\nightly_canary_alpha.txt`
- `C:\CorpusForge\data\nightly_delta_proof_20260409\igs_source\delta_report.txt`

Key artifacts:

- reports:
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_report_20260409_193522.json`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_report_20260409_193524.json`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_report_20260409_193604.json`
- scans:
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_scan_20260409_193522.json`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_scan_20260409_193524.json`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_scan_20260409_193604.json`
- transfers:
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_transfer_20260409_193522.json`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_transfer_20260409_193524.json`
- input lists:
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_input_20260409_193522.txt`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\manifests\nightly_delta_input_20260409_193524.txt`
- logs:
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\logs\nightly_delta_20260409_193522.log`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\logs\nightly_delta_20260409_193524.log`
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\logs\nightly_delta_20260409_193604.log`
- task XML:
  - `C:\CorpusForge\data\nightly_delta_proof_20260409\nightly_delta_task.generated.xml`

## Proof Results

Pass 1:

- report: `nightly_delta_report_20260409_193522.json`
- scan: `2 total`, `2 delta`, `2 new`, `0 changed`, `0 resumed_hashed`, `0 unchanged`, `1 canary`
- transfer: `2 copied`, `0 skipped`, `0 failed`, `112 bytes`
- pipeline: `2 parsed`, `0 failed`, `2 chunks`, `0 vectors`, `0 entities`, `43.95 chunks/s`
- exit code: `0`

Pass 2 after editing `delta_report.txt`:

- report: `nightly_delta_report_20260409_193524.json`
- scan: `2 total`, `1 delta`, `0 new`, `1 changed`, `0 resumed_hashed`, `1 unchanged`
- transfer: `1 copied`, `0 skipped`, `0 failed`, `53 bytes`
- pipeline: `1 parsed`, `0 failed`, `1 chunk`, `0 vectors`, `0 entities`, `24.17 chunks/s`
- exit code: `0`

Pass 3 with no further source change:

- report: `nightly_delta_report_20260409_193604.json`
- scan: `2 total`, `0 delta`, `0 new`, `0 changed`, `0 resumed_hashed`, `2 unchanged`
- transfer: not run
- pipeline: not run
- exit code: `0`

Source provenance proof:

- exported chunk `source_path` resolves to `C:\CorpusForge\data\nightly_delta_proof_20260409\igs_source\delta_report.txt`
- mirrored path `C:\CorpusForge\data\nightly_delta_proof_20260409\mirror\...` is not written into exported chunk provenance

Packager note:

- pass 1 and pass 2 both wrote to `C:\CorpusForge\data\nightly_delta_proof_20260409\output\export_20260409_1935`
- the packager is minute-granular today, so `nightly_delta_report_*.json` plus `C:\CorpusForge\data\nightly_delta_proof_20260409\output\run_history.jsonl` are the authoritative per-pass records

## Validation Results

Focused test lane:

- `50 passed in 24.30s`
- suites:
  - `tests\test_config.py`
  - `tests\test_syncer.py`
  - `tests\test_file_state_accounting.py`
  - `tests\test_pipeline_e2e.py`
  - `tests\test_nightly_delta.py`

Automated GUI regression:

- `25 passed in 2.76s`
- suites:
  - `tests\test_gui_button_smash.py`
  - `tests\test_gui_dedup_only.py`

Sanitizer:

- dry-run result: `All files are clean. Ready to push.`

## Resume And Stop Behavior

- source-side nightly delta resume state is persisted in `transfer_state_db`
  - `hashed` = fingerprinted and waiting for mirror success
  - `mirrored` = already mirrored and safe to skip unless size or mtime changes
- mirrored files preserve source mtimes during copy so chunk IDs remain stable when the export writes original source provenance
- clean stop controls:
  - signal-driven stop via Ctrl+C / `SIGTERM` / `SIGBREAK`
  - sentinel stop via `nightly_delta.stop_file`
- existing pipeline hash persistence remains intact
  - `tests\test_file_state_accounting.py` passed
  - `tests\test_pipeline_e2e.py` passed

## GUI Coverage Statement

- No GUI source files were modified in this lane.
- The mandatory full GUI harness Tier A-D plus non-author human button smash gate therefore did not apply to lane signoff.
- Automated GUI regression was still executed to confirm live chunks/chunks-per-second/stop telemetry paths were not regressed by the nightly-delta work.

## Failure Taxonomy And Residual Risk

1. Operator-config mismatch, fixed
   - Prior issue: `config/config.yaml` contained two `nightly_delta` blocks.
   - Fix: collapsed to one active block so operator intent and runtime behavior are aligned.
2. OCR prerequisite gap, documented
   - `tesseract` and `pdftoppm` are absent on this workstation.
   - Impact: no OCR or scanned-document trust claim for this lane.
3. Proof export-dir reuse, documented
   - The packager currently names exports at minute resolution.
   - Impact: proof pass 1 and pass 2 reused one export directory, so the report JSONs and `run_history.jsonl` are the source of truth.
4. Production promotion still pending
   - The proof lane validated a controlled local subset and XML emission.
   - It did not install the scheduled task or execute a full real source-share nightly run on the workstation.

## Recommendation

Code path, config wiring, proof artifacts, and validation are ready for QA.

Next operational step after QA:

1. install the scheduled task on the workstation
2. run one real canary-backed nightly pass against the source share with the active `config/config.yaml`
3. inspect the emitted report JSON, log, and export manifest before relying on unattended nightly execution

V2 impact:

- no V2 runtime or store paths were written by this lane
- only `C:\HybridRAG_V2\docs\SPRINT_SYNC.md` was updated for cross-repo status sync
