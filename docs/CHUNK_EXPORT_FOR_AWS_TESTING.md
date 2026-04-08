# Chunk Export for AWS AI Enrichment Testing

**Date:** 2026-04-07
**Author:** Agent 1 (CorpusForge Coder)

## Quick Start — Produce Chunks

### Chunk-only (no GPU, no Ollama needed)
```bash
python scripts/run_pipeline.py --input data/source/ --full-reindex
```
Set `embed.enabled: false` and `enrich.enabled: false` in config.yaml first.

### Full pipeline (parse + enrich + embed)
```bash
python scripts/run_pipeline.py --input data/source/ --full-reindex --log-file logs/run.log
```

### Headless overnight run
```bash
python scripts/run_pipeline.py --input /path/to/corpus/ --log-file logs/nightly.log
```

## Export Structure

```
data/output/export_YYYYMMDD_HHMM/
  chunks.jsonl      # One JSON object per line
  vectors.npy       # Float16 numpy array [N, 768]
  entities.jsonl    # Empty until GLiNER wired (Sprint 3)
  manifest.json     # Run metadata and stats
```

## chunks.jsonl Schema

Each line is a JSON object with these fields:

| Field | Type | Description |
|-------|------|-------------|
| chunk_id | string | SHA-256 deterministic ID (path + mtime + position + text) |
| text | string | Raw chunk text |
| enriched_text | string/null | Preamble + text (if enrichment enabled and succeeded) |
| source_path | string | Absolute path to source file |
| chunk_index | int | Position within source document (0-based) |
| text_length | int | Character count of raw text |
| parse_quality | float | Parser quality score (0.0-1.0) |

## Verified Export (2026-04-07)

| Metric | Value |
|--------|-------|
| Files processed | 5 |
| Chunks produced | 12 |
| Chunks enriched | 12/12 |
| Vectors | 12 x 768 (float16) |
| Export size | ~50 KB |
| Pipeline time | 27s (enrichment + embedding) |
| Chunk-only time | 0.26s |

## For AWS AI Testing

Feed `chunks.jsonl` to your AWS enrichment pipeline. Each chunk's `text` field
contains the raw content. Use `enriched_text` if available (includes phi4
contextual preamble). The `chunk_id` is stable and deterministic — same input
produces same ID.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — chunks produced |
| 1 | Failure — no files or fatal error |
| 2 | Partial — some files failed |
