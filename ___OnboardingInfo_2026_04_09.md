# ___OnboardingInfo_2026_04_09

Convenience onboarding index for this workspace.

If this file conflicts with `C:\HybridRAG_V2\docs\SOURCE_OF_TRUTH_MAP_2026-04-12.md`,
the source-of-truth map wins.

## 2026-04-15 Fast-Start Addendum

If you are onboarding after the V2 QA Workbench / retrieval-readiness push, start here before older sprint notes:

1. `C:\Users\jerem\HYBRIDRAG_LOCAL_ONLY\NEXT_COORDINATOR_HANDOVER_2026-04-15.md`
2. `C:\Users\jerem\HYBRIDRAG_LOCAL_ONLY\DEMO_READINESS_MAP_AND_NEXT_STEPS_2026-04-15.md`
3. `C:\Users\jerem\HYBRIDRAG_LOCAL_ONLY\V2_AND_FORGE_PROMOTION_SPRINT_PLAN_2026-04-15.md`
4. `C:\HybridRAG_V2\docs\FORGE_TO_V2_TYPED_METADATA_MIGRATION_PLAN_2026-04-13.md`
5. `C:\Users\jerem\HYBRIDRAG_LOCAL_ONLY\SEMI_STRUCTURED_IMPLEMENTATION_PLAN_2026-04-15.md`

Current reality:

- V2 now has a real QA Workbench and live benchmark surfaces
- the next clean Forge work is narrow promotion slices, not bulk dirty-tree pushes
- highest-ROI Forge work is typed metadata carry-back and semi-structured/table metadata
- V2 ingest/schema must be ready before the first Forge re-export carrying new typed metadata

## Repos

- CorpusForge: `C:\CorpusForge`
- HybridRAG V2: `C:\HybridRAG_V2`

## Important

