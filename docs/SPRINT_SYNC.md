# Unified Sprint Plan — CorpusForge + HybridRAG V2

> WARNING: Planning board only. This file is unsafe as current readiness, demo, operator, or recovery truth.
> Use `C:\HybridRAG_V2\docs\SOURCE_OF_TRUTH_MAP_2026-04-12.md`, `C:\HybridRAG_V2\docs\REBOOT_HANDOVER_2026-04-13.md`, and `C:\HybridRAG_V2\docs\SPRINT_SLICE_PRODUCT_COMPLETION_2026-04-13.md` instead.

**Last Updated:** 2026-04-13 | **Updated By:** Codex — added the product-completion master slice and linked it without replacing the active eval-GUI slice.
**Demo Target:** 2026-05-02
**Update Rule:** Every agent updates ALL 3 copies at end of sprint session (review board + both repos)

---

## Active Agents

| Agent | Role | Repo | GPU | Status |
|-------|------|------|-----|--------|
| reviewer | Forge Sprint 6 critical path | C:\CorpusForge | GPU 0 default | ACTIVE |
| reviewer | Forge Sprint 7 sample analysis | C:\CorpusForge_Dev | CPU / GPU 1 as needed | HANDOFF POSTED (accepted export delivered to reviewer) |
| reviewer | V2 Sprint 16 accepted-export import/eval | C:\HybridRAG_V2_Dev | GPU 1 chosen (GPU 0 heavily occupied at run start) | READY FOR QA (clone-local phase 2 complete; no reviewer write commands targeted mainline V2; promotion hold recommended) |
| QA | Validation standby | Read-only until a lane posts Ready for QA | Lesser-used GPU when needed | STANDBY |
| reviewer | Lane 2: GUI control + live telemetry (cooperative stop, chunks/s, stage clarity) | C:\CorpusForge | headless | **READY FOR QA (re-post 2026-04-09)** — QA's two findings addressed: (1) GUI Stop signal is now wired through PipelineRunner → Pipeline.run() via `should_stop=self._stop_event.is_set`; cooperative `_check_stop` exits cleanly at every major boundary (pre-dedup, dedup loop via Deduplicator's `should_stop`, post-dedup, skip/defer pass, parallel parse loop with future cancellation, sequential parse fallback, pre-embed, embed sub-batch loop with vector slice on truncation, pre-extract). Mid-embed stop trims `all_chunks` to match returned vectors so the export stays aligned. Hash-persistence/resume is preserved — `Deduplicator` continues to mark hashed work as `hashed` even when stop fires inside its scan. (2) GUI button-smash now includes Stop control coverage: `TestStopControl::test_stop_button_exists_and_starts_disabled`, `test_stop_button_invokes_on_stop_callback_when_running`, and a real end-to-end `test_pipeline_runner_stop_drill_interrupts_real_run` that boots a 40-file PipelineRunner, waits for live `chunks_created>0`, fires `runner.stop()`, asserts `pipeline_finished` payload has `stop_requested=True`, asserts the runner thread exits, and asserts the export was packaged on disk. Live telemetry: `chunks_per_second` row in StatsPanel, stage map renders `Discover/Dedup/Parse/Chunk/Enrich/Embed/Extract/Export/Stopping` with CPU/IO/GPU/Ollama hints so operators no longer expect GPU during parse. Tests: `tests/test_gui_button_smash.py` 15/15, `tests/test_gui_dedup_only.py` 10/10, `tests/test_pipeline_e2e.py` 15/15, `tests/test_archive_member_defer.py` 7/7, `tests/test_parsers.py` 13/13 — **60/60 PASS**. Files changed: `src/pipeline.py`, `src/gui/launch_gui.py`, `src/gui/app.py`, `src/gui/stats_panel.py`, `tests/test_pipeline_e2e.py`, `tests/test_gui_button_smash.py`, `tests/test_gui_dedup_only.py`. Stop semantics: cooperative — finishes in-flight parse work, cancels queued futures, slices embed at next sub-batch boundary, packages completed chunks/vectors aligned, then writes manifest + skip_manifest. Honest UI: button is `Stop Safely`, transitions to `Stopping...` on click and stage label flips to `Stopping`. Pipeline exit message: `Pipeline stopped cleanly: ... Completed work was packaged; remaining files stay resumable.` |

