# CorpusForge Workstation 700GB Operator Runbook

Purpose: exact operator steps for running a large source-folder ingest on a workstation, with no guessing about which GUI fields to use or what to hand off to V2.

Audience: operator running a large local source folder such as a 700 GB delivery.

Date: 2026-04-09

## Bottom Line

For the current proven large-ingest Phase 1 path:

- set `Pipeline workers` to the machine's logical CPU thread count
- leave `OCR` at `auto`
- keep `Embedding` ON
- keep `Enrichment` OFF
- keep `Entity Extraction` OFF
- start the run from the main GUI with the `Source`, `Output`, and `Start Pipeline` controls
- when it finishes, hand off the entire timestamped `export_YYYYMMDD_HHMM` folder, not individual files

## Which Worker Count To Use

Use the machine's logical CPU thread count, not physical cores.

- workstation desktop: `32`
- workstation laptop: `20`
- primary workstation: `16`

If you are using the workstation desktop, set `Pipeline workers` to `32`.

## Exact GUI Labels You Will Use

The normal CorpusForge GUI has these operator-facing sections:

- main control area:
  - `Source:`
  - `Output:`
  - `Start Pipeline`
  - `Stop`
- `Settings`
  - `Pipeline workers:`
  - `OCR:`
  - `Chunk size:`
  - `Overlap:`
  - `Embedding`
  - `Enrichment`
  - `Entity Extraction`
  - `Enrich concurrent:`
  - `Extract batch:`
  - `Embed batch:`
  - `Save Settings`
- status bar:
  - `Pipeline workers: N logical threads`

## Before You Start

1. Confirm the source folder is fully present on a local drive the workstation can read.
2. Confirm the workstation has enough free disk for:
   - the export package
   - the state DB
   - temporary parser/embed work
3. Confirm you are in the correct repo:
   - `C:\CorpusForge`
4. Confirm the workstation type:
   - desktop uses `32` workers
   - laptop uses `20` workers

## Config Settings To Confirm Before The Run

The GUI settings are written to:

```text
C:\CorpusForge\config\config.yaml
```

Before a large run, confirm these settings are what you intend:

- `paths.output_dir`
- `paths.state_db`
- `pipeline.workers`
- `parse.ocr_mode`
- `parse.defer_extensions` if you intentionally want formats deferred for this run
- `skip.*` if you intentionally want durable skip/defer policy changed for this lane
- `enrich.enabled`
- `extract.enabled`
- `hardware.embed_batch_size`

Quick PowerShell check:

```powershell
Get-Content C:\CorpusForge\config\config.yaml
```

For the current large-ingest Phase 1 path, the important values are:

- `pipeline.workers: 32` on workstation desktop, `20` on workstation laptop
- `parse.ocr_mode: auto`
- `enrich.enabled: false`
- `extract.enabled: false`
- `hardware.embed_batch_size: 256`

If this run intentionally defers known low-value formats, confirm `parse.defer_extensions` contains those dotted lowercase extensions before you start.

Durable skip/defer policy is also read from the same live file through the `skip:` block in `config/config.yaml`. Consuming code paths: `src/pipeline.py::__init__` for per-run defer merge and `src/skip/skip_manager.py::_load_skip_source` / `src/skip/skip_manager.py::SkipManager.should_skip` for durable skip policy.

## Env Vars To Confirm

These env vars affect parser behavior:

- `TESSERACT_CMD`
- `HYBRIDRAG_POPPLER_BIN`
- `HYBRIDRAG_OCR_MODE`
- `HYBRIDRAG_DOCLING_MODE`

Quick PowerShell check:

```powershell
Write-Host "TESSERACT_CMD=$env:TESSERACT_CMD"
Write-Host "HYBRIDRAG_POPPLER_BIN=$env:HYBRIDRAG_POPPLER_BIN"
Write-Host "HYBRIDRAG_OCR_MODE=$env:HYBRIDRAG_OCR_MODE"
Write-Host "HYBRIDRAG_DOCLING_MODE=$env:HYBRIDRAG_DOCLING_MODE"
```

Native OCR tool check:

```powershell
where.exe tesseract
where.exe pdftoppm
tesseract --version
pdftoppm -h
```

How to interpret them:

- `TESSERACT_CMD`: set this if `tesseract.exe` is not already on `PATH`
- `HYBRIDRAG_POPPLER_BIN`: set this if you want scanned-PDF rasterize-and-OCR support
- `HYBRIDRAG_OCR_MODE`: optional override. If blank, config drives runtime. For the normal workstation path, leave blank unless you intentionally want an override.
- `HYBRIDRAG_DOCLING_MODE`: optional dev-only override. Leave blank for the normal workstation path unless you are intentionally testing Docling.

