# CorpusForge — Agent Instructions

## Project Overview
CorpusForge is the nightly ingest pipeline that transforms raw source documents (420K+ files, 67+ formats) into query-ready artifacts consumed by HybridRAG V2. It runs on a dedicated GPU workstation as a scheduled task.

## Pipeline
Download → Hash/Dedup → Parse (32+ formats) → Chunk (1200/200) → Enrich (phi4:14B) → Embed (nomic v1.5, 768d) → Extract (GLiNER2 NER) → Export

## Code Rules
- **500 lines max per class** (comments excluded)
- **All file reads: `encoding="utf-8-sig"`** (strips BOM from corporate files)
- **All file writes: `encoding="utf-8", newline="\n"`** (clean UTF-8, Unix line endings)
- **DO NOT use `pip install sentence-transformers[onnx]`** — nukes CUDA torch
- **Set `NO_PROXY=127.0.0.1,localhost`** in all batch/script files
- **Set `PYTHONUTF8=1`** in all batch/script files
- **pip install commands need `--trusted-host` flags** for corporate proxy

## Companion Repo
HybridRAG V2 (C:\HybridRAG_V2) consumes the export packages this app produces.

## GPU Topology
- GPU 0: compute (embedding + enrichment) — check nvidia-smi before heavy work
- GPU 1: display — available for overflow but not primary compute target