**Copies of this file (keep all 3 in sync):**
- `{USER_HOME}\AgentTeam\war_rooms\HybridRAG3_Educational\SPRINT_SYNC.md` (canonical)
- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`

## 2026-04-13 Product Completion Addendum

- Master product-completion slice:
  - `C:\HybridRAG_V2\docs\SPRINT_SLICE_PRODUCT_COMPLETION_2026-04-13.md`
- Active concurrent slice that remains in force:
  - `C:\HybridRAG_V2\docs\SPRINT_SLICE_EVAL_GUI_2026-04-13.md`
- Immediate order:
  - `PC.1` measurement truth and stable reruns
  - `PC.2` retrieval and router burn-down
  - `PC.3` demo-safe packet freeze
  - `PC.4` and `PC.5` structured and tabular substrate
  - `PC.7` and `PC.8` cross-repo freeze, operator packet, and demo-machine proof
- Guardrail:
  - aggregation stays off-stage until the product-completion slice closes the tabular and aggregation gates
- Benchmark rule:
  - do not rewrite the 400-pack for score gain; query-pack work now means demo curation, robustness variants, and gold-reference tightening

---

## QA Standby Protocol

- Do not start active validation until a lane posts `Ready for QA`.
- Use absolute repo roots only: `C:\CorpusForge` and `C:\HybridRAG_V2`. If assigned a clone lane, use the exact clone root Jeremy assigned.
- Use repo-local venvs only.
- Use real hardware, real CUDA, and real production data or the real 1000-file subset whenever available.
- Constrain each validation run to one GPU with `CUDA_VISIBLE_DEVICES`. If both GPUs are active, take the lesser-used GPU and document the choice.
- Review the lane's deep packet or evidence packet before testing.
- Before judging OCR or scanned-PDF behavior in CorpusForge, check workstation prerequisites with `where.exe tesseract` and `where.exe pdftoppm`.
- If either OCR tool is missing, record OCR or scanned-document gaps as environment prerequisites unless the lane overclaimed OCR-ready or production-ready status.
- Missing OCR tools is not a code failure for text-first validation; text parsing, dedup, regex extraction, V2 import, and golden eval still count as normal code or test findings.
- Evidence packets must state whether OCR tools were present and whether the lane was text-only or OCR-capable.
- If GUI was touched, require full GUI harness Tiers A-D plus human button smash by a non-author.
- Findings-first reporting only. If there are no findings, say exactly: `No findings.`
- Before signoff, verify: both sprint boards updated; dated evidence or handoff note present; repo, branch, GPU, and data path documented; commands and outputs documented; real-data pass documented; GUI harness and button smash documented if GUI changed; blockers and residual risks documented.

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
| 2.1 | Forge | P0 | Diagnose + fix chunking pipeline failure | DONE (lazy init shipped) | reviewer |
| 2.2 | Forge | P0 | Move 11 hardcoded placeholder formats to config/skip_list.yaml | DONE (config-driven) | reviewer |
| 2.3 | Forge | P1 | GUI settings panel: workers (1-32), enrichment toggle, extraction toggle, OCR mode, chunk size/overlap | DONE (commit babb163) | reviewer |
| 2.4 | Forge | P0 | End-to-end chunk export proof (100+ files, verify chunks.jsonl + vectors.npy) | DONE (198 files, 17695 chunks, vectors match) | reviewer |
| 2.5 | Forge | P1 | Filter pdfmeta.json junk from chunks (pattern-based skip in skip_list.yaml) | DONE (17 OCR patterns, commit 8b33f8e) | reviewer |
| 2.6 | Forge | P1 | config.local.yaml support (machine-specific overrides, gitignored) | DONE (commit 6cf1e7f) | reviewer |

**Exit Criteria:** Pipeline runs E2E, all format skips in config, GUI has settings panel, clean chunks exported.

### V2 Sprint 12: Recovery Dedup Hardening (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 12.1 | V2 | P0 | Legacy skip-state audit — backfill deferred/unsupported into file_state | DONE | reviewer |
| 12.2 | V2 | P0 | Document-level dedup review — establish as accepted human-review lane | DONE | reviewer |
| 12.3 | V2 | P0 | Canonical list readiness — produce clean canonical_files.txt | DONE | reviewer |
| 12.4 | V2 | P1 | Deferred/placeholder format risk disclosure — operator matrix | DONE | reviewer |
| 12.5 | V2 | P1 | Harden import_embedengine.py — schema version validation, reject bad exports | DONE | reviewer |
| 12.6 | V2 | P2 | Clean working tree — triage uncommitted screenshots, binaries, benchmark JSONs | DONE | reviewer |

**Exit Criteria:** Backfill safe, dedup review lane defined, canonical_files.txt ready, import hardened.

### QA (reviewer)

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
| 3.0 | Forge | P0 | Enrichment auto-activation: Ollama health probe at GUI startup, auto-start Ollama, model check, blocking dialog if unavailable, GPU selection (pick lesser-used) | DONE (stdlib urllib, GUI probe + blocking dialog) | reviewer |
| 3.1 | Forge | P0 | Contextual enrichment validation: verify phi4:14B on primary workstation, validate enriched_text in export, A/B retrieval quality test | DONE (5/5 enriched, concurrent workers) | reviewer |
| 3.2 | Forge | P0 | GLiNER2 entity extraction: implement src/extract/gliner_extractor.py, wire into pipeline, entity types (PART_NUMBER, PERSON, SITE, DATE, ORG, FAILURE_MODE, ACTION), output entities.jsonl, confidence filtering | DONE (150 entities from 12 chunks, batch inference 30/sec) | reviewer |
| 3.3 | Forge | P1 | Run report + audit: files processed, chunks, entities, timing, errors, format coverage, quality distribution | DONE (run_report.txt in export) | reviewer |
| 3.4 | Forge | P2 | Enrichment rollback: --strip-enrichment export flag (output text field only, strip preambles) | DONE (CLI flag wired) | reviewer |

**Exit Criteria:** Enriched chunks measurably improve retrieval, entities extracted, run report operational.

### V2 Sprint 13: Canonical Rebuild on Forge Output (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 13.1 | V2 | P0 | Import rebuilt CorpusForge export into fresh LanceDB store | DONE | reviewer |
| 13.2 | V2 | P0 | Rebuild entity + relationship SQLite stores from fresh import | DEFERRED (S14) | reviewer |
| 13.3 | V2 | P0 | Run golden eval on rebuilt data -- baseline accuracy | DONE (20/25) | reviewer |
| 13.4 | V2 | P1 | Integration test: Forge export -> V2 import -> query -> verify results | DONE (7/7) | reviewer |
| 13.5 | V2 | P1 | Dedup format preference: define canonical format order (.docx > .pdf > .txt), auto-resolve low_risk families | DEFERRED (S14) | reviewer |

**Exit Criteria:** Fresh store populated from Forge output, golden eval baselined, integration test passing.

### QA (reviewer)

| Task | Repo | Priority | What | Status |
|------|------|----------|------|--------|
| QA-3 | Forge | P0 | QA enrichment + extraction (enriched chunks non-null, entities valid) | TODO |
| QA-13 | V2 | P0 | QA canonical rebuild (import clean, queries return results) | TODO |
| IC-1 | Both | P0 | Integration checkpoint: verify Forge export format matches V2 import expectations | TODO |
| IC-2 | Both | P0 | Integration checkpoint: verify entities.jsonl matches V2 entity store schema | TODO |

---

## Week 3: April 19-25 — Polish + Scale

### Forge Sprint 4: GUI Polish + Scheduling + Test Coverage (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 4.1 | Forge | P1 | GUI improvements: run history (last 10), format coverage display, error drill-down | DONE (run_history.jsonl, audit tool) | reviewer |
| 4.2 | Forge | P1 | Headless mode: --headless flag, exit codes (0/1/2), log rotation, Windows Task Scheduler .xml template | DONE (nightly_task.xml, headless already working) | reviewer |
| 4.3 | Forge | P1 | Audit tool: corpus audit report, duplicate detection report, quality score distribution | DONE (scripts/audit_corpus.py) | reviewer |
| 4.4 | Forge | P1 | Test coverage: parser smoke tests (1 per parser), embedder CUDA/ONNX, enricher Ollama, chunker, pipeline E2E — target 50+ tests | DONE (89 tests, was 77 — added GUI button smash engine) | reviewer |

**Exit Criteria:** GUI production-quality, headless mode tested, nightly schedule configured, 50+ tests.

### V2 Sprint 14: Structured Promotion (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 14.1 | V2 | P0 | Entity extraction at scale on full rebuilt corpus | DONE | reviewer |
| 14.2 | V2 | P0 | Entity normalization + controlled vocabulary matching (25 enterprise program sites) | DONE (label mapping) | reviewer |
| 14.3 | V2 | P0 | Relationship graph population from extracted entities | DONE (existing) | reviewer |
| 14.4 | V2 | P1 | Table extraction integration (if Docling waiver approved) | DEFERRED | reviewer |
| 14.5 | V2 | P1 | Query router tuning: verify AGGREGATION, ENTITY_LOOKUP, RELATIONSHIP paths work on real data | DONE (25/25) | reviewer |

**Exit Criteria:** Entities promoted at scale, relationship graph populated, query router working on all paths.

### QA (reviewer)

| Task | Repo | Priority | What | Status |
|------|------|----------|------|--------|
| QA-4 | Forge | P1 | QA headless mode, test coverage review, GUI button smash (12-scenario deck) | TODO |
| QA-14 | V2 | P0 | QA entity promotion (counts, quality, query results) | TODO |
| IC-3 | Both | P0 | Scale test: full corpus Forge export imports into V2, queries return results | TODO |

---

## Week 4: April 26 - May 1 — Production + Demo Prep

### Forge Sprint 5: Full Corpus Run + Performance Tuning (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 5.1 | Forge | P0 | Run pipeline against full 420K file corpus | DONE (field_engineer 6316 files → 312K chunks, golden 14/14, full 109K in progress) | reviewer |
| 5.2 | Forge | P0 | Performance tuning: batch sizes for the development workstation GPU path, SQLite WAL, memory profiling — target incremental nightly < 90min | DONE (embed 15610 chunks/sec CUDA, GPU 95-100%, parse bottleneck identified) | reviewer |
| 5.3 | Forge | P0 | Demo prep: verify V2 demo queries work against Forge data, operator documentation | DONE (OPERATOR_QUICKSTART.md) | reviewer |

**Exit Criteria:** Full corpus processed, incremental nightly < 90min, operator docs complete.

### V2 Sprint 15: Operator Hardening + Final Golden Eval (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 15.1 | V2 | P0 | Performance tuning on full corpus (P50 <3s, P95 <10s) | DONE (P50=20ms, P95=57ms) | reviewer |
| 15.2 | V2 | P0 | Final golden eval on production data -- target 20/25 | DONE (25/25) | reviewer |
| 15.3 | V2 | P0 | V1 vs V2 comparison harness on real data | DONE (report) | reviewer |
| 15.4 | V2 | P1 | Deployment guide finalization, operator training materials | DONE | reviewer |
| 15.5 | V2 | P1 | Demo rehearsal: 10 queries under time target, recovery plays | DONE (10/10) | reviewer |

**Exit Criteria:** 20/25 golden eval, P50 <3s, demo rehearsed, deployment guide complete.

### QA (reviewer)

| Task | Repo | Priority | What | Status |
|------|------|----------|------|--------|
| QA-5 | Forge | P0 | QA full corpus run (manifest stats, error rate, timing) | TODO |
| QA-15 | V2 | P0 | QA golden eval results, V1 vs V2 comparison review | TODO |
| IC-4 | Both | P0 | Demo dry run: 10 demo queries through full Forge→V2 pipeline | TODO |
| SMASH | Both | P0 | Button smash both GUIs (full 12-scenario deck each) | TODO |

---

## EMERGENCY: Sprint 6 (Forge) + Sprint 16 (V2) — Production Ingest Blockers

**Added:** 2026-04-08 | **Why:** Four P0 blockers discovered that prevent production 700GB corpus ingest

**Coordinator Update:** 2026-04-08 MDT — catch-up mode now runs as three parallel lanes:
- `reviewer` owns `C:\CorpusForge` mainline and the Forge Sprint 6 critical path only.
- `reviewer` owns `C:\CorpusForge_Dev` and the Sprint 7 real-data analysis lane.
- `reviewer` owns `C:\HybridRAG_V2_Dev` and the V2 Sprint 16 accepted-export import/eval lane.
- QA stays on standby and picks up validation as soon as a lane posts `Ready for QA`.

**Crash/Handoff Rule:** Before any lane pauses for more than 30 minutes, changes ownership, or claims completion, it must:
1. update both `docs/SPRINT_SYNC.md` copies,
2. write a dated handoff/evidence note under `docs/`,
3. record repo, branch, GPU assignment, data subset, commands run, outputs, blockers, and next step.

**Execution Rules:**
- Use the real repo, repo-local venv, real hardware, and real production data whenever possible per `docs/Repo_Rules_2026-04-04.md` and the shared QA protocol in `C:\HybridRAG_V2\docs\QA_EXPECTATIONS_2026-04-05.md`.
- Constrain each run to one GPU with `CUDA_VISIBLE_DEVICES`; if both GPUs are busy, take the lesser-used GPU and document the choice.
- Mainline Forge keeps GPU 0 by default; clone/sample or V2 rehearsal lanes use GPU 1 by default unless telemetry shows GPU 0 is less loaded.
- Any GUI-touching slice must run the full GUI harness tiers A-D from `C:\HybridRAG_V2\docs\QA_GUI_HARNESS_2026-04-05.md`, including a human button smash by a non-author before signoff.
- Every completion note must include a deep evidence packet: real-data subset used, hardware, GPU, commands, key metrics, logs/screenshots, and whether GUI harness/button smash ran.


### Forge Sprint 6: Production Ingest Enablement (P0 — START IMMEDIATELY)

**Ownership:** reviewer is the only writer on `C:\CorpusForge` mainline and the primary owner of production dedup/hash state.

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 6.1 | Forge | P0 | Bulk transfer syncer + GUI Transfer panel + CLI run_transfer.py | DONE (2026-04-08) | reviewer |
| 6.2 | Forge | P0 | Deduplicator fixed: mtime tolerance, _N suffix, progress callback, 15 tests | DONE (2026-04-08) | reviewer |
| 6.3 | Forge | P0 | GUI progress: all stages emit on_stage_progress every 5s, CLI heartbeat | DONE (2026-04-08) | reviewer |
| 6.4 | Forge | P0 | Sanitizer: 6 patterns added, .gitignore updated, 126 files clean. V2 needs reviewer parity. | DONE (Forge, 2026-04-08) | reviewer |
| 6.5 | Forge | P0 | Dedup-only GUI panel with scanned/dupes/current/elapsed/ETA | DONE (2026-04-08) | reviewer |
| 6.6 | Forge | P0 | Production corpus ingest (blocked on QA of 6.1-6.5) | **RUN 6 LANDED CLEAN, ZERO SAO/RSF LEAK VERIFIED (2026-04-09 07:25 MDT).** New canonical export: `data/production_output/export_20260409_0720/` — **242,650 chunks + 242,650 vectors float16, 32 minute runtime**. Hard verification re-pulled from chunks.jsonl: `*.sao.zip`=0, `*.rsf.zip`=0, any 'sao' dot-segment=0, any 'rsf' dot-segment=0, top-level `*.sao`=0, top-level `*.rsf`=0. The archive-defer fix from Run 6's working copy is operational at production scale on real data. Format coverage: .xlsx 189,862 (logistics gold) / .pdf 14,324 / .jpg 14,623 (metadata-only, no Tesseract) / .zip 1,307 (16 legitimate non-SAO archives only — was 102,786 with 100,055 SAO leak in Run 5). Equivalence check vs Run 5+filter: Run 6 = 242,650 chunks, Run 5 - SAO filter = 244,074 chunks → within 0.6%. **(1) Bug fix:** `src/parse/parsers/archive_parser.py` segment-based defer wired through `src/parse/dispatcher.py` + `src/pipeline.py`. **(2) Regression test:** `tests/test_archive_member_defer.py` 7/7 + existing 23 parser/pipeline e2e tests pass. **(3) Short proof sample (mechanism):** `export_20260409_0646/` — 7 chunks, 0 SAO leak. **(4) Run 6 (production validation):** `export_20260409_0720/` — 242,650 chunks, 0 SAO leak. **(5) V2 import-side filter:** still available in `import_embedengine.py` as `--exclude-source-glob`, durable `import_report_*.json` artifact written by `run_dry_run` and `run_import`; no longer needed for Run 6 but kept for safety net + retroactive Run 5 imports. **MORNING RECOMMENDATION:** import the clean Run 6 export — `--source C:\CorpusForge\data\production_output\export_20260409_0720 --create-index` (NO --exclude-source-glob needed). UNRESOLVED before operational signoff: code-state provenance (linter/other edits in pipeline.py still need commit-split or accept), `.ppt` legacy parser garbage (178 chunks), Forge 6.1-6.5 QA gate. **NOTE on files_failed=7068:** ~6,550 of those are SAO.zip archives that the new archive-defer fix correctly refuses to extract — they return empty docs at parse() entry, which the pipeline accounting counts as "failed". This is a semantic mislabeling, not a real failure. Evidence: `docs/SPRINT_6_6_EVIDENCE_2026-04-08.md`, `docs/HANDOVER_2026-04-09.md`, Run 6 README at `data/production_output/export_20260409_0720/READ_ME_BEFORE_USE.txt`. | reviewer |
| 6.7 | Forge | P0 | GUI control + live telemetry: safe stop semantics, live chunks/chunks-sec, honest CPU/IO stage wording, GUI harness/button smash | DONE (2026-04-09, ready for QA) | reviewer |

### Forge Nightly Delta Scheduling Lane (READY FOR QA)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| ND.1 | Forge | P0 | Source-side delta tracker with persisted resume state and canary accounting | DONE (2026-04-09, `src/download/delta_tracker.py`; source file state uses `hashed` -> `mirrored` in `transfer_state_db`) | reviewer |
| ND.2 | Forge | P0 | Nightly delta runner: scan source, mirror delta only, write manifests/input-list, then run `Pipeline.run()` on the mirrored subset | DONE (2026-04-09, `scripts/run_nightly_delta.py`; clean stop via signal or `stop_file`; original source provenance preserved in exported chunks) | reviewer |
| ND.3 | Forge | P1 | Windows scheduled-task helper for the workstation desktop | DONE (2026-04-09, `scripts/install_nightly_delta_task.py`; XML emitted successfully, task not installed in proof lane) | reviewer |
| ND.4 | Forge | P1 | Config wiring for the active nightly lane | DONE (2026-04-09, `config/config.yaml` + `src/config/schema.py`; duplicate `nightly_delta` block removed, active keys now include `transfer_state_db`, `stop_file`, `task_name`, `task_start_time`) | reviewer |
| ND.5 | Forge | P1 | Canary/delta proof with replay on the same source subset | DONE (2026-04-09, proof root `C:\CorpusForge\data\nightly_delta_proof_20260409`; pass 1 `2 delta/2 copied/2 chunks`, pass 2 `1 changed/1 copied/1 chunk`, pass 3 `0 delta`; report JSONs + `run_history.jsonl` are authoritative because the packager export dir is minute-granular) | reviewer |
| ND.6 | Forge | P1 | Validation and operator evidence | DONE (2026-04-09, focused pytest lane + automated GUI regression pass; no GUI files changed in this lane, so full Tier A-D + non-author button smash was not triggered; OCR tools absent, so lane is text-first only) | reviewer |

**Exit Criteria:** Operator can transfer 700GB, dedup it, see live progress at every stage, and produce clean exports for V2. Zero program-specific terms on remote.

### V2 Sprint 16: Clean Import + Sanitization

**Execution Note:** reviewer completed the accepted-export proof in `C:\HybridRAG_V2_Dev`; promotion to the main V2 store still waits for explicit approval after QA and remediation.

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 16.1 | V2 | P0 | Sanitizer fix — same patterns as Forge 6.4. Run --apply on tracked files. Push clean when verified. | DONE IN V2_Dev (parity script ported, banned filename check added, 2 tracked fixtures sanitized) | reviewer |
| 16.2 | V2 | P0 | Add CoPilot+.md to .gitignore — never push agent instruction files to remote | DONE IN V2_Dev (CoPilot+.md + config.local ignored; CoPilot+.md removed from git index) | reviewer |
| 16.3 | V2 | P0 | Import fresh Forge export — subset rehearsal now in V2_Dev, full production rebuild after Forge 6.6 | DONE IN V2_Dev (accepted export `C:\CorpusForge_Dev\data\output_dev\export_20260408_2051`; imported `83,022` chunks from `947` docs into clone-local `data\index_dev\lancedb`; IVF_PQ index ready) | reviewer |
| 16.4 | V2 | P0 | Run tiered extraction — subset now, full production corpus after 16.3/Forge 6.6. Tier 1 regex + Tier 2 GLiNER on single GPU. | DONE IN V2_Dev (single-GPU run on physical GPU 1 via `CUDA_VISIBLE_DEVICES=1`; `302,748` entity rows and `0` relationship rows in clone-local `entities.sqlite3`; fixed Tier 2 `tier1_chunk_ids` filter bug in `scripts/tiered_extract.py`, narrowing GLiNER to `15,473` chunks) | reviewer |
| 16.5 | V2 | P0 | Golden eval — subset now, production target 20/25 after 16.4 full run | READY FOR QA IN V2_Dev (retrieval-only eval `11/36`, routing `32/36`, avg `81 ms`; direct corpus-native probes positive; promotion hold recommended pending relationship coverage, entity-noise cleanup, and eval alignment) | reviewer |

**Exit Criteria:** Zero program-specific terms on remote. Clean V2 store from production corpus. 20/25 golden eval on real data.

---

## Sprint 7 (Forge): Production Data Analysis + Recovery Strategy (NEW)

**Added:** 2026-04-08 | **Data:** 90GB production source at `C:\CorpusForge\ProductionSource`
**Agent:** reviewer (export production) + reviewer (V2 consumption) — works in clone repos `C:\CorpusForge_Dev` and `C:\HybridRAG_V2_Dev`
**Purpose:** Use real production data to refine dedup strategy, extraction patterns, enrichment quality, and chunking parameters before the full 700GB ingest.
**Execution Note:** reviewer produced the accepted 1000-file export package; reviewer consumed that package in `C:\HybridRAG_V2_Dev` for Sprint 16 phase 2.

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 7.1 | Forge_Dev | P0 | Dedup analysis on 90GB — run dedup on ProductionSource, report: total files, unique files, duplicate families, format distribution, volume reduction %, duplicate patterns (suffix _1, cross-format .doc/.docx/.pdf). Preserve hash state for incremental skip continuity. | DONE (49.7% dupes, all _1 suffix, zero cross-format. Evidence: SLICE_7_1_DEDUP_EVIDENCE_2026-04-08.md) | reviewer |
| 7.2 | Forge_Dev | P0 | Format coverage audit — what formats actually appear in production data? Which parsers succeed/fail? Which produce quality chunks vs garbage? Report per-format: file count, parse success rate, avg chunks per file, quality score distribution. | DONE (TEXT-ONLY — Tesseract/Poppler missing. ~2,450 text files parseable, .rsf is junk. Evidence: SLICE_7_2_FORMAT_COVERAGE_EVIDENCE_2026-04-08.md) | reviewer |
| 7.3 | Forge_Dev | P1 | Chunking quality analysis — are 1200/200 settings optimal for these document types? Sample 500 chunks, review: are boundaries sensible? Do headings get preserved? Are tables split badly? Recommend tuning. | DONE (77% chunks in target range, 1200/200 confirmed. Evidence: SLICE_7_3_CHUNKING_QUALITY_EVIDENCE_2026-04-08.md) | reviewer |
| 7.4 | Forge_Dev | P1 | Tier 1 regex pattern refinement — run regex extraction on 1000 real chunks. What entities appear? Which patterns hit? Which miss? What new patterns needed for production data? Report entity yield by type and pattern. | DONE (94.2% coverage, 3311 c/s. Phone pattern over-matches. Evidence: SLICE_7_4_REGEX_EXTRACTION_EVIDENCE_2026-04-08.md) | reviewer |
| 7.5 | Forge_Dev | P1 | Tier 2 GLiNER vs regex comparison — run both on same 1000 chunks. Compare: entity count, type coverage, unique entities found by GLiNER that regex missed, confidence distribution. Quantify the value-add of GLiNER over regex-only. | DONE (100 chunks, complementary methods, 82 GLiNER-only entities. Evidence: SLICE_7_5_GLINER_VS_REGEX_EVIDENCE_2026-04-08.md) | reviewer |
| 7.6 | Forge_Dev | P1 | Sample enrichment quality — enrich 100 real chunks with phi4:14B. Review preambles: are they accurate? Do they improve retrievability? Compare enriched vs non-enriched retrieval on 10 test queries. | SKIPPED (time constraint — enrichment deferred per 7.9 recommendation) | reviewer |
| 7.7 | Forge_Dev | P0 | Full pipeline proof on 1000-file subset — parse + dedup + chunk + embed + extract (no enrich for speed). End-to-end validation on real data. Report all metrics. | DONE (TEXT-ONLY. 947/1000 parsed, 83,022 chunks+vectors. Export: C:\CorpusForge_Dev\data\output_dev\export_20260408_2051. Evidence: SLICE_7_7_E2E_PROOF_EVIDENCE_2026-04-08.md) | reviewer |
| 7.8 | Forge_Dev | P0 | V2 import test — export the 1000-file subset, import into V2_Dev clone, run golden eval. Does real production data produce usable query results? | DONE (accepted export `C:\CorpusForge_Dev\data\output_dev\export_20260408_2051` consumed in `V2_Dev`; import/extraction/eval evidence captured. Direct corpus-native probes are usable, but mainline promotion stays on hold because relationship rows remained `0`, entity noise is high, and the golden gate failed.) | reviewer |
| 7.9 | Forge_Dev | P1 | Recovery strategy recommendation — based on all findings, document: optimal dedup approach, recommended extraction tiers, chunking params, enrichment value, estimated time for full 700GB pipeline. Feed into Sprint 6 decisions. | DONE (text-first ~55 min, .rsf defer, two-pass extraction, Tesseract needed for Phase 2. Evidence: SLICE_7_9_RECOVERY_STRATEGY_2026-04-08.md) | reviewer |

**Exit Criteria:** Data-driven understanding of production corpus characteristics. Dedup strategy proven on 90GB. Extraction patterns refined on real data. Chunking/enrichment quality validated. Recovery strategy documented with real numbers.

**Hash continuity rule:** Whatever dedup approach is used, hash-based incremental skip must survive. When the remaining 610GB arrives or we reconnect to production source, already-processed files must be recognized and skipped by hash.

---

## Sprint 7 Follow-On (Forge_Dev): Config Hardening + Operator Readiness

**Added:** 2026-04-08 | **Agent:** reviewer (support/config lane, CPU-only)
**Purpose:** Convert Sprint 7 lessons into reusable operator artifacts. No new GPU-heavy work.

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 7F.1 | Forge_Dev | P1 | Demo text-only config preset (config.demo_text_only.yaml) — defers images/archives/sensor/.xml by config | DONE | reviewer |
| 7F.2 | Forge_Dev | P1 | Skip/defer visibility — remove 8-format truncation in run_pipeline.py, add per-extension breakdown to run_report.txt | DONE (2 code patches, safe to cherry-pick) | reviewer |
| 7F.3 | Forge_Dev | P1 | Failure taxonomy for 53 unparsed files — restricted into scanned PDF (24), DOCX parser bug (14), edge-case PDF (10), image PPTX (2), XLSX (1) | DONE (FAILURE_TAXONOMY_7_7_2026-04-08.md) | reviewer |
| 7F.4 | Forge_Dev | P1 | Workstation prerequisite plan — Tesseract, Poppler, ONNX install/verify guide | DONE (WORKSTATION_PREREQUISITES_2026-04-08.md) | reviewer |
| 7F.5 | Forge_Dev | P1 | Operator runbook — demo text-only export, defer confirmation, skip accounting | DONE (OPERATOR_RUNBOOK_DEMO_TEXT_ONLY_2026-04-08.md) | reviewer |

**Exit Criteria:** Operator can run a demo-safe text-only export using the preset, see all deferred formats with reasons, and knows what to install for Phase 2.

---

## Sprint 8 (Infra): Clone Repo Setup for Parallel Development (NEW)

**Added:** 2026-04-08 | **Agent:** reviewer (new, infrastructure)
**Purpose:** Set up clone repos so multiple agents can work in parallel without file conflicts.

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 8.1 | primary workstation | P0 | Clone CorpusForge: `git clone C:\CorpusForge C:\CorpusForge_Dev`. Rebuild venv from scratch (`python -m venv .venv && pip install -r requirements.txt`). Do NOT copy .venv. Verify CUDA: `python -c "import torch; print(torch.cuda.is_available())"`. | TODO | reviewer |
| 8.2 | primary workstation | P0 | Clone HybridRAG V2: `git clone C:\HybridRAG_V2 C:\HybridRAG_V2_Dev`. Rebuild venv from scratch. Verify CUDA + all imports work. | TODO | reviewer |
| 8.3 | primary workstation | P0 | Create config.local.yaml for each clone: separate output_dir (avoid conflicts with main repo), separate GPU assignment (clone gets GPU 1, main gets GPU 0). Point Forge_Dev source_dirs at `C:\CorpusForge\ProductionSource`. | TODO | reviewer |
| 8.4 | primary workstation | P0 | Verify clone isolation: run pipeline in Forge_Dev, confirm output goes to clone's output dir, confirm main repo is untouched. Run pytest in both clones. | TODO | reviewer |
| 8.5 | primary workstation | P1 | Document clone workflow: how to pull updates from main, how to sync findings back, rules (never push from clone, code changes in main only). | TODO | reviewer |

**Clone Exit Criteria:** Both clone repos functional with independent venvs, configs, and output dirs. Main repos untouched by clone activity.

## Docs / Sanitizer / Test-Plan Lane (2026-04-09)

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 7G.1 | Both | P1 | Remove the workstation nickname from remote-bound theory docs, sprint boards, and handover; add sanitizer parity rule so the nickname does not reappear in tracked docs | DONE | reviewer |
| 7G.2 | Forge | P1 | Restore Source-to-V2 assembly-line guide with worker override, hash continuity, and human-vs-automatic flow | DONE | reviewer |
| 7G.3 | Forge | P1 | Rewrite the golden/canary plan around the real 53-file dry run, the Sprint 7 1000-file subset, the current clean export, the V2 import handoff, and the hashed-state resume check | DONE | reviewer |
| 7G.4 | Forge | P1 | Correct operator/runtime docs so `config/config.yaml` is the live runtime config and GUI Save Settings target; retire mainline `config.local` guidance | DONE | reviewer |
| 7G.5 | Forge | P2 | Call out that low GPU during parse is expected because parse is mostly CPU/I/O/OCR bound, then fold tonight's docs-lane details into the handover | DONE | reviewer |
| 7G.6 | Both | P2 | Run sanitizer verification after the doc refresh and confirm the workstation nickname does not regress in remote-bound docs or sprint boards | DONE (2026-04-09; final V2 `CHANGELOG.md` sanitizer hit removed, both repo dry-runs clean) | reviewer |

**Docs Lane Exit Criteria:** Remote-bound docs and synced sprint boards stay sanitize-clean; CorpusForge docs reflect `config/config.yaml` as the live runtime config; the canary/golden plan names the real data subsets, current clean export, V2 import path, and hashed-resume expectation; handover captures tonight's docs lane.

---

## Parallel Recovery / Adaptation Queue (2026-04-09)

**Added:** 2026-04-09 | **Purpose:** use the production-like sample tree and the next real Forge export to harden family-aware parsing, skip/defer policy, and downstream retrieval without exposing production-specific categories.

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| CA.1 | Forge | P0 | Corpus adaptation profiling: run the new profiler on the local sample tree now, then on the next real Forge export artifacts (`manifest.json`, `run_report.txt`, `skip_manifest.json`, `chunks.jsonl`, failure list/log`). Write evidence note with generic document-family findings only. | READY FOR QA (2026-04-09; evidence in `docs/CORPUS_ADAPTATION_EVIDENCE_2026-04-09.md`; sample-tree profile plus real export `export_20260409_0720` analyzed; no strong auto-skip rule promoted from this pass) | reviewer |
| CA.2 | Forge | P0 | Family-aware skip/defer hardening: convert high-confidence profiler findings into visible skip/defer candidates for OCR sidecars, derivative junk, encrypted-PDF naming cues, and archive-duplicate reporting where precision justifies it. Add tests. | READY FOR QA (2026-04-09; evidence in `docs/SKIP_DEFER_HARDENING_2026-04-09.md`; live-config smoke in `docs/SKIP_DEFER_HARDENING_2026-04-09_live_config_smoke.txt`; proof in `docs/SKIP_DEFER_HARDENING_2026-04-09_proof.json`; overlap regression added; hash/resume unchanged) | reviewer |
| CA.3 | V2 | P1 | Family-aware query-routing plan: map generic document families into query classification, retrieval weighting, metadata usage, and table-vs-narrative handling. Planning/doc lane first unless a very small safe code improvement is obvious. Artifact: `C:\HybridRAG_V2\docs\FAMILY_AWARE_QUERY_ROUTING_PLAN_2026-04-09.md`. | READY FOR QA | reviewer |
| CA.4 | Both | P1 | GPU execution guidance plan: define which stages should use one GPU, an additional local GPU, or CPU-only paths; distinguish proven paths from experiments; call out any hardcoded thresholds that should become config. | READY TO ASSIGN | reviewer |
| CA.QA | Both | P0 | QA new adaptation lanes as they land. Runtime-changing lanes require targeted pytest and proof artifact inspection; GUI changes still require full Tier A-D + non-author smash. | READY | reviewer |

