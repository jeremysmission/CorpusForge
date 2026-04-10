# CorpusForge — Operator Quickstart

**One page. Exact commands. Copy-paste ready.**

For the current workstation morning path, see:

- `docs/MORNING_OPERATOR_QUICKSTART_2026-04-09.md`

For the workstation large-ingest GUI path, see:

- `docs/OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md`

## Run from Scratch (First Time)

```bash
cd C:\CorpusForge

# 1. Activate venv
.venv\Scripts\activate

# 2. Verify CUDA
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 3. Run pipeline on your source data
python scripts/run_pipeline.py --input "C:\path\to\source\files" --full-reindex --log-file logs/run.log

# 4. Check results
python scripts/audit_corpus.py
```

## Run Nightly (Incremental)

```bash
# Only processes new/changed files since last run
python scripts/run_pipeline.py --input "C:\path\to\source\files" --log-file logs/nightly.log
```

## Run with Specific Options

```bash
# Chunk-only (no GPU needed)
python scripts/run_pipeline.py --input data/source/ --full-reindex --strip-enrichment

# From a canonical file list (post-dedup)
python scripts/run_pipeline.py --input-list canonical_files.txt --strict-input-list

# Full pipeline with enrichment + extraction
python scripts/run_pipeline.py --input data/source/ --full-reindex --log-file logs/full.log

# Optional Docling dev test lane (only if installed)
set HYBRIDRAG_DOCLING_MODE=fallback
python scripts/run_pipeline.py --input data/source/ --full-reindex --log-file logs/docling.log
```

## Schedule Nightly Run (Windows Task Scheduler)

```bash
schtasks /create /tn "CorpusForge Nightly" /xml config\nightly_task.xml
schtasks /query /tn "CorpusForge Nightly" /v
schtasks /run /tn "CorpusForge Nightly"
```

## Launch GUI

```bash
python scripts/boot.py
```

## Check if Tonight's Run Succeeded

**Quick check:**
```bash
# Last line of log shows exit summary
tail -5 logs/nightly.log

# Or check the run report
cat data/output/export_*/run_report.txt | tail -20

# Or audit the latest export
python scripts/audit_corpus.py
```

**What to look for:**
- Exit code 0 = success, 2 = partial (some files failed), 1 = fatal error
- `Files parsed` should be > 0
- `Vectors created` should equal `Chunks created`
- `run_report.txt` in the export dir has full stats

**Red flags:**
- "Files parsed: 0" = nothing was processed (check source path)
- "Enrichment disabled" in log = Ollama wasn't running (expected for --strip-enrichment)
- "OOM backoff" in log = GPU memory pressure (reduce embed_batch_size in config/config.yaml)
- Exit code 1 = config error or no files found

## Export Location

```
data/output/export_YYYYMMDD_HHMM/
  chunks.jsonl        # Chunk text + metadata (one JSON per line)
  vectors.npy         # Float16 embeddings [N, 768]
  entities.jsonl      # GLiNER entity candidates
  manifest.json       # Run metadata + stats
  run_report.txt      # Human-readable summary
  skip_manifest.json  # Files skipped with reasons
```

## Inspect Export Before Import

```bash
# Quick trust check on a specific export
python tools/inspect_export_quality.py --export-dir "C:\CorpusForge\data\output\latest"

# Production example with extra red-flag checks
python tools/inspect_export_quality.py --export-dir "C:\CorpusForge\data\production_output\export_20260409_0720" --source-glob "*.zip" --text-marker "word/document.xml"

# Canonical leak gate: command exits PASS only if both leak counts are zero
python tools/inspect_export_quality.py --export-dir "C:\CorpusForge\data\output\latest" --require-zero-source-glob "*.SAO.zip" --require-zero-source-glob "*.RSF.zip"
```

What this tool checks:

- `chunks.jsonl` is valid JSON line-by-line
- required keys exist: `chunk_id`, `text`, `source_path`
- `text_length` matches real text length when present
- top source extensions by chunk count
- suspicious `source_path` patterns such as `*.SAO.zip` and `*.RSF.zip`
- suspicious text markers such as `[Content_Types].xml` and `_rels/.rels`
- a small sample of suspicious chunks for manual review

What to look for:

- unexpected chunk volume from a format that was supposed to be deferred
- archive-heavy exports dominated by `*.zip` paths
- chunk previews that show container metadata instead of document text
- numeric dump text where you expected human-readable prose
- surprisingly high `parse_quality` on obvious junk
- gate output that ends with `RESULT: PASS` and proof lines showing `matched_chunks=0` for the forbidden patterns

## Feed Export to HybridRAG V2

```bash
# From HybridRAG V2 repo:
python scripts/import_embedengine.py --source "C:\CorpusForge\data\output\latest"
```

## Config Files

| File | What | Committed |
|------|------|-----------|
| `config/config.yaml` | Runtime config. Edit this file directly for workers, paths, parser defer list, GPU, batch sizes, and optional `parse.docling_mode`. GUI **Save Settings** writes here. Desktop workers: `32`, laptop workers: `20`. | Yes |

## Parser Env Vars

- `TESSERACT_CMD` — path to `tesseract.exe` if not already on PATH
- `HYBRIDRAG_POPPLER_BIN` — directory containing `pdftoppm.exe`
- `HYBRIDRAG_DOCLING_MODE` — optional override: `off` | `fallback` | `prefer`
- `CORPUSFORGE_INSTALL_DOCLING=1` — installer flag for the optional Docling dev dependency

Preferred control path:

- use `config/config.yaml` for stable workstation behavior
- use env vars only for temporary overrides or side-by-side parser testing
