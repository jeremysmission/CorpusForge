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

## Sprint 2: Unblock Chunking + Config-Driven Formats + GUI Settings (ACTIVE — April 7+)

**Goal:** Get chunking working NOW, eliminate all hardcoded skips, make GUI human-operable with config controls. Produce chunks for AWS AI enrichment testing ASAP.

**Why this sprint exists:** Chunking broke on 2026-04-07. We need working chunk output to test enrichment through AWS AIs. GUI is monitor-only with no operator controls. Placeholder formats are hardcoded in Python, violating the "everything in config" rule.

### Slice 2.1: Diagnose and Fix Chunking Pipeline (P0 — Day 1)
- [ ] Reproduce the chunking failure from today's run
- [ ] Check uncommitted `run_pipeline.py` changes for clues
- [ ] Verify CUDA/torch availability (`python -c "import torch; print(torch.cuda.is_available())"`)
- [ ] Verify config.yaml paths resolve correctly (source_dirs, output_dir)
- [ ] Run pipeline on 10-file test subset, capture full traceback
- [ ] Fix root cause, verify chunks.jsonl + vectors.npy produced
- [ ] **Exit:** Pipeline produces chunks from real source files

### Slice 2.2: Move All Hardcoded Format Skips to Config (P0 — Day 1-2)
- [ ] Move placeholder formats (`.dwg`, `.dwt`, `.prt`, `.sldprt`, `.asm`, `.sldasm`, `.mpp`, `.vsd`, `.one`, `.ost`, `.eps`) from hardcoded `dispatcher.py` lines 138-149 into `config/skip_list.yaml` under a new `placeholder_formats` section
- [ ] `dispatcher.py` reads placeholder list from config at startup, not from hardcoded dict
- [ ] Operator can add/remove placeholder formats by editing config only
- [ ] Add `parse.defer_extensions` support in dispatcher (already in schema, wire it up)
- [ ] **Exit:** Zero hardcoded format decisions in Python — all driven from config/skip_list.yaml

### Slice 2.3: GUI Settings Panel (P1 — Day 2-3)
- [ ] Add "Settings" tab/panel to GUI alongside Pipeline Control
- [ ] **Worker count:** Spinbox to change `pipeline.workers` (1-32), updates config live
- [ ] **Chunking toggle:** Checkbox to enable/disable chunking stage
- [ ] **Enrichment toggle:** Checkbox to enable/disable `enrich.enabled`
- [ ] **Entity extraction toggle:** Checkbox to enable/disable `extract.enabled`
- [ ] **OCR mode:** Dropdown for `parse.ocr_mode` (skip/auto/force)
- [ ] **Chunk size / overlap:** Editable fields for `chunk.size` and `chunk.overlap`
- [ ] Settings changes write back to config.yaml on save (not live — requires pipeline restart)
- [ ] **Exit:** Human operator can configure all major pipeline options from GUI without editing YAML

### Slice 2.4: End-to-End Chunk Export Proof (P0 — Day 3)
- [ ] Run full pipeline on real source subset (100+ files, mixed formats)
- [ ] Verify chunks.jsonl has correct structure (chunk_id, text, source_path, metadata)
- [ ] Verify vectors.npy shape matches chunk count
- [ ] Export chunks in format ready for AWS AI enrichment testing
- [ ] Document: exact command to produce chunks for AWS testing
- [ ] **Exit:** Working chunk export, operator can produce chunks from GUI or CLI

### Sprint 2 Exit Criteria
- [ ] Chunking pipeline runs end-to-end and produces exportable chunks
- [ ] All format skip/defer decisions live in config, zero hardcoded
- [ ] GUI has settings panel with worker count, chunking, enrichment, extraction, OCR toggles
- [ ] Chunks exported and ready for AWS AI enrichment testing

---

## Sprint 3: Enrichment + Entity Extraction (Week 3 — April 14-18)

**Goal:** Wire up enrichment and entity extraction stages, produce enriched chunks.

### Slice 3.1: Contextual Enrichment Validation (Day 1-2)
- [ ] Verify enricher works with Ollama phi4:14B on Beast
- [ ] Test graceful degradation when Ollama unavailable
- [ ] Validate enriched_text field in chunks.jsonl export
- [ ] A/B: compare retrieval quality enriched vs plain chunks

### Slice 3.2: Entity Extraction Implementation (Day 2-4)
- [ ] Implement `extract/ner_extractor.py` — GLiNER2 zero-shot NER (or GPT-4o fallback)
- [ ] Entity types: PART_NUMBER, PERSON, SITE, DATE, ORGANIZATION, FAILURE_MODE, ACTION
- [ ] Output: entities.jsonl with confidence scores
- [ ] Wire into pipeline orchestrator as optional stage
- [ ] **Fallback if GLiNER waiver blocked:** GPT-4o extraction via API

### Slice 3.3: Run Report + Audit (Day 4-5)
- [ ] Run report generation (files processed, chunks, entities, timing, errors)
- [ ] Format coverage audit (what parsed, what placeholder'd, what skipped)
- [ ] Quality score distribution

### Sprint 3 Exit Criteria
- [ ] Enriched chunks produce measurably better retrieval
- [ ] Entity extraction produces candidate entities
- [ ] Run report provides operational visibility

---

## Sprint 4: GUI Polish + Scheduling (Week 4 — April 19-25)

**Goal:** Production-quality GUI and automated scheduling.

### Slice 4.1: GUI Improvements (Day 1-3)
- [ ] Run history (last 10 runs with stats)
- [ ] Format coverage display (what's parsing, what's placeholder, what's skipped)
- [ ] Deferred format management from GUI
- [ ] Error drill-down panel

### Slice 4.2: Scheduling (Day 3-5)
- [ ] Windows Task Scheduler setup script
- [ ] Headless mode (no GUI, log to file)
- [ ] Configurable schedule in config.yaml

### Slice 4.3: Audit Tool (Day 5-7)
- [ ] Comprehensive corpus audit report
- [ ] Duplicate detection report
- [ ] Quality score distribution

### Sprint 4 Exit Criteria
- [ ] GUI is production-quality for operator use
- [ ] Nightly schedule tested
- [ ] Audit report provides corpus visibility

---

## Sprint 5: Production Hardening (Week 5 — April 26 - May 2)

**Goal:** Run against full production corpus, harden for demo.

### Slice 5.1: Full Corpus Run (Day 1-4)
- [ ] Run pipeline against full 420K file corpus
- [ ] Monitor: memory, GPU utilization, disk I/O, timing
- [ ] Fix any scale-related issues (file handle limits, SQLite locking, etc.)
- [ ] Verify: V2 import handles full-scale export

### Slice 5.2: Performance Tuning (Day 4-6)
- [ ] Optimize batch sizes for Beast GPU topology (GPU 0 compute, GPU 1 display)
- [ ] Optimize SQLite WAL mode for concurrent reads during export
- [ ] Profile memory usage on full corpus
- [ ] Target: incremental nightly run < 90 minutes

### Slice 5.3: Demo Prep (Day 6-7)
- [ ] Verify V2 demo queries work against CorpusForge-produced data
- [ ] Document: "How to run CorpusForge from scratch"
- [ ] Document: "How to check if tonight's run succeeded"
- [ ] Final audit report on production corpus

### Sprint 5 Exit Criteria
- [ ] Full corpus processed successfully
- [ ] Incremental nightly run under 90 minutes
- [ ] V2 demo queries produce correct answers on CorpusForge data
- [ ] Operator documentation complete

---

Jeremy Randall | CorpusForge | 2026-04-04 MDT