**Queue Artifacts:** `docs/CORPUS_ADAPTATION_PLAN_2026-04-09.md`, `docs/CORPUS_ADAPTATION_SLICES_2026-04-09.md`, `docs/DOCUMENT_FAMILY_MATRIX_2026-04-09.md`, `docs/FIELD_MINING_PLAYBOOK_2026-04-09.md`, `docs/PARALLEL_WORK_QUEUE_2026-04-09.md`.

**Clone Rules (carry forward):**
- Clones are for testing/development ONLY — never push from a clone
- All code changes happen in main repo, then `git pull` into clone
- Each clone gets its own config.local.yaml (different output dirs, GPU assignment)
- Venv MUST be rebuilt from scratch — copied venvs break on Windows (hardcoded paths)

---

## Sprint 9 (2026-04-10): review board Lanes

**Added:** 2026-04-10 | **Purpose:** recover from the lost 700GB long-run payload, convert the captured corpus metadata into retrieval value, and keep the four-lane team moving from a single coordinator board.

| Slice | Repo | Priority | What | Status | Owner |
|-------|------|----------|------|--------|-------|
| 9.1 | Forge | P0 | Durability / chunk checkpointing: persist parse/chunk output during long runs, resume after stop/crash before export, and keep export safety guarantees intact. | READY FOR QA (corrected packet at `data/sprint9_lane1_validation_20260410_171433/hardware_proof_report.json` plus handoff/checklist in `docs/SPRINT9_1_DURABILITY_HARDWARE_HANDOFF_2026-04-10.md` and `docs/SPRINT9_1_DURABILITY_QA_CHECKLIST_2026-04-10.md`. The absolute proof command is now replayable and refreshes the fixed proof root in place. Real subset: 8 files with 4 duplicate pairs; dedup-only reduced to 4 canonicals and preserved source-relative portable copy `4/4`. Stop pass left `_checkpoint_active` with `2 docs / 59 chunks`, status `stopped_before_export`, and no export dir. Compatible rerun emitted `Resumed 2 files / 59 chunks from checkpoint.` and exported `62` aligned chunks/vectors (`vector_dim=768`). Separate live-embed run on the same subset proved CUDA activity before parse finished: live snapshot `files_parsed=1/4`, `vectors_created=1`, GPU memory `2111 MiB` vs `36 MiB` baseline, `5` saved `nvidia-smi` samples, and nonzero torch CUDA allocations/reservations. Targeted tests passed: `tests/test_pipeline_e2e.py` `23/23`, `tests/test_gui_button_smash.py` `16/16`, isolated `tests/test_gui_dedup_only.py` `14/14` from an alternate working directory; the combined slice still hits a workstation Tk blocker at the shared `root` fixture with `_tkinter.TclError: invalid command name \"tcl_findLibrary\"`) | reviewer |
| 9.2 | Forge | P1 | Runtime config simplification / operator clarity: inventory remaining config files, enforce `config/config.yaml` as the live runtime path, and retire/quarantine stale operator-facing config confusion. | READY FOR QA (2026-04-10: truth map + handoff at `docs/LANE9_2_CONFIG_SIMPLIFICATION_HANDOFF_2026-04-10.md`; added `config/CONFIG_INVENTORY_2026-04-10.md`; GUI, CLI, precheck, and operator docs now consistently call out `config/config.yaml` as the live runtime config; `paths.skip_list` intentionally remains `config/config.yaml`; legacy/preset YAMLs are labeled non-runtime; precheck now resolves relative `--config` against repo root before reporting it; focused tests `tests/test_config.py`, `tests/test_gui_dedup_only.py`, and `tests/test_gui_button_smash.py` passed 49/49; external-cwd `boot.py` + precheck proof passed; Tier D non-author human GUI button smash still required before signoff) | reviewer |
| 9.3 | Both | P1 | Retrieval metadata schema: convert captured corpus structure into implementation-ready metadata fields and ranking/filter rules for DM, logistics, cybersecurity, archive, and future V3 linkage. Artifacts: `C:\CorpusForge\docs\RETRIEVAL_METADATA_SCHEMA_SPRINT9_2026-04-10.md`, `C:\HybridRAG_V2\docs\RETRIEVAL_METADATA_SCHEMA_SPRINT9_2026-04-10.md`, and bounded probe packet `C:\HybridRAG_V2\docs\RETRIEVAL_METADATA_GPU_PROBE_2026-04-10.{md,json}`. | READY FOR QA (GPU addendum) | reviewer |
| 9.4 | Both | P1 | Nightly delta / scheduler / admin-panel plan: implementation-ready slices for unattended delta copy + Forge pipeline + V2 staging/import, with stop/pause/resume expectations, V1 prior art references, canary strategy, and plan doc at `C:\CorpusForge\docs\NIGHTLY_DELTA_SCHEDULER_ADMIN_PLAN_2026-04-10.md`. | READY FOR QA (design lane only; main packet `docs/NIGHTLY_DELTA_SCHEDULER_ADMIN_PLAN_2026-04-10.md`, handoff `docs/LANE4_NIGHTLY_DELTA_HANDOFF_2026-04-10.md`, targeted tests passed: Forge `tests/test_nightly_delta.py`, V2 `tests/test_stage_forge_import.py`) | reviewer |
| 9.QA | Both | P0 | QA lane for Sprint 9. Runtime-changing work still requires targeted tests and proof artifacts; GUI/runtime operator claims still require harness coverage and non-author validation before signoff. | READY | QA |

