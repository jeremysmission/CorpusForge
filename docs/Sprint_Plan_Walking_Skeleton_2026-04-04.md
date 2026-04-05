# Unified Sprint Plan — Walking Skeleton Method

**Author:** Jeremy Randall (CoPilot+)
**Date:** 2026-04-04 MDT
**Repos:** CorpusForge (ingest) + HybridRAG V2 (query)
**Demo Target:** 2026-05-02 (4 weeks)
**Method:** Walking Skeleton — thinnest end-to-end path first, then incremental features
**Work Mode:** Nights and weekends. Agile — every sprint ships something demo-able.

---

## Guiding Principles

1. **Skeleton first.** Build the thinnest slice through BOTH apps before adding any features.
2. **Config first.** Everything reads config. Config is the foundation.
3. **One feature at a time.** Focused tasks produce better code than monolithic asks.
4. **Tests alongside.** Golden eval queries from Sprint 1 onward. They're your safety net.
5. **CorpusForge before V2** for each feature — V2 depends on CorpusForge output.
6. **Reuse V1 aggressively.** 60-70% of CorpusForge is V1 code. Don't rewrite what works.
7. **500 lines per class max.** Keeps code reviewable, portable, modular.
8. **Never build all 8 CorpusForge stages before testing if V2 can import the output.** Prove the handoff works at every stage.

---

## Sprint 0: Config + Skeleton Wiring (Days 1-3 — April 5-7)

**Goal:** Both apps boot, config validates, and 1 file flows end-to-end from CorpusForge export to V2 query answer.

### Slice 0.1: Config Schemas (Day 1 — Both Repos)

**CorpusForge:**
- [ ] `src/config/schema.py` — Pydantic schema: source paths, output path, chunk size/overlap, embed model, GPU settings
- [ ] `config/config.yaml` — single config, beast preset defaults
- [ ] Boot script: load config → validate → print "CorpusForge ready"

**HybridRAG V2:**
- [ ] `src/config/schema.py` — Pydantic schema: LanceDB path, SQLite path, LLM settings, retrieval settings, hardware preset
- [ ] `config/config.yaml` — single config, no modes, beast preset defaults
- [ ] Boot script: load config → validate → print "V2 ready"

**Exit:** Both apps boot and validate config without errors.

### Slice 0.2: CorpusForge Minimal Pipeline (Day 1-2)

- [ ] `src/parse/parsers/txt_parser.py` — parse 1 text file (simplest parser)
- [ ] `src/chunk/chunker.py` — port from V1 (1200/200, sentence boundary)
- [ ] `src/chunk/chunk_ids.py` — port from V1 (SHA-256 deterministic IDs)
- [ ] `src/embed/embedder.py` — port from V1 (CUDA primary, skip ONNX for now)
- [ ] `src/embed/batch_manager.py` — port from V1 (token-budget batching)
- [ ] `src/export/packager.py` — write chunks.jsonl + vectors.npy + manifest.json
- [ ] `src/pipeline.py` — orchestrate: parse → chunk → embed → export
- [ ] `scripts/run_pipeline.py` — CLI: `python scripts/run_pipeline.py --input test_file.txt`

**Test:** Run on 1 text file. Verify chunks.jsonl has chunks, vectors.npy has 768-dim float16 vectors, manifest.json has correct metadata.

**Exit:** CorpusForge produces a valid export package from a single file.

### Slice 0.3: V2 Import + LanceDB + Basic Query (Day 2-3)

- [ ] `src/store/lance_store.py` — create LanceDB table, insert chunks + vectors, hybrid search
- [ ] `scripts/import_embedengine.py` — read CorpusForge export → load into LanceDB
- [ ] `src/llm/client.py` — unified openai SDK client (GPT-4o, GPT-OSS-120B)
- [ ] `src/query/vector_retriever.py` — LanceDB hybrid search (vector + BM25)
- [ ] `src/query/context_builder.py` — assemble top-K chunks into context string
- [ ] `src/query/generator.py` — GPT-4o generation with graduated confidence prompt
- [ ] `src/api/routes.py` — POST /query endpoint (minimal FastAPI)
- [ ] `src/api/server.py` — FastAPI app bootstrap

