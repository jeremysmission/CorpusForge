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

## Push Workflow (MANDATORY)
1. Commit locally (all work stays on local repo)
2. Run `python sanitize_before_push.py --apply` before ANY push to remote
3. Only the sanitized version goes to the remote/work repo
4. The remote repo is what gets zipped for deployment — no surprises in the zip
5. **NEVER push unsanitized code to remote**
6. **NEVER push `sanitize_before_push.py` itself to remote** — it contains replacement patterns and is in `.gitignore`
7. **Git commits: author is Jeremy only** — no Co-Authored-By, no AI attribution
8. **No mention of anthropic, claude, agent, or AI in any committed code/docs** — use "CoPilot+" when referring to AI assistance

## Companion Repo
HybridRAG V2 (C:\HybridRAG_V2) consumes the export packages this app produces.

## GPU Topology
- GPU 0: compute (embedding + enrichment) — check nvidia-smi before heavy work
- GPU 1: display — available for overflow but not primary compute target
