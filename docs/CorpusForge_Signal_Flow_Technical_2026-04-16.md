# CorpusForge — Signal Flow, Module To Module (Technical)

**Author:** CoPilot+ | Jeremy Randall
**Date:** 2026-04-16 MDT
**Audience:** software engineers, QA, infra, new maintainers
**Format:** end-to-end signal trace across the live package layout
**Companion doc:** `CorpusForge_Signal_Flow_Nontechnical_2026-04-16.md`

---

## Scope

This document traces one full ingest — from operator trigger through stage-by-stage module execution — calling out:

- the file that owns each stage,
- the data handed between stages,
- durability points (checkpoints, manifests),
- failure and resume semantics,
- config gates and env-var toggles,
- GPU vs CPU paths.

It is a **sequence / dataflow** doc. For the static module map, read
`Module_Level_Explanation_Technical_2026-04-15.md`.

---

## Block Diagram — Signal Flow

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                          OPERATOR SURFACE                           │
 │   start_corpusforge.bat ──► src/gui/launch_gui.py ──► src/gui/app.py│
 │                          OR                                         │
 │   scripts/run_pipeline.py  (CLI / nightly)                          │
 │                          OR                                         │
 │   scripts/nightly_delta_ingest.py  (scheduled task)                 │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   BOOT + CONFIG                                                     │
 │   scripts/boot.py ──► src/config/schema.py                          │
 │     reads config/config.yaml, validates, returns typed AppConfig    │
 │     ─ env gates: CUDA_VISIBLE_DEVICES, CORPUSFORGE_HEADLESS,        │
 │       HYBRIDRAG_POPPLER_BIN, TESSERACT_CMD                          │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   GPU SELECTION                                                     │
 │   src/gpu_selector.py                                               │
 │     select_gpu() ─► apply_gpu_selection()                           │
 │     honors CUDA_VISIBLE_DEVICES / config override                   │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   CONDUCTOR                                                         │
 │   src/pipeline.py :: Pipeline                                       │
 │     __init__()  ─► wires skip / parse / chunk / enrich / embed /    │
 │                    extract / packager / chunk_checkpoint            │
 │     run()       ─► stage loop with cooperative stop (skip_signal)   │
 │     RunStats    ─► per-run counters surfaced to GUI                 │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
     ┌─────────────────────────────┼─────────────────────────────┐
     ▼                             ▼                             ▼
 STAGE 1                        STAGE 2                       STAGE 3
 HASH                           DEDUP                         SKIP/DEFER
 src/download/                  src/download/                 src/skip/
 hasher.py                      deduplicator.py               skip_manager.py
                                src/dedup/                    (+ defer tokens
                                document_dedup.py             for archives)
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   STAGE 4 — PARSE                                                   │
 │   src/parse/dispatcher.py     ─► fan-out by extension               │
 │   src/parse/parsers/*.py      ─► one module per format              │
 │   src/parse/parsers/docling_bridge.py  (opt. premium converter)     │
 │   src/parse/quality_scorer.py ─► per-doc quality metric             │
 │   Output: list[ParsedDocument]                                      │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   STAGE 5 — CHUNK                                                   │
 │   src/chunk/chunker.py    ─► text → chunks                          │
 │   src/chunk/chunk_ids.py  ─► stable chunk_id generation             │
 │   Output: list[Chunk]                                               │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   DURABILITY POINT — CHECKPOINT                                     │
 │   src/export/chunk_checkpoint.py                                    │
 │     writes _checkpoint_active/* under run output root               │
 │     resume contract: files_parsed + chunks preserved                │
 │     clears on successful Stage 9 export                             │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   STAGE 6 — ENRICH (optional)                                       │
 │   src/enrichment/contextual_enricher.py                             │
 │     off by default; graceful degradation                            │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   STAGE 7 — EMBED (GPU)                                             │
 │   src/embed/embedder.py        ─► nomic-embed-text, dim=768, fp16   │
 │   src/embed/batch_manager.py   ─► token-budget packing, OOM backoff │
 │     CUDA required for full throughput; CPU fallback supported       │
 │     Output: vectors (np.float16, shape [N_chunks, 768])             │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   STAGE 8 — EXTRACT (optional)                                      │
 │   src/extract/gliner_extractor.py                                   │
 │     GLiNER entity pull; off by default                              │
 │     Output: entities.jsonl                                          │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   STAGE 9 — EXPORT                                                  │
 │   src/export/packager.py                                            │
 │     writes under data/production_output/export_YYYYMMDD_HHMM/:      │
 │       chunks.jsonl                                                  │
 │       vectors.npy  (np.float16, [N,768])                            │
 │       entities.jsonl (optional)                                     │
 │       manifest.json                                                 │
 │       skip_manifest.json                                            │
 │     updates `latest` pointer; clears checkpoint                     │
 └─────────────────────────────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
   OPERATOR SURFACE         OFFLINE ANALYSIS         V2 HANDOFF
   src/gui/stats_panel      src/analysis/*.py        C:\HybridRAG_V2\
   src/gui/safe_after       scripts/audit_corpus.py  scripts\
   (bg-thread → main        scripts/analyze_export_  stage_forge_
   thread marshaling)       artifacts.py             import.py
                            tools/run_critical_
                            e2e_gate.py
```

---

## 1. Operator Trigger Surface

Three entry points, one shared conductor:

| Surface | Entrypoint | Notes |
|---|---|---|
| Desktop GUI | `start_corpusforge.bat` → `src/gui/launch_gui.py` → `src/gui/app.py::CorpusForgeApp` | Tk root; background runner threads; UI updates via `src/gui/safe_after.py` queue drain |
| CLI / ad-hoc | `scripts/run_pipeline.py` | Parses argv, calls `scripts/boot.py`, constructs `Pipeline`, `Pipeline.run()` |
| Dedup-only recovery | `scripts/build_document_dedup_index.py`, `src/gui/launch_dedup_gui.py` | Bypasses parse→embed; writes dedup-only manifest |
| Scheduled | `scripts/nightly_delta_ingest.py` + `scripts/install_nightly_delta_task.py` | Delta lane; only new/changed files |

All paths converge on `src/pipeline.py::Pipeline`.

---

## 2. Boot + Config

- `scripts/boot.py` is the config entrypoint. It invokes `src/config/schema.py` which parses `config/config.yaml` into a typed `AppConfig`-shaped model.
- `config/config.yaml` is the **only** live runtime config (see `config/CONFIG_INVENTORY_2026-04-10.md`). `config.local.yaml` is archived.
- Environment gates that matter:
  - `CUDA_VISIBLE_DEVICES` — GPU pinning.
  - `CORPUSFORGE_HEADLESS=1` — disables Tk; forces CLI-only UI.
  - `HYBRIDRAG_POPPLER_BIN` — override for scanned-PDF OCR rasterization.
  - `TESSERACT_CMD` — override for Tesseract binary resolution.

---

## 3. GPU Selection — `src/gpu_selector.py`

- `select_gpu(config)` picks a device index based on `CUDA_VISIBLE_DEVICES` or config override.
- `apply_gpu_selection(choice)` pins Torch/CUDA context before any heavy module imports.
- Call order matters: selector runs before `src/embed/embedder.py` imports Torch-CUDA kernels. Reversing the order breaks pinning.

---

## 4. The Conductor — `src/pipeline.py`

### Responsibilities

- Wires every stage: `SkipManager`, parser dispatcher, `Chunker`, `ContextualEnricher`, `Embedder`, `GlinerExtractor`, `Packager`, `ChunkCheckpoint`.
- Owns the cooperative-stop signal (`src/util/skip_signal.py`) that GUI Stop / SIGTERM trip.
- Emits `RunStats` snapshots per stage (surfaced to GUI).

### Stop / resume contract

- Stop between Stages 5 and 7 → checkpoint is `_checkpoint_active`, manifest status `stopped_before_export`, no `export_YYYYMMDD_HHMM/` directory.
- Stop after Stage 9 starts → run completes (idempotent) or leaves a partial export; checkpoint cleared on success.
- Rerun on same `(source, output_root)` reads checkpoint and emits `Resumed N files / M chunks from checkpoint.`

Covered by `tests/test_pipeline_e2e.py` (23 tests) and the Sprint 9.1 hardware-proof packet.

---

## 5. Stages In Order

### Stage 1 — Hash (`src/download/hasher.py`)

- Walks source root; emits content-hash + state record per file.
- Idempotent across runs via persisted state (`data/file_state.sqlite`).
- Tradeoff: first run on a new source dominates wall time; subsequent runs are cheap.

### Stage 2 — Dedup (`src/download/deduplicator.py` + `src/dedup/document_dedup.py`)

- `deduplicator.py` is file-state-level: same hash at two paths → one canonical.
- `document_dedup.py` is a separate review pass (recovery lane) for cases where the file-state lane already ran and an operator wants a re-scan.

### Stage 3 — Skip / Defer (`src/skip/skip_manager.py`)

- Reads `skip_list` from `config/config.yaml`.
- Decision flavors: `skip` (never parse), `defer` (parse later, typically archive members or CAD), `allow`.
- Writes `skip_manifest.json` at export time with reason codes so skips are explainable.
- Guarantees: hashed-but-not-parsed files still appear in state tracking. No silent drops.

### Stage 4 — Parse (`src/parse/dispatcher.py` + `src/parse/parsers/*.py`)

- `dispatcher.py` maps extension → parser module.
- Every parser returns a `ParsedDocument`: `{text, source_path, pages, parser_id, quality, warnings[]}`.
- Notable parsers:
  - `pdf_parser.py` — 4-stage escalation (pypdf → pdfplumber → docling → OCR via Tesseract/Poppler).
  - `image_parser.py` — Tesseract OCR, falls back to EXIF/metadata-only on no-text.
  - `archive_parser.py` — safe unwrap, member-level defer tokens, recursion cap, path traversal guard.
  - `docling_bridge.py` — optional high-quality converter path; off-by-default.
  - `placeholder_parser.py` — "seen but not yet supported" sentinel so formats aren't silently lost.
- `quality_scorer.py` produces a per-doc quality value used by downstream review tools; does not gate embedding.

### Stage 5 — Chunk (`src/chunk/chunker.py`)

- Splits `ParsedDocument.text` into overlapping windows (token-budget aware).
- `chunk_ids.py::make_chunk_id` generates a 64-char SHA-256 hex digest over `f"{norm_path}|{mtime_ns}|{chunk_start}|{chunk_end}|{sha256(text[:2000])}"`, where `norm_path` is lowercased and forward-slash-normalized. Same five inputs → same ID; any edit changes `mtime_ns` (and usually the text fingerprint), forcing re-index of that file.

### Durability Point — `src/export/chunk_checkpoint.py`

Between Stage 5 (chunk) and Stage 7 (embed) the pipeline writes a durable checkpoint:

- On-disk under `<run_output_root>/_checkpoint_active/`:
  - `checkpoint.jsonl` — parsed+chunked records.
  - `state.json` — progress counters.
- Cleared on successful Stage 9.
- Read on restart; files already parsed and chunked are not re-parsed.

This is the fix for the 700GB loss incident — before this point, parse/chunk output only existed in memory until packaging.

### Stage 6 — Enrich (`src/enrichment/contextual_enricher.py`) — optional

- Config-gated (`enrichment.enabled`).
- Adds contextual windows to each chunk; graceful degradation if a chunk fails.

### Stage 7 — Embed (`src/embed/embedder.py` + `src/embed/batch_manager.py`)

- Model: `nomic-embed-text` via sentence-transformers. Dim = 768. Dtype = float16.
- `batch_manager.py` implements token-budget packing; tracked in `project_hybridrag_speed_gems_2026_04.md` (2935 chunks/sec on primary workstation dual-3090).
- OOM backoff: halves batch size and retries; persists across the run.
- Output: `np.ndarray[np.float16]` of shape `[N_chunks, 768]` held via mmap when `embed.mmap = true`.

### Stage 8 — Extract (`src/extract/gliner_extractor.py`) — optional

- Config-gated (`extraction.enabled`).
- GLiNER model; writes `entities.jsonl` with one row per entity per chunk.

### Stage 9 — Export (`src/export/packager.py`)

- Writes to `data/production_output/export_YYYYMMDD_HHMM/`:
  - `chunks.jsonl` — one chunk per line; fields per `FORGE_V2_METADATA_CONTRACT_2026-04-12.md`.
  - `vectors.npy` — fp16, shape `[N,768]`, row-aligned with `chunks.jsonl`.
  - `entities.jsonl` — only when Stage 8 ran.
  - `manifest.json` — run summary (counts, model id, timestamps, status, git SHA).
  - `skip_manifest.json` — all skip/defer decisions with reasons.
- Updates `latest` junction on success.
- Clears `_checkpoint_active` only after all target files are fsynced.

---

## 6. Operator Feedback Path

- `src/gui/stats_panel.py` subscribes to `RunStats` snapshots.
- Background threads never touch Tk widgets directly. All UI mutations go through `src/gui/safe_after.py` — a queue drained on the Tk main loop via `root.after(...)`.
- `src/gui/testing/gui_engine.py` + `src/gui/testing/gui_boot.py` provide a "virtual operator" harness used by `tests/test_gui_button_smash.py` and `tests/test_gui_dedup_only.py`.

---

## 7. V2 Handoff

Out of Forge's scope, but terminates the signal flow:

- `C:\HybridRAG_V2\scripts\stage_forge_import.py` — operator-preferred staging path.
- Reads the export folder, validates against `FORGE_V2_METADATA_CONTRACT_2026-04-12.md`, and loads vectors into V2's LanceDB instance.

Once V2's import completes, the corpus is queryable. That is the "back to query" terminus — an operator ask (kick off a run) has produced a queryable corpus.

---

## 8. Offline Analysis / Audit Lane

Not part of the stage loop, but part of the operator's toolkit:

- `src/analysis/corpus_profiler.py` → `scripts/profile_source_corpus.py` — pre-flight view of the source corpus.
- `src/analysis/export_artifact_analyzer.py` → `scripts/analyze_export_artifacts.py` — post-run structural audit of an export.
- `src/analysis/export_metadata_contract.py` → `scripts/report_export_metadata_contract.py` — contract conformance check vs the V2 metadata contract.
- `scripts/check_export_integrity.py` + `tools/run_critical_e2e_gate.py` — gate tools (PASS/FAIL/BLOCKED) used before promoting an export.

---

## 9. Nightly Delta Lane

A scheduled path that re-uses the same conductor with a reduced source set:

- `scripts/build_delta_manifest.py` — produces the delta file list from the hasher's state store.
- `scripts/nightly_delta_ingest.py` — feeds that list into a normal `Pipeline.run()`.
- `scripts/install_nightly_delta_task.py` + `tools/install_nightly_delta_task.ps1` — Windows scheduled task registration.
- Evidence: `docs/LANE1_NIGHTLY_DELTA_EVIDENCE_2026-04-09.md`, `docs/NIGHTLY_DELTA_OPERATIONS_2026-04-09.md`.

---

## 10. Failure / Resume Cheat Sheet

| Failure point | What on disk | How to recover |
|---|---|---|
| Stop between Stage 5 and Stage 7 | `_checkpoint_active/` present, no export dir, `manifest.json` status = `stopped_before_export` | Rerun with same source + output root — checkpoint-resumes |
| Stop / crash during Stage 7 (embed) | Checkpoint still active; partial embed buffer | Rerun — embedder reads checkpoint, re-embeds only missing chunks |
| Stop during Stage 9 (export write) | Partial export folder; checkpoint retained | Delete partial export dir; rerun |
| Missing OCR tools (Poppler / Tesseract) | Scanned PDFs parse via text-only fallback; image OCR disabled | Fix via `HYBRIDRAG_POPPLER_BIN` / `TESSERACT_CMD`; rerun precheck |
| GPU OOM | Batch manager auto-halves batch; continues | No operator action; check log for "OOM backoff" |
| Config drift | `config/config.yaml` out of sync with GUI | Close GUI before editing by hand; GUI Save writes to `config.yaml` |

---

## 11. File-Level Call Graph (Compressed)

```
start_corpusforge.bat
  └─ launch_gui.py
       └─ app.py :: CorpusForgeApp
            ├─ settings_panel.py       (writes config/config.yaml)
            ├─ stats_panel.py          (reads RunStats)
            ├─ transfer_panel.py       (scripts/run_transfer.py)
            ├─ dedup_only_panel.py     (dedup-only recovery)
            └─ PipelineRunner (thread)
                 └─ scripts/run_pipeline.py
                      └─ scripts/boot.py
                           ├─ src/config/schema.py
                           └─ src/gpu_selector.py
                                └─ src/pipeline.py :: Pipeline.run()
                                     ├─ src/download/hasher.py
                                     ├─ src/download/deduplicator.py
                                     ├─ src/skip/skip_manager.py
                                     ├─ src/parse/dispatcher.py
                                     │    └─ src/parse/parsers/*.py
                                     ├─ src/parse/quality_scorer.py
                                     ├─ src/chunk/chunker.py
                                     ├─ src/export/chunk_checkpoint.py  (write)
                                     ├─ src/enrichment/contextual_enricher.py  (opt)
                                     ├─ src/embed/embedder.py
                                     │    └─ src/embed/batch_manager.py
                                     ├─ src/extract/gliner_extractor.py  (opt)
                                     └─ src/export/packager.py
                                          └─ src/export/chunk_checkpoint.py  (clear)
```

---

## 12. Tests That Exercise This Flow End-To-End

- `tests/test_pipeline_e2e.py` — full 9-stage run with checkpoint/stop/resume coverage.
- `tests/test_pipeline_manifest_stats.py` — manifest + `RunStats` shape.
- `tests/test_run_pipeline_input_list.py` — CLI input list contract.
- `tests/test_gui_button_smash.py` — GUI runner wiring (stop button, stats pump).
- `tests/test_archive_member_defer.py` — parse/skip defer interplay.
- `tests/test_file_state_accounting.py` — skip/defer bookkeeping vs hasher state.

---

Signed: CoPilot+ | CorpusForge | 2026-04-16 MDT