**Test:** Import CorpusForge export. Ask a question about the test file. Get a sourced answer.

**Exit:** Question in → answer out, end-to-end through both apps. The skeleton walks.

### Slice 0.4: First Golden Eval (Day 3)

- [ ] Write 5 golden queries in `tests/golden_eval/golden_queries.json`
- [ ] `tests/golden_eval/eval_runner.py` — run queries, check fact_score
- [ ] Verify all 5 produce reasonable answers
- [ ] This becomes the regression test for everything that follows

**Sprint 0 Deliverable:** A working system — crude, minimal, but data flows from raw file through both apps to a sourced answer. Every subsequent sprint adds capability to this working skeleton.

---

## Sprint 1: Core Pipeline (Days 4-8 — April 8-12)

**Goal:** CorpusForge handles real corpus data. V2 handles real queries with reranking.

### Slice 1.1: CorpusForge — Full Parser Stack (Day 4-5)

- [ ] Port remaining 31 parsers from V1 into `src/parse/parsers/`
  - PDF (pdfplumber + OCR fallback)
  - DOCX, XLSX, PPTX, CSV, MSG, HTML, RTF, JSON, XML, etc.
- [ ] `src/parse/dispatcher.py` — route files by extension
- [ ] `src/parse/quality_scorer.py` — port from V1, score 0.0-1.0
- [ ] `src/parse/ocr.py` — pytesseract + Poppler pipeline
- [ ] Error isolation: try/except per file, never crash

**Test:** Run CorpusForge on 100 mixed-format files. Verify parse success rate > 90%.

### Slice 1.2: CorpusForge — Hash + Dedup (Day 5-6)

- [ ] `src/download/hasher.py` — SHA-256 content hashing
- [ ] `src/download/deduplicator.py` — _1 suffix + content-hash dedup
- [ ] SQLite file_state table (path, hash, mtime, status)
- [ ] Incremental mode: re-run pipeline, verify unchanged files are skipped

**Test:** Run pipeline twice on same files. Second run processes 0 files.

### Slice 1.3: V2 — FlashRank Reranking (Day 6-7)

- [ ] `src/query/reranker.py` — FlashRank integration (or LanceDB built-in if waiver pending)
- [ ] Wire into query pipeline: retrieve top-30 → rerank → top-10
- [ ] A/B test: run golden eval with and without reranking, measure improvement

**Test:** Reranking improves fact_score on at least 3 of 5 golden queries.

### Slice 1.4: V2 — Graduated Confidence + Streaming (Day 7-8)

- [ ] Update generator prompt with graduated confidence (HIGH/PARTIAL/NOT_FOUND)
- [ ] `src/api/routes.py` — add POST /query/stream (SSE)
- [ ] Verify streaming works end-to-end

### Slice 1.5: Scale Test (Day 8)

- [ ] Run CorpusForge on 1,000 real files from production corpus
- [ ] Import into V2, run golden eval
- [ ] Measure: LanceDB search latency, total query latency, memory usage
- [ ] Expand golden eval to 10 queries

**Sprint 1 Deliverable:** CorpusForge parses 32+ formats, deduplicates, and exports. V2 imports, searches with FlashRank reranking, generates answers with confidence levels and streaming. 10 golden queries passing. Already better than V1.

---

## Sprint 2: Structured Extraction (Days 9-15 — April 13-19)

**Goal:** Entity extraction and quality gates. Aggregation and lookup queries work.

### Slice 2.1: CorpusForge — Contextual Enrichment (Day 9-10)

- [ ] `src/enrich/ollama_client.py` — local Ollama API client for phi4:14B
- [ ] `src/enrich/enricher.py` — generate context prefix per chunk
- [ ] Wire into pipeline between chunk and embed stages
- [ ] Updated export: enriched_text field in chunks.jsonl

**Test:** Import enriched chunks into V2. Run golden eval. Measure retrieval improvement. Target: 20%+ better fact_score on semantic queries.

### Slice 2.2: CorpusForge — GLiNER2 Entity Extraction (Day 10-11)

