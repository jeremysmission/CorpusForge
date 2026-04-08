# Unified Sprint Plan — CorpusForge + HybridRAG V2

**Last Updated:** 2026-04-07 | **Updated By:** Agent 1 (Forge Coder) — Forge S3 all slices DONE, READY FOR QA
**Demo Target:** 2026-05-02
**Update Rule:** Every agent updates ALL 3 copies at end of sprint session (review board + both repos)

---

## Active Agents

| Agent | Role | Repo | GPU | Status |
|-------|------|------|-----|--------|
| Agent 1 | CorpusForge Coder | C:\CorpusForge | GPU 0 | ACTIVE |
| Agent 2 | HybridRAG V2 Coder | C:\HybridRAG_V2 | GPU 1 / CPU | ACTIVE |
| Agent 3 | QA + Planning + Cross-Repo | Read-only both + V1 docs | None | ACTIVE |

**Copies of this file (keep all 3 in sync):**
- `{USER_HOME}\AgentTeam\war_rooms\HybridRAG3_Educational\SPRINT_SYNC.md` (canonical)
- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`

---

## Hard Gates (Cannot Start Until)

| Gate | Blocked Sprint | Requires | Why |
|------|---------------|----------|-----|
| **GATE-1** | V2 S13 | Forge S2 EXIT GREEN | V2 needs importable chunks.jsonl + vectors.npy |
| **GATE-2** | V2 S14 | Forge S3 EXIT GREEN | Entity promotion needs enriched chunks + entities.jsonl |
| **GATE-3** | Demo (May 2) | Forge S5 + V2 S15 EXIT GREEN | Full corpus processed, 20/25 golden eval |

---

## Week 1: April 7-11 — Unblock Both Pipelines

### Forge Sprint 2: Unblock Chunking + Config Formats + GUI Settings (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 2.1 | Forge | P0 | Diagnose + fix chunking pipeline failure | DONE (lazy init shipped) | Agent 1 |
| 2.2 | Forge | P0 | Move 11 hardcoded placeholder formats to config/skip_list.yaml | DONE (config-driven) | Agent 1 |
| 2.3 | Forge | P1 | GUI settings panel: workers (1-32), enrichment toggle, extraction toggle, OCR mode, chunk size/overlap | DONE (commit babb163) | Agent 1 |
| 2.4 | Forge | P0 | End-to-end chunk export proof (100+ files, verify chunks.jsonl + vectors.npy) | DONE (198 files, 17695 chunks, vectors match) | Agent 1 |
| 2.5 | Forge | P1 | Filter pdfmeta.json junk from chunks (pattern-based skip in skip_list.yaml) | DONE (17 OCR patterns, commit 8b33f8e) | Agent 1 |
| 2.6 | Forge | P1 | config.local.yaml support (machine-specific overrides, gitignored) | DONE (commit 6cf1e7f) | Agent 1 |

**Exit Criteria:** Pipeline runs E2E, all format skips in config, GUI has settings panel, clean chunks exported.

### V2 Sprint 12: Recovery Dedup Hardening (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 12.1 | V2 | P0 | Legacy skip-state audit — backfill deferred/unsupported into file_state | DONE | Agent 2 |
| 12.2 | V2 | P0 | Document-level dedup review — establish as accepted human-review lane | DONE | Agent 2 |
| 12.3 | V2 | P0 | Canonical list readiness — produce clean canonical_files.txt | DONE | Agent 2 |
| 12.4 | V2 | P1 | Deferred/placeholder format risk disclosure — operator matrix | DONE | Agent 2 |
| 12.5 | V2 | P1 | Harden import_embedengine.py — schema version validation, reject bad exports | DONE | Agent 2 |
| 12.6 | V2 | P2 | Clean working tree — triage uncommitted screenshots, binaries, benchmark JSONs | DONE | Agent 2 |

**Exit Criteria:** Backfill safe, dedup review lane defined, canonical_files.txt ready, import hardened.

### QA (Agent 3)

| Task | Repo | Priority | What | Status |
|------|------|----------|------|--------|
| QA-2.1 | Forge | P0 | QA Coder's lazy init + config-driven formats (when "Ready for QA" posted) | STANDBY |
| QA-12 | V2 | P0 | QA Sprint 12 slices (when "Ready for QA" posted) | STANDBY |
| SYNC | Both | P0 | Maintain SPRINT_SYNC.md across all 3 locations | ACTIVE |

---

## Week 2: April 12-18 — Enrichment + Canonical Rebuild

### Forge Sprint 3: Enrichment Auto-Activation + GLiNER Extraction (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 3.0 | Forge | P0 | Enrichment auto-activation: Ollama health probe at GUI startup, auto-start Ollama, model check, blocking dialog if unavailable, GPU selection (pick lesser-used) | DONE (stdlib urllib, GUI probe + blocking dialog) | Agent 1 |
| 3.1 | Forge | P0 | Contextual enrichment validation: verify phi4:14B on Beast, validate enriched_text in export, A/B retrieval quality test | DONE (5/5 enriched, concurrent workers) | Agent 1 |
| 3.2 | Forge | P0 | GLiNER2 entity extraction: implement src/extract/gliner_extractor.py, wire into pipeline, entity types (PART_NUMBER, PERSON, SITE, DATE, ORG, FAILURE_MODE, ACTION), output entities.jsonl, confidence filtering | DONE (150 entities from 12 chunks, batch inference 30/sec) | Agent 1 |
| 3.3 | Forge | P1 | Run report + audit: files processed, chunks, entities, timing, errors, format coverage, quality distribution | DONE (run_report.txt in export) | Agent 1 |
| 3.4 | Forge | P2 | Enrichment rollback: --strip-enrichment export flag (output text field only, strip preambles) | DONE (CLI flag wired) | Agent 1 |

**Exit Criteria:** Enriched chunks measurably improve retrieval, entities extracted, run report operational.

### V2 Sprint 13: Canonical Rebuild on Forge Output (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 13.1 | V2 | P0 | Import rebuilt CorpusForge export into fresh LanceDB store | DONE | Agent 2 |
| 13.2 | V2 | P0 | Rebuild entity + relationship SQLite stores from fresh import | DEFERRED (S14) | Agent 2 |
| 13.3 | V2 | P0 | Run golden eval on rebuilt data -- baseline accuracy | DONE (20/25) | Agent 2 |
| 13.4 | V2 | P1 | Integration test: Forge export -> V2 import -> query -> verify results | DONE (7/7) | Agent 2 |
| 13.5 | V2 | P1 | Dedup format preference: define canonical format order (.docx > .pdf > .txt), auto-resolve low_risk families | DEFERRED (S14) | Agent 2 |

**Exit Criteria:** Fresh store populated from Forge output, golden eval baselined, integration test passing.

### QA (Agent 3)

| Task | Repo | Priority | What | Status |
|------|------|----------|------|--------|
| QA-3 | Forge | P0 | QA enrichment + extraction (enriched chunks non-null, entities valid) | TODO |
| QA-13 | V2 | P0 | QA canonical rebuild (import clean, queries return results) | TODO |
| IC-1 | Both | P0 | Integration checkpoint: verify Forge export format matches V2 import expectations | TODO |
| IC-2 | Both | P0 | Integration checkpoint: verify entities.jsonl matches V2 entity store schema | TODO |

---

## Week 3: April 19-25 — Polish + Scale

### Forge Sprint 4: GUI Polish + Scheduling + Test Coverage

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 4.1 | Forge | P1 | GUI improvements: run history (last 10), format coverage display, error drill-down | TODO | Agent 1 |
| 4.2 | Forge | P1 | Headless mode: --headless flag, exit codes (0/1/2), log rotation, Windows Task Scheduler .xml template | TODO | Agent 1 |
| 4.3 | Forge | P1 | Audit tool: corpus audit report, duplicate detection report, quality score distribution | TODO | Agent 1 |
| 4.4 | Forge | P1 | Test coverage: parser smoke tests (1 per parser), embedder CUDA/ONNX, enricher Ollama, chunker, pipeline E2E — target 50+ tests | TODO | Agent 1 |

**Exit Criteria:** GUI production-quality, headless mode tested, nightly schedule configured, 50+ tests.

### V2 Sprint 14: Structured Promotion (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 14.1 | V2 | P0 | Entity extraction at scale on full rebuilt corpus | DONE | Agent 2 |
| 14.2 | V2 | P0 | Entity normalization + controlled vocabulary matching (25 IGS sites) | DONE (label mapping) | Agent 2 |
| 14.3 | V2 | P0 | Relationship graph population from extracted entities | DONE (existing) | Agent 2 |
| 14.4 | V2 | P1 | Table extraction integration (if Docling waiver approved) | DEFERRED | Agent 2 |
| 14.5 | V2 | P1 | Query router tuning: verify AGGREGATION, ENTITY_LOOKUP, RELATIONSHIP paths work on real data | DONE (25/25) | Agent 2 |

**Exit Criteria:** Entities promoted at scale, relationship graph populated, query router working on all paths.

### QA (Agent 3)

| Task | Repo | Priority | What | Status |
|------|------|----------|------|--------|
| QA-4 | Forge | P1 | QA headless mode, test coverage review, GUI button smash (12-scenario deck) | TODO |
| QA-14 | V2 | P0 | QA entity promotion (counts, quality, query results) | TODO |
| IC-3 | Both | P0 | Scale test: full corpus Forge export imports into V2, queries return results | TODO |

---

## Week 4: April 26 - May 1 — Production + Demo Prep

### Forge Sprint 5: Full Corpus Run + Performance Tuning

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 5.1 | Forge | P0 | Run pipeline against full 420K file corpus | TODO | Agent 1 |
| 5.2 | Forge | P0 | Performance tuning: batch sizes for Beast dual-3090, SQLite WAL, memory profiling — target incremental nightly < 90min | TODO | Agent 1 |
| 5.3 | Forge | P0 | Demo prep: verify V2 demo queries work against Forge data, operator documentation | TODO | Agent 1 |

**Exit Criteria:** Full corpus processed, incremental nightly < 90min, operator docs complete.

### V2 Sprint 15: Operator Hardening + Final Golden Eval

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 15.1 | V2 | P0 | Performance tuning on full corpus (P50 <3s, P95 <10s) | TODO | Agent 2 |
| 15.2 | V2 | P0 | Final golden eval on production data — target 20/25 | TODO | Agent 2 |
| 15.3 | V2 | P0 | V1 vs V2 comparison harness on real data | TODO | Agent 2 |
| 15.4 | V2 | P1 | Deployment guide finalization, operator training materials | TODO | Agent 2 |
| 15.5 | V2 | P1 | Demo rehearsal: 10 queries under time target, recovery plays | TODO | Agent 2 |

**Exit Criteria:** 20/25 golden eval, P50 <3s, demo rehearsed, deployment guide complete.

### QA (Agent 3)

| Task | Repo | Priority | What | Status |
|------|------|----------|------|--------|
| QA-5 | Forge | P0 | QA full corpus run (manifest stats, error rate, timing) | TODO |
| QA-15 | V2 | P0 | QA golden eval results, V1 vs V2 comparison review | TODO |
| IC-4 | Both | P0 | Demo dry run: 10 demo queries through full Forge→V2 pipeline | TODO |
| SMASH | Both | P0 | Button smash both GUIs (full 12-scenario deck each) | TODO |

---

## May 2 — DEMO DAY

| Item | Repo | Owner | Acceptance |
|------|------|-------|-----------|
| 10 demo queries covering all failure classes | V2 | Agent 2 | All return results with sources |
| V1 vs V2 comparison (side-by-side) | V2 | Agent 2 | V2 visibly better on aggregation/entity queries |
| Full corpus processed and current | Forge | Agent 1 | Nightly ran successfully night before |
| Zero crashes during demo | Both | Agent 3 (QA) | Button smash passed, recovery plays tested |
| Skip file acknowledgment (what we can't parse and why) | Forge | Agent 1 | Format coverage matrix visible |

---

## Parallel Work Matrix

| Week | Agent 1 (Forge) | Agent 2 (V2) | Agent 3 (QA) | Conflicts |
|------|-----------------|--------------|-------------|-----------|
| 1 (Apr 7-11) | S2: GUI + pdfmeta + config.local | S12: Dedup hardening + import validation | QA S2 + S12 | NONE |
| 2 (Apr 12-18) | S3: Enrichment + GLiNER | S13: Canonical rebuild | QA S3 + S13, IC-1, IC-2 | GATE-1 |
| 3 (Apr 19-25) | S4: Polish + headless + tests | S14: Entity promotion at scale | QA S4 + S14, IC-3, button smash | GATE-2 |
| 4 (Apr 26-May 1) | S5: Full corpus + perf tune | S15: Golden eval + demo prep | QA S5 + S15, IC-4, demo dry run | Both must complete |

---

## Update Protocol

1. **Every agent updates ALL 3 copies** of this file at end of each sprint session
2. When a sprint completes → update Status column + add completion date
3. When a GATE is reached → Agent 3 verifies gate condition before unblocking
4. If a sprint slips → update ETA + flag downstream impact in this doc
5. Jeremy (Operator) has absolute authority to override any gate, priority, or assignment

---

Signed: Agent 3 (QA/Planning) | HybridRAG3_Educational | 2026-04-07 | MDT