**Sprint 9 Board:** `C:\CorpusForge\___WAR_ROOM_BOARD_2026_04_10.md`

---

## May 2 — DEMO DAY

| Item | Repo | Owner | Acceptance |
|------|------|-------|-----------|
| 10 demo queries covering all failure classes | V2 | reviewer | All return results with sources |
| V1 vs V2 comparison (side-by-side) | V2 | reviewer | V2 visibly better on aggregation/entity queries |
| Full corpus processed and current | Forge | reviewer | Nightly ran successfully night before |
| Zero crashes during demo | Both | reviewer (QA) | Button smash passed, recovery plays tested |
| Skip file acknowledgment (what we can't parse and why) | Forge | reviewer | Format coverage matrix visible |

---

## Parallel Work Matrix

| Week | reviewer (Forge) | reviewer (V2) | reviewer (QA) | Conflicts |
|------|-----------------|--------------|-------------|-----------|
| 1 (Apr 7-11) | S2: GUI + pdfmeta + config.local | S12: Dedup hardening + import validation | QA S2 + S12 | NONE |
| 2 (Apr 12-18) | S3: Enrichment + GLiNER | S13: Canonical rebuild | QA S3 + S13, IC-1, IC-2 | GATE-1 |
| 3 (Apr 19-25) | S4: Polish + headless + tests | S14: Entity promotion at scale | QA S4 + S14, IC-3, button smash | GATE-2 |
| 4 (Apr 26-May 1) | S5: Full corpus + perf tune | S15: Golden eval + demo prep | QA S5 + S15, IC-4, demo dry run | Both must complete |

---

## Update Protocol

1. **Every agent updates ALL 3 copies** of this file at end of each sprint session
2. When a sprint completes → update Status column + add completion date
3. When a GATE is reached → reviewer verifies gate condition before unblocking
4. If a sprint slips → update ETA + flag downstream impact in this doc
5. Jeremy (Operator) has absolute authority to override any gate, priority, or assignment

---

Signed: reviewer (QA/Planning) | HybridRAG3_Educational | 2026-04-07 | MDT