- [ ] `src/extract/ner_extractor.py` — GLiNER2 zero-shot NER on CPU
- [ ] Entity types: PART_NUMBER, PERSON, SITE, DATE, ORG, FAILURE_MODE
- [ ] Updated export: entities.jsonl with confidence scores
- [ ] **Fallback if GLiNER waiver pending:** skip this slice, move to Slice 2.3 with GPT-4o only

**Test:** Extract entities from 100 chunks. Spot-check 20 for accuracy.

### Slice 2.3: V2 — Quality Gates + Normalization (Day 11-13)

- [ ] `src/ingest/entity_extractor.py` — GPT-4o second-pass on complex chunks
- [ ] `src/ingest/quality_gate.py` — confidence threshold (>= 0.7), type-specific validation
- [ ] `src/ingest/entity_normalizer.py` — controlled vocabulary for sites, part patterns, name cleanup
- [ ] Site vocabulary YAML (25 IGS sites with aliases)
- [ ] Part number patterns (ARC-NNNN, IGSI-NNNN, PO-YYYY-NNNN)
- [ ] `scripts/audit_extraction.py` — quality report (accepted/rejected/reasons)

**Test:** Import entities from CorpusForge. Run quality gate. Verify: "Pre-Site Survey To Thule AB" normalizes to "Thule". "Annette Parsons, (970) 986-2551" splits correctly. Garbage entities rejected.

### Slice 2.4: V2 — Entity + Relationship Stores (Day 13-14)

- [ ] `src/store/entity_store.py` — SQLite entities table with indexes
- [ ] `src/store/relationship_store.py` — SQLite relationship triples
- [ ] `src/store/table_store.py` — SQLite extracted table rows (Docling, if waiver ready)

### Slice 2.5: V2 — Query Router + Structured Retrieval (Day 14-15)

- [ ] `src/query/router.py` — GPT-4o query classification (SEMANTIC/ENTITY/AGGREGATE/TABULAR/COMPLEX)
- [ ] `src/query/entity_retriever.py` — SQLite lookup for entity + aggregation queries
- [ ] `src/query/table_retriever.py` — Text2SQL via GPT-4o for tabular queries
- [ ] `src/query/decomposer.py` — sub-query generation for COMPLEX queries
- [ ] Wire router into main query pipeline

**Test:** Golden eval expanded to 15 queries including:
- "Who is the POC for Thule?" → returns a real name from entity store
- "How many maintenance service reports in 2025?" → returns SQL count
- "Explain the calibration procedure" → still works via semantic path

**Sprint 2 Deliverable:** CorpusForge produces enriched chunks + candidate entities. V2 validates, normalizes, and stores entities. Query router classifies questions. Aggregation and lookup queries work for the first time. 15 golden queries passing.

---

## Sprint 3: GUI + Quality Polish (Days 16-22 — April 20-26)

**Goal:** Demo-ready GUI with streaming, confidence badges, and all query types. CRAG verification.

### Slice 3.1: V2 — GUI Port (Day 16-18)

- [ ] `src/gui/app.py` — main Tkinter window (carry V1 aesthetic)
- [ ] `src/gui/query_panel.py` — query input, streaming response display
- [ ] `src/gui/source_panel.py` — expandable source citations
- [ ] `src/gui/theme.py` — dark/light color scheme from V1
- [ ] Confidence badge (HIGH green / PARTIAL yellow / NOT_FOUND red)
- [ ] Query path indicator (SEMANTIC / SQL / LOOKUP / MULTI-HOP)
- [ ] Structured results panel (tables rendered as tables)
- [ ] Remove: mode toggle, role selector, grounding bias slider

### Slice 3.2: V2 — CRAG Verification Loop (Day 18-19)

- [ ] GPT-OSS-20B grades response against retrieved sources
- [ ] If confidence < 0.8: rewrite query, re-retrieve, re-generate
- [ ] Max 2 retries, then return with [LOW CONFIDENCE] flag
- [ ] Optional — disable if latency budget is tight

### Slice 3.3: V2 — Advanced Query Features (Day 19-20)

- [ ] Multi-hop queries via relationship JOIN
- [ ] Query expansion (synonym matching, acronym resolution)
- [ ] Parent chunk expansion (retrieve child, return parent for context)

