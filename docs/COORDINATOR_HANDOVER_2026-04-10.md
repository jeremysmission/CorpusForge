# Coordinator Handover — 2026-04-10

> WARNING: Historical cross-repo handover. Useful context, but not the current source of truth for readiness, recovery, or operator posture.
> Start instead with `C:\HybridRAG_V2\docs\SOURCE_OF_TRUTH_MAP_2026-04-12.md` and `C:\HybridRAG_V2\docs\REBOOT_HANDOVER_2026-04-13.md`.

Purpose: preserve the cross-repo state before reset, separate durable work from local-only work, and define the next clean 4-lane split.

## Repo anchors

- CorpusForge: `C:\CorpusForge`
- HybridRAG V2: `C:\HybridRAG_V2`
- CorpusForge onboarding: `C:\CorpusForge\___OnboardingInfo_2026_04_09.md`
- HybridRAG V2 onboarding: `C:\HybridRAG_V2\___OnboardingInfo_2026_04_09.md`

## Current durable state

Already pushed:

- CorpusForge `origin/master`: `6acf55c` — Lane 4 corpus adaptation evidence packet
- HybridRAG V2 `origin/master`: `82bf51b` — Lane 4 family-aware routing packet
- Clean canonical Forge export from Sprint 6.6: `C:\CorpusForge\data\production_output\export_20260409_0720`
- Run 6 archive-member defer fix proved at production scale: zero `*.SAO.zip` / `*.RSF.zip` leak in the export
- V2 import-side fallback filter exists, is explicit, and is no longer needed for Run 6
- PII toggle / outbound scrub work previously passed QA

## Yesterday / overnight work completed

1. Forge 6.6 was hardened from a non-canonical Run 5 into a clean Run 6 export.
2. Archive-member defer was fixed in Forge and regression-tested.
3. Adaptation analysis was documented and landed:
   - `C:\CorpusForge\docs\CORPUS_ADAPTATION_EVIDENCE_2026-04-09.md`
   - `C:\HybridRAG_V2\docs\FAMILY_AWARE_QUERY_ROUTING_PLAN_2026-04-09.md`
4. Retroactive changelog work landed in both repos.
5. Single-runtime-config direction was established in mainline docs: live path is `config/config.yaml`, not `config.local.yaml`.

## Local repo-safe work still pending push

CorpusForge local dirty set includes:

- nightly delta scheduling / mirror / canary path
  - `scripts/run_nightly_delta.py`
  - `scripts/install_nightly_delta_task.py`
  - `src/download/delta_tracker.py`
  - `tests/test_nightly_delta.py`
  - `docs/NIGHTLY_DELTA_OPERATIONS_2026-04-09.md`
  - evidence: `docs/LANE1_NIGHTLY_DELTA_EVIDENCE_2026-04-09.md`
- skip/defer hardening + proof artifacts
  - `src/skip/skip_manager.py`
  - `tests/test_skip_manager.py`
  - `docs/SKIP_DEFER_HARDENING_2026-04-09.md`
  - `docs/LANE2_CLOSEOUT_2026-04-09.md`
- GUI / pipeline / telemetry work still sitting locally
  - `src/gui/app.py`
  - `src/gui/launch_gui.py`
  - `src/gui/stats_panel.py`
  - `src/pipeline.py`
  - `tests/test_gui_button_smash.py`
  - `tests/test_gui_dedup_only.py`
  - `tests/test_pipeline_e2e.py`
- operator / setup / config docs refresh
  - `docs/OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md`
  - `docs/SOURCE_TO_V2_ASSEMBLY_LINE_GUIDE_2026-04-08.md`
  - `docs/WORKSTATION_SETUP_2026-04-06.md`
  - `docs/SPRINT_SYNC.md`

HybridRAG V2 local dirty set includes:

- staging / import orchestration
  - `scripts/stage_forge_import.py`
  - `tests/test_stage_forge_import.py`
  - `docs/V2_STAGING_IMPORT_RUNBOOK_2026-04-09.md`
- operator-surface and docs refresh
  - `docs/OPERATOR_SURFACE_QA_2026-04-08.md`
  - `docs/SPRINT_SYNC.md`
  - `scripts/import_embedengine.py`
  - `scripts/overnight_extraction.py`

## Local-only items that must NOT be pushed

- personal GPU benchmark lane:
  - `{USER_HOME}\overnight_gpu\lane2\`
- private manual:
  - `{USER_HOME}\Corpus_Adaptation_Manual_2026-04-09.md`
- sample profile artifacts:
  - `{USER_HOME}\Corpus_Profile_Sample_2026-04-09.md`
  - `{USER_HOME}\Corpus_Profile_Sample_2026-04-09.json`

Rule: no personal multi-GPU guidance belongs in remote work materials.

## Known open issues still on record

- `src/pipeline.py` provenance / mixed-delta cleanup
- legacy `.ppt` parser garbage
- Forge 6.1-6.5 QA gate history
- need a true end-to-end operator QA lane that checks the full line, not only narrow slices
- config/doc cleanup is still incomplete because many historical docs still describe older flows

## Clean lane split for the next 4-agent cycle

Use numeric lane names only from this point forward. Older closeout docs may reflect an earlier numbering pass; do not reuse those names for new assignments.

### Lane 1 — Forge Automation

Mission:
- finish nightly delta operations as a durable operator feature
- add an operator-visible admin surface or GUI entry point for precheck / scheduler status
- validate scheduled delta -> mirror -> Forge pipeline -> export handoff

Deliverables:
- scheduler install/update path
- operator-facing runbook
- proof artifacts from one plan run and one delta run

### Lane 2 — Forge Reliability

Mission:
- make stop/pause/resume/operator messaging fully honest
- make hash-only skip/defer behavior explicit for `.jpg`, `.sao`, `.rsf`, and similar low-value families
- turn hardcoded thresholds into config where operator tuning matters

Deliverables:
- code + tests
- one end-to-end recovery proof
- GUI harness and non-author button smash requirements written into the QA packet

### Lane 3 — V2 Import / Retrieval Quality

Mission:
- harden the staging/import path
- convert the family-aware routing plan into the smallest safe runtime improvements
- prep for the 400-question corpus / eval set when provided

Deliverables:
- import/staging artifacts
- retrieval/routing evidence
- explicit QA packet for operator-visible behavior

### Lane 4 — Docs / Ops / QA Infrastructure

Mission:
- finish the config and GUI reference guides with code pointers
- keep sanitizer parity and purge stale/confusing config guidance
- define a light revisioning/changelog rule and apply it consistently

Deliverables:
- one config reference
- one GUI/operator reference
- one revision/changelog policy note
- sprint board cleanup

### QA lane

Required checks:
- findings-first review
- full GUI harness when GUI is touched
- non-author button smash for operator-facing changes
- one real end-to-end path: source -> dedup -> parse/chunk -> export -> V2 stage/import

## First files to open after reset

1. `C:\HybridRAG_V2\docs\SOURCE_OF_TRUTH_MAP_2026-04-12.md`
2. `C:\HybridRAG_V2\docs\REBOOT_HANDOVER_2026-04-13.md`
3. `C:\HybridRAG_V2\docs\COORDINATOR_CONTINUITY_NOTES_2026-04-13.md`
4. `C:\CorpusForge\docs\HANDOVER_2026-04-09.md`
5. `C:\CorpusForge\___OnboardingInfo_2026_04_09.md`

Signed: CoPilot+ | Coordinator | 2026-04-10 MDT
