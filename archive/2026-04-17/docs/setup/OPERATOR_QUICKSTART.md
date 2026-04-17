# CorpusForge — Operator Quickstart

**One page. Exact commands. Copy-paste ready.**

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
- "OOM backoff" in log = GPU memory pressure (reduce embed_batch_size in config.local.yaml)
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

## Feed Export to HybridRAG V2

```bash
# From HybridRAG V2 repo:
python scripts/run_pipeline.py --input-list "C:\CorpusForge\data\output\latest\chunks.jsonl"
```

## Config Files

| File | What | Committed |
|------|------|-----------|
| `config/config.yaml` | Base config (all settings) | Yes |
| `config/config.local.yaml` | Machine overrides (workers, GPU, batch sizes) | No (gitignored) |
| `config/skip_list.yaml` | Format skip rules | Yes |
