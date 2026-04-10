# Parallel Recovery Handover — 2026-04-09

Purpose: if the session or machine dies, this file is the quickest way to recover the current overnight plan without rebuilding context from scratch.

## Repo anchors

- CorpusForge repo: `C:\CorpusForge`
- HybridRAG V2 repo: `C:\HybridRAG_V2`
- CorpusForge onboarding: `C:\CorpusForge\___OnboardingInfo_2026_04_09.md`
- HybridRAG V2 onboarding: `C:\HybridRAG_V2\___OnboardingInfo_2026_04_09.md`

## Current high-signal state

- Clean Forge export is still `C:\CorpusForge\data\production_output\export_20260409_0720`
- Current basic V2 import path is `C:\HybridRAG_V2\scripts\import_embedengine.py`
- Active Forge runtime config is now `C:\CorpusForge\config\config.yaml`
- `config.local.yaml` is retired from the live runtime path
- GUI Save Settings now writes to `config/config.yaml`
- Resume/hash persistence was recently fixed so interrupted work files persist as `hashed` in the SQLite state DB instead of living only in RAM
- Latest pushed CorpusForge commit before this note: `734b98b`
- Latest pushed HybridRAG V2 commit before this note: `592f64f`

## Active parallel lanes

### Lane 1 — CorpusForge nightly delta scheduling + canary ops

Worker nickname: `Tesla`

Mission:
- detect new/changed files on the source drive
- copy only delta locally
- run the existing Forge pipeline on that delta
- add canary-ready proof/testing
- produce a scheduler/task install path and runbook

Scope:
- `C:\CorpusForge\config\config.yaml`
- `C:\CorpusForge\src\config\schema.py`
- `C:\CorpusForge\scripts\run_transfer.py` if needed
- `C:\CorpusForge\scripts\nightly_delta_ingest.py`
- `C:\CorpusForge\scripts\build_delta_manifest.py`
- `C:\CorpusForge\tools\install_nightly_delta_task.ps1`
- `C:\CorpusForge\docs\NIGHTLY_DELTA_OPERATIONS_2026-04-09.md`
- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- tests for this lane

Status at handover:
- worker acknowledged dirty repo and was told to keep this lane narrow
- allowed to read V1 prior art for scheduler/admin patterns
- should not drift into GUI telemetry or V2 runtime work

### Lane 2 — CorpusForge GUI control + live telemetry

Worker nickname: `Anscombe`

Mission:
- improve stop/pause behavior
- add live chunk count + chunks/sec
- keep operator-visible stage/status honest
- run GUI harness and button-smash coverage

Scope:
- `C:\CorpusForge\src\gui\app.py`
- `C:\CorpusForge\src\gui\stats_panel.py`
- `C:\CorpusForge\src\gui\launch_gui.py`
- `C:\CorpusForge\src\pipeline.py`
- `C:\CorpusForge\tests\test_gui_button_smash.py`
- `C:\CorpusForge\tests\test_gui_dedup_only.py`
- `C:\CorpusForge\tests\test_pipeline_e2e.py`
- `C:\CorpusForge\docs\SPRINT_SYNC.md`

Latest QA status for the immediately previous GUI/config/resume lane:
- single active runtime config: PASS
- crash/process-exit hash persistence: PASS
- full GUI/operator signoff: NOT YET

Outstanding blocker from QA:
1. `Stop Pipeline` is not a real live stop yet. GUI runner stop flag does not currently interrupt the active pipeline path.
2. Button-smash suite still excludes the Stop control, so this regression is not covered.

Required next step:
- wire a real cooperative stop signal into `Pipeline.run()`
- add Stop coverage to GUI harness/button-smash

### Lane 3 — HybridRAG V2 staging/import ops

Worker nickname: `Hooke`

Mission:
- make nightly Forge handoff cleaner on the V2 side
- keep imports/staging explicit and operator-visible
- add durable reporting artifacts
- make canary validation easy

Scope:
- `C:\HybridRAG_V2\scripts\import_embedengine.py`
- helper scripts under `C:\HybridRAG_V2\scripts\`
- `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`
- short runbook doc under `C:\HybridRAG_V2\docs\`
- tests if needed

Constraints:
- no CorpusForge runtime changes
- no hidden filters or hidden latest-export behavior

### Lane 4 — docs, sprints, sanitizer, golden/canary test plan

Worker nickname: `Singer`

Mission:
- remove the old workstation nickname from remote-bound technical docs
- harden banned-word hygiene if needed
- add tonight's work into sprint slices/boards
- create a better golden-production-data + canary test plan
- add a concise operator note that low GPU during parse is generally expected

Scope:
- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`
- `C:\CorpusForge\docs\HANDOVER_2026-04-09.md`
- theory-of-operations docs in both repos
- sanitizer scripts only if there is a real gap
- new golden/canary plan doc under `C:\CorpusForge\docs\`

## QA plan

- QA1 should pick up whichever lane posts `Ready for QA` first
- Priority order:
  1. Lane 2 GUI control/telemetry
  2. Lane 1 nightly delta scheduler
  3. Lane 3 V2 staging/import
  4. Lane 4 docs/sanitizer/golden-plan
- QA2 only needs to activate if two substantial lanes finish close together

## Important recent fix already landed

The single-config + crash persistence batch is already in mainline:

- commit: `734b98b`
- summary:
  - active runtime config is `config/config.yaml`
  - no live `config.local.yaml` path
  - dedup now persists work-file hashes as `hashed` before full export success
  - interrupted runs no longer lose all hash progress

Core files from that batch:
- `C:\CorpusForge\src\download\deduplicator.py`
- `C:\CorpusForge\src\config\schema.py`
- `C:\CorpusForge\src\parse\dispatcher.py`
- `C:\CorpusForge\src\skip\skip_manager.py`
- `C:\CorpusForge\src\gui\launch_gui.py`

## Operator facts worth preserving

- During parse, low GPU usage is usually expected because parse is mostly CPU, disk, decompression, OCR, and parser bound
- GPU should matter more during embedding than during discovery/parse
- The 700GB operator docs now point at `config/config.yaml`, not `config.local.yaml`

## If recovery is needed

1. Open the onboarding file in either repo root.
2. Open this file.
3. Reopen:
   - `C:\CorpusForge\docs\SPRINT_SYNC.md`
   - `C:\CorpusForge\docs\HANDOVER_2026-04-09.md`
   - `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`
4. Resume lane work from the scopes above instead of rediscovering context.
