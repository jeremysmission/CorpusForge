# Recovery Action Plan — Production Corpus Ingest

**Date:** 2026-04-08
**Author:** Jeremy Randall (CoPilot+)
**Demo Target:** 2026-05-02

---

## Current State

### CorpusForge
- Sprints 1-5 complete, all QA passed
- 89 tests passing, sanitizer clean
- Per-role corpus runs on primary workstation: field_engineer (312K chunks), logistics, autocad, bulk_stress_test completed; cyber_security, system_admin still running; engineering, program_management failed (bash variable bug, need re-run)
- Tiered extraction implemented: Tier 1 regex at 4,238 chunks/sec (V2 side)
- GLiNER on CPU at 1 chunk/sec — unusable at full scale, GPU acceleration pending

### HybridRAG V2
- Sprints 12-15 complete, all QA passed
- 25/25 golden eval, 75 tests passing
- Tiered extraction ready (regex + event blocks + relationships)
- Entity store has mixed V1+V2 data — needs clean rebuild from fresh Forge export
- Demo-ready pending fresh production corpus

### Infrastructure
- primary workstation: CUDA-capable development workstation, 16 threads
- Work Desktop: 32-thread CPU, single GPU
- Work Laptop: 20-thread CPU, single GPU
- AWS AI endpoint: Successfully tested, available for chunk enrichment

---

## Big Poles in the Tent

1. **Fresh 700GB source pull + reindex** — Production corpus lives on work machines. Everything tested so far was primary workstation test subset.
2. **Dedup before chunking** — V1 lesson: 55.6% was junk. Run dedup on fresh 700GB BEFORE burning GPU cycles on chunking.
3. **GLiNER extraction speed** — 1 chunk/sec CPU unusable at scale. Tiered Tier 1 regex handles 60-70% at 4,238/sec. Tier 2 GLiNER GPU acceleration not yet benchmarked.
4. **AWS AI enrichment** — Tested endpoint works. If chunk enrichment succeeds, offloads phi4 from primary workstation, runs in parallel with local indexing.
5. **V2 entity store clean rebuild** — Mixed V1+V2 data. Needs full wipe and re-import from fresh Forge exports.

---

## Work Machine Actions (At Work Today)

### Before Pulling Data
1. `git pull` both repos (CorpusForge + HybridRAG V2) on work machines
2. Create `config.local.yaml` for each workstation:
   - Desktop: `pipeline.workers: 32`
   - Laptop: `pipeline.workers: 20`
3. Verify CUDA: `python -c "import torch; print(torch.cuda.is_available())"`

### The Pull + Reindex Sequence
1. Pull fresh 700GB source data to staging directory
2. Run CorpusForge dedup FIRST — chunk-only mode (no GPU needed):
   ```
   python scripts/run_pipeline.py --input /path/to/700gb/ --full-reindex --log-file logs/dedup_pass.log
   ```
   Set `embed.enabled: false`, `enrich.enabled: false`, `extract.enabled: false` in config
3. Review dedup report — how much is duplicate/junk vs real content
4. Run dedup review on flagged families (document-level)
5. Freeze `canonical_files.txt`
6. Re-run with `embed.enabled: true` on canonical files only — CUDA indexing
7. Export chunks.jsonl + vectors.npy

### AWS Enrichment Testing
- Take a subset of chunks.jsonl (1000 chunks)
- Feed to AWS AI endpoint for contextual enrichment
- Compare: AWS enrichment quality vs local phi4 enrichment quality
- If AWS works well — bulk enrichment in parallel with local indexing

---

## primary workstation Actions (Home)

### Immediate
1. Let cyber_security and system_admin per-role runs finish
2. Re-run engineering and program_management (failed due to bash variable bug)
3. Compile per-persona coverage report from all completed role directories

### After Work Data Arrives
1. primary workstation becomes dedup + quality review machine
2. Run document-level dedup on 700GB pull
3. Run Forge full pipeline (parse + embed + extract) on deduped canonical set
4. Export to V2 — clean entity store rebuild
5. Run golden eval on fresh data — real demo proof

---

## New Sprints

### Sprint 6 (Forge): Production Corpus Ingest — CRITICAL PATH

| Slice | What | Where | Priority |
|-------|------|-------|----------|
| 6.1 | Pull fresh 700GB source data | Work machines | P0 |
| 6.2 | Chunk-only dedup pass (no GPU, fast) | Work machines or primary workstation | P0 |
| 6.3 | Dedup review + canonical file list freeze | primary workstation | P0 |
| 6.4 | Full pipeline on canonical set (CUDA embed + extract) | primary workstation or work desktop (32 threads) | P0 |
| 6.5 | AWS enrichment test on chunk subset | Work machines (API access) | P1 |
| 6.6 | Export and deliver to V2 | primary workstation | P0 |

**Exit Criteria:** Deduped canonical corpus chunked, embedded, entities extracted, exported for V2 import.

### Sprint 16 (V2): Clean Corpus Import + Final Eval

| Slice | What | Priority |
|-------|------|----------|
| 16.1 | Wipe entity store, import fresh Forge Sprint 6 export | P0 |
| 16.2 | Run tiered extraction (Tier 1 regex + Tier 2 GLiNER) on full corpus | P0 |
| 16.3 | Golden eval on production data — target 20/25 | P0 |
| 16.4 | Demo rehearsal on real corpus | P0 |

**Exit Criteria:** Clean V2 store from production corpus, 20/25 golden eval, demo rehearsed.

---

## Daily Action Plan

| Time | Action | Where |
|------|--------|-------|
| Morning | Review overnight results, prod stale agents | primary workstation |
| At work | Pull 700GB source data to staging | Work machine |
| At work | git pull both repos, set up config.local.yaml | Work machines |
| At work | Test AWS enrichment on chunk subset | Work machine |
| At work | Start chunk-only dedup pass on fresh data | Work desktop (32 threads) |
| Tonight | Review dedup results, freeze canonical list | primary workstation |
| Overnight | Full CUDA pipeline on canonical set | primary workstation or work desktop |

---

## Bottleneck Reference

| Stage | primary workstation Speed | Work Desktop Speed | Notes |
|-------|------------|-------------------|-------|
| Parse (16 workers) | ~52 files/min | ~100 files/min (32 threads) | PDF cmap warnings slow parse |
| Embed (CUDA) | 177 chunks/sec | TBD | GPU dependent |
| Enrich (Ollama phi4) | 1.2 chunks/sec | N/A (no Ollama at work) | Use AWS instead |
| Extract Tier 1 (regex) | 4,238 chunks/sec | Similar | CPU-bound, scales with threads |
| Extract Tier 2 (GLiNER CPU) | 1.0 chunks/sec | Similar | GPU acceleration pending |

---

Jeremy Randall (CoPilot+) | 2026-04-08