GPU note:

- `CUDA_VISIBLE_DEVICES` is set automatically by CorpusForge at run start via the GPU selector.
- Do not pre-set it unless you intentionally want to pin the run to a specific GPU.

Important scope note:

- Tesseract and Poppler matter for **CorpusForge**, not for V2 directly.
- Tesseract is used for image OCR.
- Poppler plus Tesseract are used for scanned-PDF OCR fallback.
- If both are missing, the pipeline still runs, but scanned PDFs and images degrade.

## Launch The GUI

Run this from PowerShell:

```powershell
cd C:\CorpusForge
.venv\Scripts\activate
python scripts\boot.py
```

Expected result:

- the CorpusForge GUI opens
- the status bar appears at the bottom
- the status bar shows `Pipeline workers: ... logical threads`
- the `Pipeline Control` section includes a `Run Precheck` button

## Set The Source Folder

In the main control area:

1. In `Source:`, either paste the full source folder path or click `Browse`.
2. Point it at the folder you want Forge to ingest.

Example:

```text
D:\Your700GBSource
```

Do not point this at an export folder. Point it at the raw source tree you want parsed.

## Run The Precheck Before The Real Run

After `Source:`, `Output:`, and the settings are set:

1. click `Run Precheck`
2. wait for the precheck result block to print into the GUI log
3. confirm the final line says `RESULT: PASS`

The same precheck can also be run outside the GUI with the fast batch launcher:

```powershell
cd C:\CorpusForge
.\PRECHECK_WORKSTATION_700GB.bat
```

The batch launcher uses the repo-local `.venv` and writes a dated text report under:

```text
C:\CorpusForge\logs\precheck_workstation_YYYYMMDD_HHMMSS.txt
```

## Set The Output Folder

In the main control area:

1. In `Output:`, either paste the full output folder path or click `Browse`.
2. Pick the parent folder where Forge should create the timestamped export directory.

Recommended standard path:

```text
C:\CorpusForge\data\production_output
```

What Forge will create when the run succeeds:

```text
C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM\
```

That timestamped export folder is the handoff unit for the next step.

## Set The Settings

In the `Settings` panel, set these values for the current large-ingest Phase 1 path:

### Required

- `Pipeline workers:` `32` on the workstation desktop, `20` on the workstation laptop
- `OCR:` `auto`
- `Embedding:` checked
- `Enrichment:` unchecked
- `Entity Extraction:` unchecked

### Leave At Current Proven Defaults Unless You Intentionally Need A Different Run Shape

- `Chunk size:` `1200`
- `Overlap:` `200`
- `Embed batch:` `256`

### Notes

- `Enrichment OFF` is intentional for the current large Phase 1 path. The large-run evidence explicitly used enrichment disabled.
- `Entity Extraction OFF` is intentional for the current Phase 1 path. Extraction is a later pass after chunks and vectors are ready.
- `OCR auto` means OCR is attempted only where the parser lane supports it and the workstation has the needed dependencies.

## Save The Settings

After you set the values:

1. Click `Save Settings`
2. Confirm the log says settings were saved to `config/config.yaml`
3. Confirm the bottom status bar shows the worker count you expect

Important:

- GUI `Save Settings` writes machine overrides to:

```text
C:\CorpusForge\config\config.yaml
```

The settings that matter most before a large run are:

- `Pipeline workers`
- `OCR`
- `Embedding`
- `Enrichment`
- `Entity Extraction`
- `Embed batch`

## Start The Run

When `Source`, `Output`, and `Settings` are correct:

1. click `Start Pipeline`
2. do not start the `Dedup-Only Pass` unless you intentionally want a review-first workflow

What happens after `Start Pipeline`:

1. Forge discovers files under the source folder
2. hashes and deduplicates them
3. skips or defers configured files
4. parses the remaining files
5. chunks the text
6. embeds the chunks
7. writes a timestamped export folder under the chosen output folder

This normal path is automatic. It does not stop for manual approval between stages.

## If The Computer Crashes Or Reboots

CorpusForge does persist file-level state, but restart behavior is not the same as a perfect mid-run checkpoint.

What is persisted:

- file-content SHA-256 hashes
- normalized file path
- file mtime
- file size
- file status in the SQLite state DB

Typical statuses recorded in the state DB:

- `hashed`
- `indexed`
- `duplicate`
- `deferred`
- `skipped`

What survives a restart:

- files already hashed during dedup, even if the run never reached export
- files already recorded as `duplicate`, `deferred`, or `skipped`
- files already recorded as `indexed` from a completed prior run

What does not currently behave like a full mid-run checkpoint:

