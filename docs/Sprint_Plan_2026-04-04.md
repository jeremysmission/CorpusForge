# CorpusForge — Sprint Plan (4-Week Demo Target)

**Author:** Jeremy Randall (CoPilot+)
**Repo:** CorpusForge
**Date:** 2026-04-04 MDT
**Demo Target:** 2026-05-02 (aligned with HybridRAG V2)
**Dependency:** HybridRAG V2 consumes CorpusForge's export packages

---

## Guiding Principles

1. **CorpusForge must produce V2-consumable exports by end of Sprint 1.** V2 can't demo without data.
2. **Reuse V1 code aggressively.** 60-70% of core logic is already written and tested.
3. **Enrichment and entity extraction are Sprint 2.** Sprint 1 delivers chunks and vectors.
4. **500 lines per class max** (comments excluded).
5. **Incremental from day one.** Nightly runs must be fast — minutes, not hours.

---

## Sprint 1: Core Pipeline (Week 1 — April 5-11)

**Goal:** Parse, chunk, embed, and export. Produce a package V2 can import and query.

### Slice 1.1: Repo Bootstrap + Config (Day 1)
- [ ] Initialize git repo, CoPilot+.md, .gitignore, sanitize_before_push.py
- [ ] Create directory structure
- [ ] Port Pydantic config schema (source paths, output path, chunk settings, GPU settings)
- [ ] Write config.yaml

### Slice 1.2: Download & Hash (Day 1-2)
- [ ] Implement `download/syncer.py` — file copy from configured source directories
- [ ] Implement `download/hasher.py` — SHA-256 content hashing
- [ ] Implement `download/deduplicator.py` — _1 suffix detection + content-hash dedup
- [ ] SQLite file state table (path, hash, mtime, size, status)

### Slice 1.3: Parse (Day 2-3)
- [ ] Port 32 parsers from V1 — split into individual files under `src/parse/parsers/`
- [ ] Implement `parse/dispatcher.py` — route by extension
- [ ] Implement `parse/quality_scorer.py` — score 0.0-1.0
- [ ] Implement `parse/ocr.py` — pytesseract + Poppler pipeline
- [ ] Error isolation: try/except per file, never crash pipeline

### Slice 1.4: Chunk + Embed (Day 3-5)
- [ ] Port `chunk/chunker.py` from V1 (1200/200, sentence boundary)
- [ ] Port `chunk/chunk_ids.py` — deterministic SHA-256 IDs
- [ ] Port `embed/embedder.py` — CUDA primary + ONNX fallback
- [ ] Port `embed/batch_manager.py` — token-budget batching + OOM backoff
- [ ] Verify: nomic-embed-text v1.5 produces 768-dim float16 vectors

### Slice 1.5: Export + Pipeline Orchestrator (Day 5-7)
- [ ] Implement `export/packager.py` — write chunks.jsonl + vectors
- [ ] Implement `export/manifest.py` — generate manifest.json
- [ ] Implement `pipeline.py` — orchestrate all stages sequentially
- [ ] Implement `scripts/run_pipeline.py` — CLI entry point
- [ ] Test: run pipeline on small subset (~100 files), verify V2 can import

### Sprint 1 Exit Criteria
- [ ] Pipeline runs end-to-end on test corpus
- [ ] Export package produced with chunks.jsonl + vectors + manifest.json
- [ ] HybridRAG V2 successfully imports the export package
- [ ] V2 can answer basic semantic queries against CorpusForge output
- [ ] Incremental mode works (re-run skips unchanged files)

---

## Sprint 2: Enrichment + Entity Extraction (Week 2 — April 12-18)

**Goal:** Add contextual enrichment and first-pass entity extraction to the pipeline.

### Slice 2.1: Contextual Enrichment (Day 1-3)
- [ ] Implement `enrich/ollama_client.py` — local Ollama API for phi4:14B
- [ ] Implement `enrich/enricher.py` — generate context prefix per chunk
- [ ] Enrichment prompt: document title, section heading, topic summary
- [ ] Incremental: only enrich new/changed chunks (checkpoint tracking)
- [ ] GPU memory management: phi4:14B (~9GB) + embedder on separate GPU if available