### Slice 3.4: CorpusForge — GUI + Scheduling (Day 20-22)

- [ ] `src/gui/app.py` — monitoring window (pipeline progress, run history)
- [ ] `scripts/schedule_nightly.py` — Windows Task Scheduler setup
- [ ] Headless mode (no GUI, log to file) for nightly runs
- [ ] `scripts/audit_index.py` — corpus audit report

### Slice 3.5: Golden Eval Expansion (Day 22)

- [ ] Expand to 20+ golden queries covering all 5 failure classes
- [ ] Include: aggregation, entity lookup, tabular, synonym mismatch, cross-document
- [ ] Run full eval, document results
- [ ] V1 vs V2 comparison on identical queries

**Sprint 3 Deliverable:** GUI demo-ready with streaming, confidence badges, and all query types. CorpusForge runs on schedule with monitoring. 20 golden queries passing. V1 vs V2 comparison documented.

---

## Sprint 4: Demo Hardening (Days 23-28 — April 27 - May 2)

**Goal:** Production-quality on real work data. Demo rehearsed.

### Slice 4.1: Full Corpus Processing (Day 23-25)

- [ ] Run CorpusForge against full 420K file corpus (background, may take 2-3 days)
- [ ] Monitor: GPU utilization, memory, disk I/O, timing per stage
- [ ] Fix any scale issues (file handle limits, SQLite WAL locking, batch OOM)
- [ ] V2 imports full-scale export, verify all stores populated

### Slice 4.2: Performance Tuning (Day 25-26)

- [ ] Benchmark all query types on production data
- [ ] Tune: LanceDB index settings, FlashRank top-N, retrieval depth, RRF weights
- [ ] Target: P50 < 3s, P95 < 10s
- [ ] Memory profiling on Beast and laptop
- [ ] CorpusForge incremental nightly target: < 90 minutes

### Slice 4.3: Demo Prep (Day 26-28)

- [ ] Prepare 10 demo queries covering all failure classes
- [ ] Document expected answers for each
- [ ] Rehearse demo flow: simple → entity → aggregation → tabular → complex
- [ ] Build "V1 vs V2" comparison (same query, different results)
- [ ] Final golden eval: 20/20 on production data
- [ ] Bug fixes, edge cases, polish

### Slice 4.4: Documentation (Day 28)

- [ ] Update all docs with final architecture
- [ ] Deployment guide (clean install from scratch)
- [ ] Operator guide (how to query, read confidence, check CorpusForge status)
- [ ] Demo script with talking points

**Sprint 4 Deliverable:** Demo-ready. Production data queried successfully. V1 vs V2 comparison dramatic. Operator docs complete. Ready to show.

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| LanceDB waiver delayed | FAISS + FTS5 fallback in Slice 0.3 |
| GLiNER waiver delayed | GPT-4o handles all extraction (costlier but works) |
| Docling waiver delayed | openpyxl + pdfplumber (lower accuracy but functional) |
| FlashRank waiver delayed | LanceDB built-in reranking (zero deps) |
| Full corpus enrichment takes too long | Kick off Day 9, runs in background. Demo on partial enrichment if needed. |
| Skeleton doesn't walk by Day 3 | Stop and debug. Nothing else matters until end-to-end works. |
| Quality gates reject too many entities | Lower threshold temporarily, tune with audit report data |
| GPT-4o extraction cost exceeds budget | Start with high-value docs only (service reports, logistics), expand later |

---

## Milestone Summary

| Day | Milestone | State of System |
|---|---|---|
| Day 3 | Skeleton walks | 1 file → CorpusForge → V2 → answer. Crude but end-to-end. |
| Day 8 | Sprint 1 done | 32+ parsers, dedup, reranking, streaming. 10 golden queries. Better than V1. |
| Day 15 | Sprint 2 done | Entity extraction + quality gates. Aggregation works. 15 golden queries. |
| Day 22 | Sprint 3 done | GUI, CRAG, all query types. 20 golden queries. Demo-able. |
| Day 28 | Sprint 4 done | Production data, tuned, rehearsed. Demo-ready. |

---

Jeremy Randall | HybridRAG_V2 + CorpusForge | 2026-04-04 MDT