- files processed in the current run are only marked `indexed` after the pipeline completes its normal end-to-end path
- discovery still re-enumerates the source tree on restart
- if the machine crashes during parse, chunk, embed, or export, some files from that interrupted run may be reprocessed on restart because they were not yet marked `indexed`

Practical restart rule:

- rerun the same command or GUI path
- do **not** turn on `full_reindex` unless you intentionally want to redo everything
- expect already tracked unchanged files to be skipped
- expect already hashed but unfinished work files to reuse their saved hash instead of hashing from scratch again
- expect some in-flight work from the interrupted run to be redone

So the honest statement is:

- **yes, hashing/state is persisted and restart is incremental**
- **no, the current pipeline is not a perfect exact-resume-from-the-crash-point system**

## What To Watch During The Run

Use the GUI status/progress plus the log panel.

Healthy signs:

- progress counts move during dedup, parse, and embed
- the status bar still shows the intended worker count
- the log keeps updating

Stop and inspect if you see:

- repeated parser crashes
- no progress movement for a long period
- output path errors
- a final run with `Vectors created` not matching `Chunks created`

## What Success Looks Like

A successful run writes a timestamped export folder under the `Output:` path:

```text
C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM\
  chunks.jsonl
  vectors.npy
  entities.jsonl
  manifest.json
  run_report.txt
  skip_manifest.json
```

For the current Phase 1 path:

- `chunks.jsonl` must exist
- `vectors.npy` must exist
- `manifest.json` must exist
- `run_report.txt` must exist
- `skip_manifest.json` must exist
- `entities.jsonl` may exist but can be empty when extraction is off

## What To Hand Off To The Next Step

Hand off the entire timestamped export folder.

Do not cherry-pick individual files.

Correct handoff unit:

```text
C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM\
```

That folder is what HybridRAG V2 consumes.

## Quick Validation Before Hand-Off

Run this from PowerShell:

```powershell
cd C:\CorpusForge
.venv\Scripts\activate
python tools\inspect_export_quality.py --export-dir "C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM"
```

If this is supposed to be a clean rerun with the archive leak fixed, use the gate form:

```powershell
python tools\inspect_export_quality.py --export-dir "C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM" --require-zero-source-glob "*.SAO.zip" --require-zero-source-glob "*.RSF.zip"
```

What you want to see:

- `RESULT: PASS`
- `proof: matched_chunks=0` for both forbidden patterns

## Next Step: Import Into HybridRAG V2

If the export is the handoff target and V2 is the next stage, run this from:

```powershell
cd C:\HybridRAG_V2
.venv\Scripts\python.exe scripts\import_embedengine.py --source "C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM" --create-index
```

### Current Morning Export

The current clean export is:

```text
C:\CorpusForge\data\production_output\export_20260409_0720
```

Import it into V2 with no exclude filter:

```powershell
cd C:\HybridRAG_V2
.venv\Scripts\python.exe scripts\import_embedengine.py --source C:\CorpusForge\data\production_output\export_20260409_0720 --create-index
```

Leak-gate proof for this export:

- `*.SAO.zip`: `0`
- `*.RSF.zip`: `0`
- `tools/inspect_export_quality.py` result: `PASS`

If you must fall back to the older non-canonical `Run 5` export for any reason, use the visible import filter:

```powershell
cd C:\HybridRAG_V2
.venv\Scripts\python.exe scripts\import_embedengine.py --source C:\CorpusForge\data\production_output\export_20260409_0103 --exclude-source-glob "*.SAO.zip" --exclude-source-glob "*.RSF.zip" --create-index
```

Use that only for the fallback path. Do not copy that exception forward to clean exports.

## If You Want A Review-First Workflow Instead

Use the `Dedup-Only Pass` panel only when you intentionally want a human checkpoint before the full parse/chunk/embed run.

That panel writes:

- `canonical_files.txt`
- `dedup_report.json`
- `run_report.txt`

If you use that path, the next full run should be launched from the canonical file list, not directly from the raw source tree.

## Operator Summary

If you are on the workstation desktop, the exact minimum path is:

1. launch GUI
2. set `Source:` to the 700 GB source folder
3. set `Output:` to `C:\CorpusForge\data\production_output`
4. in `Settings`, set:
   - `Pipeline workers: 32`
   - `OCR: auto`
   - `Embedding: ON`
   - `Enrichment: OFF`
   - `Entity Extraction: OFF`
   - `Embed batch: 256`
5. click `Save Settings`
6. confirm `config/config.yaml` and the relevant env vars look correct
7. click `Start Pipeline`
8. when complete, hand off the whole `export_YYYYMMDD_HHMM` folder
9. import that folder into V2 as the next step