- The real repos are in the `C:\` drive root.
- Any `C:\Users\jerem\codex_tmp\...` repo copy is a study or recovery clone, not a canonical implementation root.
- `docs/SPRINT_SYNC.md` is a planning board, not the canonical readiness or operator truth source.
- The preferred Forge -> V2 operator handoff now uses `scripts/stage_forge_import.py`.
- `scripts/import_embedengine.py` is still the underlying import engine, but it is no longer the preferred first-line operator entrypoint.
- The single active Forge runtime config is `C:\CorpusForge\config\config.yaml`.
- Direct repo-local probes win for counts when docs disagree.
- Repo-local `.venv` is required for QA and local validation.

## Read These First

1. `C:\HybridRAG_V2\docs\SOURCE_OF_TRUTH_MAP_2026-04-12.md`
2. `C:\HybridRAG_V2\docs\RESEARCH_STANDING_ORDERS.md`
3. `C:\HybridRAG_V2\docs\AUTHORITATIVE_FACTS_AND_SOURCES_2026-04-12.md`
4. `C:\HybridRAG_V2\docs\V2_DEMO_READINESS_GAP_ANALYSIS_2026-04-12.md`
5. `C:\HybridRAG_V2\docs\MAY2_CANONICAL_DEMO_PACKET_2026-04-12.md`
6. `C:\HybridRAG_V2\docs\LANE3_OPERATOR_INSTALLER_PREFLIGHT_EVIDENCE_2026-04-13.md` for current workstation OCR/install/preflight truth
7. `C:\HybridRAG_V2\docs\SPRINT_SLICE_PRODUCT_COMPLETION_2026-04-13.md`
8. `C:\HybridRAG_V2\docs\SPRINT_SLICE_EVAL_GUI_2026-04-13.md` if your lane touches the eval GUI
9. `C:\CorpusForge\docs\OPERATOR_QUICKSTART.md`
10. `C:\CorpusForge\config\config.yaml`

## Current High-Signal Truths

- Current clean Forge export: `C:\CorpusForge\data\production_output\export_20260409_0720`
- Preferred V2 intake path: `C:\HybridRAG_V2\scripts\stage_forge_import.py`
- Underlying V2 import engine: `C:\HybridRAG_V2\scripts\import_embedengine.py`
- Do not assume `config.local.yaml` is part of the live runtime path anymore.
- GUI Save Settings writes to `config/config.yaml`.
- Hash persistence and resume keep interrupted files as `hashed` in the state DB instead of RAM-only state.
- On this machine, Tesseract exists at `C:\Program Files\Tesseract-OCR\tesseract.exe` but may not be on PATH.
- On this machine, Poppler / `pdftoppm.exe` is not currently discoverable, so scanned-PDF OCR remains partial until fixed.

## CorpusForge Reference Files

- Pipeline orchestration: `C:\CorpusForge\src\pipeline.py`
- GUI launch and wiring: `C:\CorpusForge\src\gui\launch_gui.py`
- Main GUI app: `C:\CorpusForge\src\gui\app.py`
- GUI stats and progress: `C:\CorpusForge\src\gui\stats_panel.py`
- Config loading and schema: `C:\CorpusForge\src\config\schema.py`
- Skip and defer rules: `C:\CorpusForge\src\skip\skip_manager.py`
- Parser dispatch: `C:\CorpusForge\src\parse\dispatcher.py`
- Archive leak fix area: `C:\CorpusForge\src\parse\parsers\archive_parser.py`
- Hash and dedup state: `C:\CorpusForge\src\download\hasher.py`, `C:\CorpusForge\src\download\deduplicator.py`
- Precheck tool: `C:\CorpusForge\tools\precheck_workstation_large_ingest.py`
- Export inspection tool: `C:\CorpusForge\tools\inspect_export_quality.py`

## HybridRAG V2 Reference Files

- Staging intake path: `C:\HybridRAG_V2\scripts\stage_forge_import.py`
- Import engine: `C:\HybridRAG_V2\scripts\import_embedengine.py`
- Import and extract GUI: `C:\HybridRAG_V2\scripts\import_extract_gui.py`
- GUI launcher wrapper: `C:\HybridRAG_V2\RUN_IMPORT_AND_EXTRACT_GUI.bat`
- Production eval runner: `C:\HybridRAG_V2\scripts\run_production_eval.py`
- Tiered extraction runner: `C:\HybridRAG_V2\scripts\tiered_extract.py`
- Query pipeline: `C:\HybridRAG_V2\src\query\pipeline.py`
- Query router: `C:\HybridRAG_V2\src\query\query_router.py`
- Vector retriever: `C:\HybridRAG_V2\src\query\vector_retriever.py`
- Store access: `C:\HybridRAG_V2\src\store\lance_store.py`

## Operator And Runtime Docs Most Likely To Matter

- `C:\HybridRAG_V2\docs\V2_STAGING_IMPORT_RUNBOOK_2026-04-09.md`
- `C:\CorpusForge\docs\OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md`
- `C:\CorpusForge\docs\MORNING_OPERATOR_QUICKSTART_2026-04-09.md`
- `C:\CorpusForge\docs\SOURCE_TO_V2_ASSEMBLY_LINE_GUIDE_2026-04-08.md`

## Known Open Items Already On Record

- `pipeline.py` provenance and mixed-delta cleanup
- legacy `.ppt` garbage handling
- older Forge 6.1-6.5 QA gate

Do not rediscover these from scratch unless your lane directly touches them.

## Before Coding

- run `git status --short` in the repo you own
- preserve unrelated user changes
- prefer `rg` for search
- if you touch tracked docs or scripts, run the repo sanitizer before signoff:
  - `C:\CorpusForge\sanitize_before_push.py`
  - `C:\HybridRAG_V2\sanitize_before_push.py`

## Prior Art

- Check HybridRAG3 or V1 first for admin-tab UX, toggle patterns, scheduling hooks, telemetry, and operator-facing controls before inventing a fresh pattern.
