# CorpusForge Source-to-V2 Assembly Line Guide

Purpose: explain the real operator flow from a raw source folder to a HybridRAG V2 import.

Audience: operator, owner, or overnight runner preparing a large ingest such as a 700 GB source drop.

Date: 2026-04-08

## Bottom Line

CorpusForge does not stop and wait for a human between normal stages.

A normal run is one automatic assembly line:

1. discover files
2. hash and deduplicate
3. skip or defer what should not be parsed
4. parse
5. chunk
6. enrich if enabled
7. embed if enabled
8. extract entities if enabled
9. export a V2-ready package

HybridRAG V2 is not fed live during the Forge run. Forge finishes an export package first. V2 then imports that package as a separate step.

## Where To Set Parallel Workers

The parser worker count lives here:

```text
config/config.local.yaml
  pipeline:
    workers: <number>
```

Use logical CPU threads, not physical core count.

Current workstation targets:

- desktop: `32`
- laptop: `20`

The GUI Save Settings action writes machine-specific overrides to `config/config.local.yaml`.

If `config.local.yaml` is missing, CorpusForge falls back to `config/config.yaml`.

## The Assembly Line

### Stage 0: Choose The Input Path

CorpusForge processes the path you point it at:

- `--input <folder>` for a source tree
- `--input-list <canonical_files.txt>` for a controlled reviewed list

If you use the Transfer panel or a staging folder, that is an operator workflow choice. The pipeline itself only cares about the input path it receives.

### Stage 1: Hash And Deduplicate

CorpusForge computes a SHA-256 file-content hash for each file.

It uses that hash in two ways:

- skip unchanged files on later runs
- drop duplicates before spending parse, enrichment, or embedding time

Two duplicate patterns are handled:

- `_N` suffix duplicates such as `Report.docx` and `Report_1.docx`
- any files with identical SHA-256 content, even if filenames differ

If your new 700 GB source set looks like the recent measured sample, it is realistic that dedup could cut it roughly in half. Treat that as an estimate, not a promise. The actual reduction depends on the incoming duplicate rate.

### Stage 2: Skip And Defer

After dedup, CorpusForge decides which files should be hashed and accounted for but not parsed in this run.

Typical reasons:

- deferred format by config
- OCR sidecar junk
- temp files
- zero-byte files
- encrypted files
- oversize limits

These files are still visible. They do not silently disappear.

### Stage 3: Parse

Files that survive dedup and skip/defer checks are parsed into document text.

Important reality:

- this is parallel
- parser timeouts are enforced
- failed files are recorded
- scanned-PDF and image behavior depends on Tesseract and Poppler being installed

### Stage 4: Chunk

Parsed documents are split into overlapping text chunks.

Current default shape:

- target size: about 1200 characters
- overlap: 200 characters

Each chunk gets a deterministic `chunk_id`.

### Stage 5: Enrich (Optional)

If enrichment is enabled, CorpusForge sends each chunk through the local Ollama enrichment step and adds `enriched_text`.

If enrichment is disabled, the run continues automatically with raw text only.

### Stage 6: Embed (Optional)

If embedding is enabled, CorpusForge creates vectors for the chunks and writes them to `vectors.npy`.

If embedding is disabled, the run still exports chunks, but the export is not a normal V2-ready vector package.

### Stage 7: Entity Extraction (Optional)

If extraction is enabled, CorpusForge writes first-pass entities to `entities.jsonl`.

If extraction is disabled, the run still completes and exports chunks and vectors.

### Stage 8: Export

A successful run writes a timestamped export folder under the configured output directory:

```text
data/output/export_YYYYMMDD_HHMM/
  chunks.jsonl
  vectors.npy
  entities.jsonl
  manifest.json
  run_report.txt
  skip_manifest.json
```

CorpusForge also updates `data/output/latest` to point to the newest successful export.

## Where The Hashes Live

### File Hashes

File-content SHA-256 hashes live in the SQLite state database:

```text
data/file_state.sqlite3
```

Or whatever path is set in `paths.state_db`.

That database is the continuity layer across runs. Each tracked file row stores:

- normalized file path
- SHA-256 file-content hash
- mtime
- size
- status

Typical statuses:

- `indexed`
- `duplicate`
- `deferred`
- `skipped`

This is what lets a later incremental run skip unchanged files safely.

### Skip And Defer Hashes

Files that are skipped or deferred still have their SHA-256 captured and written into `skip_manifest.json`.

That file travels with the export package for operator accounting, but the durable continuity record remains the SQLite state DB.

### Chunk IDs

Chunk IDs are not the same as file hashes.

Each `chunk_id` is a deterministic SHA-256 built from:

- normalized source path
- file mtime in nanoseconds
- chunk start offset
- chunk end offset
- chunk text fingerprint

Those chunk IDs are written into `chunks.jsonl` and then carried into V2.

### What Carries Into V2

The file-content SHA-256 does not become the primary V2 identity key.

What V2 consumes and carries forward is mainly:

- `chunk_id`
- `text`
- `enriched_text` if present
- `source_path`
- vectors aligned row-for-row with the chunks

V2 validates the export package on import, then loads the chunks into its vector store.

## What Is Automatic Versus Human-Gated

### Default Mode: Automatic

If you launch a normal Forge run, the stages run straight through automatically. There is no built-in human approval gate between dedup, parse, chunk, enrich, embed, and export.

### Controlled Mode: Human Review Between Stages

If you want a human checkpoint, create it intentionally by splitting the work:

1. run a dedup or review pass first
2. inspect the output
3. produce `canonical_files.txt`
4. run the main pipeline on that file list with `--input-list`

This is the safer mode when the source drop is large, messy, or politically important.

## Recommended Morning Workflow For A Fresh 700 GB Drop

### Fast Path

Use this when you trust the source set and want one continuous run:

```powershell
cd C:\CorpusForge
.venv\Scripts\activate
python scripts/run_pipeline.py --input "D:\Your700GBSource" --full-reindex --log-file logs\full_corpus_run.log
```

Then inspect:

- `data/output/latest`
- `run_report.txt`
- `skip_manifest.json`
- `manifest.json`

Then import into V2:

```powershell
cd C:\HybridRAG_V2
.venv\Scripts\activate
python scripts/import_embedengine.py --source "C:\CorpusForge\data\output\latest"
```

### Safer Controlled Path

Use this when you want a human checkpoint before burning full GPU time:

1. run a dedup-only or review-first pass
2. inspect duplicate families and deferred formats
3. freeze a canonical list
4. run Forge on that canonical list
5. import the resulting export into V2

Example:

```powershell
cd C:\CorpusForge
.venv\Scripts\activate
python scripts/run_pipeline.py --input-list "C:\path\to\canonical_files.txt" --strict-input-list --log-file logs\canonical_run.log
```

Then import into V2:

```powershell
cd C:\HybridRAG_V2
.venv\Scripts\activate
python scripts/import_embedengine.py --source "C:\CorpusForge\data\output\latest"
```

## Operator Checklist Before Hitting Go

- verify the source path is correct
- verify the output path has enough free space
- verify `config.local.yaml` points at the intended machine-specific paths if you are overriding defaults
- verify Tesseract and Poppler if you need OCR behavior
- verify Ollama only if enrichment is enabled
- decide whether you want fast path or controlled reviewed path
