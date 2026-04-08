# Canonical List Rebuild Handoff 2026-04-07

## Purpose

Use `canonical_files.txt` as the controlled handoff from recovery dedup into chunking/rebuild.

This is the approved bridge between:

- document-level dedup review
- actual Forge chunk/export runs

---

## Source Of Truth

The canonical list is produced by document dedup:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\build_document_dedup_index.py --input "<SOURCE_FOLDER>"
```

That output directory contains:

- `canonical_files.txt`
- `document_dedup.sqlite3`
- `duplicate_files.jsonl`
- `dedup_report.json`

Do not hand-build the canonical list by copy/paste if the dedup output already exists.

---

## Review Before Rebuild

Use the approved human-review lane first:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\review_dedup_samples.py --dedup-dir "<DOCUMENT_DEDUP_OUTPUT_DIR>"
```

Use document-level review as the decision source.

---

## Run The Rebuild From The Canonical List

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\run_pipeline.py --input-list "<DOCUMENT_DEDUP_OUTPUT_DIR>\\canonical_files.txt"
```

---

## Safe Validation Mode

If you want the run to abort when the canonical list contains missing paths:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\run_pipeline.py --input-list "<DOCUMENT_DEDUP_OUTPUT_DIR>\\canonical_files.txt" --strict-input-list
```

This is the recommended first pass for a rebuild from a large recovered source tree.

What it now reports explicitly:

- duplicate entries removed from the list
- missing paths in the list
- deferred formats that will be hash-skipped
- unsupported extensions excluded before parse

---

## Recommended Order

1. Run document dedup.
2. Review duplicate families with the document-level review workflow.
3. Dry-run or strict-run the canonical list handoff.
4. Only then run the real rebuild from `canonical_files.txt`.

---

## Why This Matters

`canonical_files.txt` should be treated as a controlled production boundary.

If that file has drifted paths, duplicate entries, or hidden unsupported families, the rebuild should say so clearly instead of silently mutating the corpus shape.
