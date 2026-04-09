# CorpusForge Morning Operator Quickstart

Purpose: one-page operator instructions for the workstation morning run, with exact settings and exact commands.

Date: 2026-04-09

## Current Clean Export

The current clean export is:

```text
C:\CorpusForge\data\production_output\export_20260409_0720
```

This export passed the SAO/RSF leak gate.

Proof file:

```text
C:\CorpusForge\data\production_output\export_20260409_0720\QUALITY_GATE_SAO_RSF_20260409_0726.txt
```

Expected verdict in that file:

```text
RESULT: PASS
```

## If You Are Starting A New Large CorpusForge Run

### 1. Launch CorpusForge

From Explorer:

- double-click [start_corpusforge.bat](C:/CorpusForge/start_corpusforge.bat)

From PowerShell:

```powershell
cd C:\CorpusForge
.\start_corpusforge.bat
```

### 2. Run The Precheck

Fast path from the GUI:

- click `Run Precheck`

Fallback from PowerShell:

```powershell
cd C:\CorpusForge
.\PRECHECK_WORKSTATION_700GB.bat
```

What you want to see:

```text
RESULT: PASS
```

Warnings are acceptable if they are clearly labeled `WARNING` and the run is still `PASS`.

### 3. Set The GUI Fields

Use these exact settings on the workstation desktop:

- `Source:` your 700GB source folder
- `Output:` `C:\CorpusForge\data\production_output`
- `Pipeline workers:` `32`
- `OCR:` `auto`
- `Embedding:` `ON`
- `Enrichment:` `OFF`
- `Entity Extraction:` `OFF`
- `Embed batch:` `256`

Then:

1. click `Save Settings`
2. click `Start Pipeline`

### 4. What To Expect If The Machine Crashes

CorpusForge keeps file-hash state in the state database, so restart is incremental.

That means:

- unchanged files can be skipped on restart
- the run does not restart from zero
- files that were in flight during the crash may be redone

This is resume-capable, but not a perfect mid-file checkpoint system.

## Environment Checks To Confirm Before A Big Run

Run these in PowerShell:

```powershell
where.exe tesseract
where.exe pdftoppm
tesseract --version
pdftoppm -h
Write-Host "TESSERACT_CMD=$env:TESSERACT_CMD"
Write-Host "HYBRIDRAG_POPPLER_BIN=$env:HYBRIDRAG_POPPLER_BIN"
Write-Host "HYBRIDRAG_OCR_MODE=$env:HYBRIDRAG_OCR_MODE"
Write-Host "HYBRIDRAG_DOCLING_MODE=$env:HYBRIDRAG_DOCLING_MODE"
```

What matters:

- `Tesseract` matters for image OCR
- `Poppler` plus `Tesseract` matter for scanned-PDF OCR
- these matter for `CorpusForge`, not for V2 directly

If Poppler is missing, the run can still succeed, but scanned PDFs degrade.

## What To Deliver After The Run Finishes

Do not cherry-pick files out of the export.

Hand off the entire timestamped export folder:

```text
export_YYYYMMDD_HHMM
```

That folder should contain:

- `chunks.jsonl`
- `vectors.npy`
- `manifest.json`
- `run_report.txt`
- `skip_manifest.json`
- `READ_ME_BEFORE_USE.txt`

## Current Morning V2 Import Command

For the clean Run 6 export, use:

```powershell
cd C:\HybridRAG_V2
.venv\Scripts\python.exe scripts\import_embedengine.py --source C:\CorpusForge\data\production_output\export_20260409_0720 --create-index
```

No `--exclude-source-glob` filter is needed for Run 6.

## If You Need The Full Detailed Runbook

See:

- [OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md](C:/CorpusForge/docs/OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md)
