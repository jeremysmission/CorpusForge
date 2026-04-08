# Chunk Export for AWS AI Enrichment Testing

**Date:** 2026-04-07
**Author:** Jeremy Randall (CoPilot+)

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

**E2E proof run — 198 real files, mixed formats (txt, xml, json, pdf, html):**

| Metric | Value |
|--------|-------|
| Files input | 198 |
| Files parsed | 118 |
| Files skipped (OCR sidecar) | 74 |
| Files failed (empty PDFs) | 6 |
| Chunks produced | 17,695 |
| Chunks enriched | 0 (Ollama not running — Sprint 3 dependency) |
| Vectors | 17,695 x 768 (float16) |
| All required fields present | Yes (7/7 in every chunk) |
| Chunk/vector count match | Yes |
| Manifest stats accurate | Yes |
| Throughput | 177.3 chunks/sec |
| Pipeline time | 99.8s |
| GPU | GPU 0 (auto-selected, RTX 3090) |
| Exit code | 0 (success) |

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
