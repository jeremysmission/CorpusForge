# Forge Export Integrity Checklist

Date: 2026-04-12
Repo: `C:\CorpusForge`
Audience: operator validating a fresh Forge desktop export before any real HybridRAG_V2 import

## Purpose

Provide one lightweight handoff gate for a large Forge export.

This checklist is designed for full production exports where loading the entire corpus into memory just to audit it is unnecessary risk.
It is a count/integrity gate, not per-row chunk schema validation.

Tonight's mandatory gate is:

1. `scripts/check_export_integrity.py` passes
2. `run_report.txt` and `skip_manifest.json` are readable and sane
3. HybridRAG_V2 accepts the export in `--dry-run` mode

## Mandatory Tonight

Do these steps on the fresh desktop export before any real V2 import:

1. capture the export directory path
2. run `scripts/check_export_integrity.py`
3. review the run report and skip summary
4. run the HybridRAG_V2 dry-run import

If any mandatory gate fails, hold the export and investigate. Do not move on to `--create-index`.

## Optional Later

Optional later work, not required tonight:

- deeper corpus audit on smaller exports or when RAM headroom is available
- richer artifact analysis using failure lists or adaptation tooling
- a real V2 import with `--create-index`

## Not Solved By This Checklist

Passing this checklist does not mean:

- Tier 2 is clean
- Tier 1 entities are clean in V2
- demo-ready aggregation claims are safe
- family-aware metadata is present in the export

This checklist only validates the Forge export and the basic Forge -> V2 handoff contract.

## Step 1: Capture The Export Path

From PowerShell:

```powershell
cd C:\CorpusForge
$export = (
  Get-ChildItem .\data\production_output -Directory -Filter 'export_*' |
  Sort-Object Name -Descending |
  Select-Object -First 1
).FullName
Write-Host "Export path: $export"
```

All later steps assume `$export` is set to the target export directory.

## Step 2: Run The Integrity Helper

From PowerShell:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe .\scripts\check_export_integrity.py --export-dir $export
```

Mandatory result:

```text
RESULT: PASS
```

What the helper checks:

- required artifact presence
- `manifest.json` readability
- `skip_manifest.json` readability
- non-empty `run_report.txt`
- `chunks.jsonl` line count
- `vectors.npy` is a readable 2D array
- `vectors.npy` row count and dimension using memory-mapped I/O
- `entities.jsonl` line count
- agreement between manifest counts and file-backed counts

What it does not check:

- per-row chunk JSON schema
- V2 import semantics

Those are covered downstream by the HybridRAG_V2 `--dry-run` import step.

Optional structured evidence artifact:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe .\scripts\check_export_integrity.py `
  --export-dir $export `
  --output-json (Join-Path $export 'integrity_report_2026-04-12.json')
```

Optional machine-readable stdout:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe .\scripts\check_export_integrity.py --export-dir $export --json
```

## Step 3: Run Report And Skip Summary Review

Review the human-readable run report:

```powershell
Get-Content (Join-Path $export 'run_report.txt') -Tail 60
```

What you want to see:

- `Files parsed` is greater than zero
- `Chunks created` is greater than zero
- `Vectors created` matches `Chunks created`
- `Entities found` may be zero for this Phase 1 packet

Review the skip/defer summary:

```powershell
Get-Content (Join-Path $export 'skip_manifest.json') -Head 80
```

What you want to see:

- the file parses cleanly
- skip reasons look explainable from the current config
- there is no sign the export silently dropped files without accounting for them

## Step 4: Export Audit Step For Tonight

Tonight's required export audit is the combination of:

- helper pass
- run report review
- skip summary review

That is the required audit for a large export.

Do not treat `scripts/audit_corpus.py` as tonight's mandatory gate for a full 10M-class export. It is better suited to smaller exports or later analysis when RAM headroom is not a concern.

## Step 5: HybridRAG_V2 Dry-Run Import Validation

From PowerShell:

```powershell
cd C:\HybridRAG_V2
.\.venv\Scripts\python.exe .\scripts\import_embedengine.py --source $export --dry-run
```

Mandatory success signals:

- no required-file errors
- no chunk/vector mismatch error
- no manifest rejection
- no strict validation failure
- dry-run summary prints the expected chunk and vector counts

Useful follow-up after the dry run:

```powershell
Get-ChildItem $export -Filter 'import_report_*_dry_run.json' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
```

If a dry-run report JSON was written, keep it with the export evidence.

## Pass / Hold / Fail

### Pass To Handoff

All of these are true:

- integrity helper passes
- run report is readable and sane
- skip manifest is readable and sane
- V2 `--dry-run` import passes

### Hold For Review

Any of these is true:

- Forge exited `2` but the export still exists
- the export looks usable, but the run report needs explanation
- the V2 dry run passes but the failure count in Forge needs coordinator review

### Fail

Any of these is true:

- missing required artifacts
- malformed non-2D `vectors.npy`
- manifest/chunk/vector counts do not align
- V2 dry-run rejects the export
- no fresh export directory was written

## If This Checklist Passes

The export is ready for the next operator decision:

- either hold it as a validated export package
- or proceed to a real HybridRAG_V2 import with `--create-index` when that lane is authorized

## Related Docs

- [FORGE_DESKTOP_RERUN_PACKET_2026-04-12.md](./FORGE_DESKTOP_RERUN_PACKET_2026-04-12.md)
- [OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md](./OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md)