### Slice 2.2: GLiNER2 Entity Extraction (Day 3-5)
- [ ] Implement `extract/ner_extractor.py` — GLiNER2 zero-shot NER
- [ ] Entity types: PART_NUMBER, PERSON, SITE, DATE, ORGANIZATION, FAILURE_MODE
- [ ] Output: candidate_entities.jsonl with confidence scores
- [ ] Run on CPU (does not compete with GPU for embedding/enrichment)
- [ ] **Fallback if GLiNER waiver blocked:** skip first-pass, V2 uses GPT-4o for all extraction

### Slice 2.3: Updated Export (Day 5-6)
- [ ] Add enriched_text to chunks.jsonl
- [ ] Add entities.jsonl to export package
- [ ] Update manifest.json with enrichment/extraction stats
- [ ] Test: V2 imports enriched chunks, BM25 search uses enriched text

### Slice 2.4: Run Report (Day 6-7)
- [ ] Implement run_report.json generation
- [ ] Stats: files processed/skipped/failed, chunks created, entities extracted
- [ ] Timing per stage
- [ ] Error summary with file paths

### Sprint 2 Exit Criteria
- [ ] Enriched chunks produce better retrieval in V2 (A/B test on golden queries)
- [ ] Entity extraction produces candidate entities V2 can validate
- [ ] Run report provides operational visibility
- [ ] Full pipeline (download → export) runs end-to-end with all stages

---

## Sprint 3: GUI + Scheduling (Week 3 — April 19-25)

**Goal:** Monitoring GUI and automated nightly scheduling.

### Slice 3.1: GUI (Day 1-4)
- [ ] Implement `gui/app.py` — main Tkinter window (V2 aesthetic)
- [ ] Implement `gui/progress_panel.py` — pipeline stage, progress bar, ETA
- [ ] Implement `gui/status_panel.py` — last run stats, error count
- [ ] Implement `gui/theme.py` — shared dark/light color scheme
- [ ] "Run Now" button for manual trigger
- [ ] Run history (last 10 runs)

### Slice 3.2: Scheduling (Day 4-5)
- [ ] Implement `scripts/schedule_nightly.py` — Windows Task Scheduler setup
- [ ] Headless mode (no GUI, log to file)
- [ ] Configurable schedule time in config.yaml

### Slice 3.3: Audit Tool (Day 5-7)
- [ ] Implement `scripts/audit_index.py` — "what did we process?" report
- [ ] File counts by format, parse success rate, chunk distribution
- [ ] Duplicate detection report
- [ ] Quality score distribution
- [ ] Entity extraction coverage

### Sprint 3 Exit Criteria
- [ ] GUI shows real-time pipeline progress
- [ ] Nightly schedule configured and tested
- [ ] Audit report provides corpus visibility

---

## Sprint 4: Production Hardening (Week 4 — April 26 - May 2)

**Goal:** Run against full production corpus, harden for demo.

### Slice 4.1: Full Corpus Run (Day 1-4)
- [ ] Run pipeline against full 420K file corpus
- [ ] Monitor: memory, GPU utilization, disk I/O, timing
- [ ] Fix any scale-related issues (file handle limits, SQLite locking, etc.)
- [ ] Verify: V2 import handles full-scale export

### Slice 4.2: Performance Tuning (Day 4-6)
- [ ] Optimize batch sizes for Beast GPU topology (GPU 0 compute, GPU 1 display)
- [ ] Optimize SQLite WAL mode for concurrent reads during export
- [ ] Profile memory usage on full corpus
- [ ] Target: incremental nightly run < 90 minutes

### Slice 4.3: Demo Prep (Day 6-7)
- [ ] Verify V2 demo queries work against CorpusForge-produced data
- [ ] Document: "How to run CorpusForge from scratch"
- [ ] Document: "How to check if tonight's run succeeded"
- [ ] Final audit report on production corpus

### Sprint 4 Exit Criteria
- [ ] Full corpus processed successfully
- [ ] Incremental nightly run under 90 minutes
- [ ] V2 demo queries produce correct answers on CorpusForge data
- [ ] Operator documentation complete

---

Jeremy Randall | CorpusForge | 2026-04-04 MDT
