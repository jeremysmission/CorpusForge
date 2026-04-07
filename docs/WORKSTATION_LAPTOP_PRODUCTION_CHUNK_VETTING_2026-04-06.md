# Workstation Laptop Production Chunk Vetting

Date: 2026-04-06

## Purpose

This is the controlled test to decide whether the workstation laptop is safe to use for production-grade chunk creation and export work.

The goal is not just "the pipeline runs."

The goal is to prove:

- the parser stack is complete enough
- OCR actually works on scanned documents
- expected skips are explicit, not silent
- chunk output is sane enough to trust for real rebuild work

## What Counts As A Pass

The workstation laptop is considered vetted for production-grade chunking only if all of these are true:

1. `CorpusForge` runs end to end on a controlled mixed-format source folder.
2. Digital PDFs, `DOCX`, and normal office files produce non-empty chunks.
3. At least one scanned PDF and one image-only document produce useful OCR text.
4. Expected deferred files appear in `skip_manifest.json` instead of disappearing silently.
5. The export package is complete and readable:
   - `chunks.jsonl`
   - `vectors.npy`
   - `manifest.json`
   - `skip_manifest.json` when applicable
6. Spot-checked chunks are readable and not obviously garbled.
7. A second rerun on the same controlled folder does not explode into unexpected duplicate work.

## What Counts As A Fail

Treat the laptop as not yet production-safe if any of these happen:

- scanned PDFs produce empty or near-empty text when OCR should have worked
- `tesseract` or `pdftoppm` are missing
- parser failures are common on ordinary `PDF`, `DOCX`, or spreadsheet files
- files disappear with no chunk output and no skip-manifest explanation
- chunk text is obviously corrupt or truncated on the controlled sample

## Controlled Source Folder Design

Build a small but mixed folder. Target about `15-30` files total.

Include:

- `3-5` normal digital PDFs with selectable text
- `3-5` scanned PDFs that require OCR
- `2-3` `DOCX` files
- `1-2` legacy `DOC` files if available
- `2-3` spreadsheets (`XLSX` or `XLS`)
- `1-2` image-only files with readable text (`PNG`, `JPG`, `TIFF`)
- `1-2` known difficult files such as drawings, scanned forms, or exported variants
- `1-2` files expected to defer or skip cleanly if you have them

Best test content:

- scanned maintenance reports
- drawings with text callouts
- forms or tables
- one or two obvious OCR-dependent documents

## Preflight Commands

Run these from the `CorpusForge` repo root in PowerShell.

### Python and venv

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\pip.exe --version
```

### Torch and CUDA

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

### OCR tools

```powershell
where.exe tesseract
where.exe pdftoppm
```

If `tesseract` or `pdftoppm` is not found, do not trust the laptop for scanned-PDF production work yet.

## Controlled Run

Use a dedicated output root so this test stays isolated.

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\run_pipeline.py --input <CONTROLLED_SOURCE_FOLDER>
```

If you want the output to stay obviously separate, point `output_dir` in a temporary config copy to a controlled test path before running.

## What To Capture Immediately After The Run

Capture:

- the terminal summary
- the export directory path
- `manifest.json`
- `skip_manifest.json` if present
- `chunks.jsonl`

The summary should tell you:

- files found
- files parsed
- files failed
- chunks created
- chunks enriched
- vectors created

## Chunk Quality Spot Check

Open `chunks.jsonl` and manually inspect chunk text from:

- one digital PDF
- one scanned PDF
- one `DOCX`
- one spreadsheet-derived chunk
- one image-OCR chunk if present

Look for:

- readable text
- not obviously empty
- not only headers/footers
- no obvious OCR collapse into garbage
- source paths matching the expected test files

## Skip Review

If any files were skipped or deferred, inspect `skip_manifest.json`.

You want:

- every deferred file accounted for
- a reason present
- no silent losses

## Optional V2 Import Sanity Check

If you want a stronger end-to-end test, import the controlled export into a dedicated V2 store.

```powershell
cd C:\HybridRAG_V2
.\.venv\Scripts\python.exe scripts\import_embedengine.py --source <EXPORT_DIR> --dry-run
```

If the dry run looks sane, import into an isolated config/store path.

## Re-Run Stability Check

Run the same controlled source folder a second time after the first successful pass.

Goal:

- make sure rerun behavior is sane
- no catastrophic duplicate explosion
- no unexplained churn

If the second run behaves wildly differently on the same folder, do not treat the laptop as production-safe yet.

## Review Package To Hand Back

When asking for review, supply:

1. the controlled source folder path
2. a short file list or screenshot of the test contents
3. the export directory path
4. the terminal summary
5. `manifest.json`
6. `skip_manifest.json` if present
7. `5-10` representative lines or snippets from `chunks.jsonl`
8. notes on which files were expected to require OCR
9. the outputs of:
   - `where.exe tesseract`
   - `where.exe pdftoppm`
   - the torch/CUDA check

## Decision Rule

Use the workstation laptop for production chunking only if:

- the controlled sample passes cleanly
- OCR-required files prove out
- skip behavior is explicit
- chunk text looks production-usable

If the laptop passes this test, it is good enough to become:

- a shard helper
- a controlled rebuild helper
- a production support lane

If it fails, keep the high-capacity local machine as the trusted rebuild lane and treat the laptop as a repair target, not a production lane.
