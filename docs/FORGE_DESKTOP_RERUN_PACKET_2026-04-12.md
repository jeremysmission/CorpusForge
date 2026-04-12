# Forge Desktop Rerun Packet

Date: 2026-04-12
Repo: `C:\CorpusForge`
Audience: operator launching the workstation desktop full Phase 1 Forge rerun as soon as install correctness is green

## Purpose

Turn the current recommendation into one concrete launch packet:

- run the workstation desktop in unattended Forge Phase 1 mode
- produce one fresh export package
- hand that export to a lightweight integrity gate
- validate the export against HybridRAG_V2 with a dry-run import before any real V2 import

This packet is intentionally narrow. It does not cover:

- family-aware metadata contract work
- Tier 2 GLiNER stabilization
- clean Tier 1 rerun inside V2
- V2 machine orchestration beyond the dry-run handoff check

## Decision

Use the workstation desktop in `headless CLI` mode, not the GUI, for the full rerun.

Reason:

- the goal is unattended execution
- `scripts/run_pipeline.py` is the headless-safe production entry point
- the active runtime config already carries the recommended Phase 1 settings

## Mandatory Tonight

Do these steps once install correctness is confirmed:

1. run the desktop precheck and require `RESULT: PASS`
2. confirm the live runtime config still matches the approved Phase 1 settings
3. launch a headless full rerun from the raw source tree with `--full-reindex`
4. capture the newest `export_YYYYMMDD_HHMM` directory under `data\production_output`
5. run the handoff gates in [FORGE_EXPORT_INTEGRITY_CHECKLIST_2026-04-12.md](./FORGE_EXPORT_INTEGRITY_CHECKLIST_2026-04-12.md)

If step 5 fails, stop there. Do not move into a real V2 import on that export.

## Optional Later

These are not required for the desktop rerun tonight:

- deeper export analysis on smaller proof exports or when RAM headroom is available
- real V2 import with `--create-index`
- nightly-delta scheduler work
- metadata enrichment or extraction work inside Forge

## Still Blocked Outside This Packet

This packet does not solve these downstream blockers:

- Beast Tier 2 CUDA OOM loop
- clean Tier 1 rerun in V2
- clean demo-ready aggregation claims
- richer Forge metadata emission for family-aware retrieval

The desktop rerun is valuable because it creates a fresh Phase 1 export and closes the operator gap. It does not make V2 clean by itself.

## Approved Phase 1 Settings

These settings are the approved desktop rerun shape:

- `Pipeline workers`: `32`
- `OCR`: `auto`
- `Embedding`: `ON`
- `Enrichment`: `OFF`
- `Entity Extraction`: `OFF`
- `Embed batch`: `256`

Live config path:

```text
C:\CorpusForge\config\config.yaml
```

Expected active values in that file:

- `paths.output_dir: data/production_output`
- `pipeline.workers: 32`
- `parse.ocr_mode: auto`
- `embed.enabled: true`
- `enrich.enabled: false`
- `extract.enabled: false`
- `hardware.embed_batch_size: 256`

## Prerequisites

All of these should be true before launch:

- workstation desktop install correctness is green
- repo root is the authoritative repo: `C:\CorpusForge`
- source tree is present and readable
- desktop has enough free disk for a new export plus logs and state
- the operator is not relying on the desktop for a conflicting long-running GPU task

Recommended source root for this rerun:

```text
ProductionSource\verified\source\verified\IGS
```

If that path is not the intended source on the desktop, stop and correct the source path first. Do not casually substitute a parent folder.

## Step 1: Run The Precheck

From PowerShell:

```powershell
cd C:\CorpusForge
.\PRECHECK_WORKSTATION_700GB.bat
```

Mandatory result:

```text
RESULT: PASS
```

If the result is not `PASS`, do not start the rerun.

## Step 2: Confirm The Live Runtime Config

From PowerShell:

```powershell
cd C:\CorpusForge
Get-Content .\config\config.yaml
```

Confirm the values listed in `Approved Phase 1 Settings`.

Do not edit config as part of this packet unless the operator is explicitly correcting one of those values before launch.

## Step 3: Launch The Desktop Full Rerun

Recommended launch path:

```powershell
cd C:\CorpusForge
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = "logs\desktop_rerun_$ts.log"
.\.venv\Scripts\python.exe .\scripts\run_pipeline.py `
  --config .\config\config.yaml `
  --input "ProductionSource\verified\source\verified\IGS" `
  --full-reindex `
  --log-file $log
Write-Host "Log path: $log"
```

Notes:

- `--full-reindex` is mandatory for this rerun packet
- keep the live `config/config.yaml` as the runtime config
- this is a Forge Phase 1 rerun, so enrichment and extraction stay off

## Expected Output Artifacts

On a successful or usable-partial run, expect a new export directory under:

```text
C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM
```

Required artifacts in that export directory:

- `chunks.jsonl`
- `vectors.npy`
- `manifest.json`
- `run_report.txt`
- `skip_manifest.json`
- `entities.jsonl`

Also expect a new headless log under:

```text
C:\CorpusForge\logs\desktop_rerun_YYYYMMDD_HHMMSS.log
```

## Success And Fail Signals

### Best Outcome

- process exits with code `0`
- newest export directory exists
- `run_report.txt` shows:
  - `Files parsed > 0`
  - `Chunks created > 0`
  - `Vectors created == Chunks created`
  - `Entities found = 0` is expected for this packet

### Usable With Review

- process exits with code `2`
- export directory still exists
- count-alignment checks pass later in the integrity checklist
- failures are explainable from the log or `run_report.txt`

### Stop / Fail

Treat any of these as a stop:

- precheck does not pass
- process exits with code `1`
- no new export directory is written
- `chunks.jsonl` or `vectors.npy` is missing
- `Vectors created != Chunks created`
- HybridRAG_V2 dry-run import rejects the export

## Step 4: Capture The Newest Export Path

From PowerShell:

```powershell
cd C:\CorpusForge
$export = (
  Get-ChildItem .\data\production_output -Directory -Filter 'export_*' |
  Sort-Object Name -Descending |
  Select-Object -First 1
).FullName
Write-Host "Newest export: $export"
```

Use that exact path in the integrity checklist.

## Step 5: Run The Integrity Checklist

Next document:

- [FORGE_EXPORT_INTEGRITY_CHECKLIST_2026-04-12.md](./FORGE_EXPORT_INTEGRITY_CHECKLIST_2026-04-12.md)

Do not skip this step. The desktop rerun is not complete until:

- export artifacts are present
- chunk/vector/manifest counts align
- the V2 dry-run import passes

## First Operator Action Once Install Correctness Is Confirmed

Run:

```powershell
cd C:\CorpusForge
.\PRECHECK_WORKSTATION_700GB.bat
```

If it returns `RESULT: PASS`, proceed directly to the headless launch command in `Step 3`.

## Related Docs

- [OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md](./OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md)
- [MORNING_OPERATOR_QUICKSTART_2026-04-09.md](./MORNING_OPERATOR_QUICKSTART_2026-04-09.md)
- [SOURCE_TO_V2_ASSEMBLY_LINE_GUIDE_2026-04-08.md](./SOURCE_TO_V2_ASSEMBLY_LINE_GUIDE_2026-04-08.md)
