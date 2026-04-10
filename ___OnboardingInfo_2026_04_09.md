# ___OnboardingInfo_2026_04_09

Quick onboarding for this workspace

Repos:
- CorpusForge: `C:\CorpusForge`
- HybridRAG V2: `C:\HybridRAG_V2`

Important:
- The real repos are in the `C:\` drive root.
- Legacy V1 / HybridRAG3 can be useful for repurposing tech, especially prior GUI/admin-tab patterns, scheduling, filters/toggles, telemetry, and operator UX. If you need a prior-art pattern, check V1 before inventing a new one.

Read these first, in order:
1. `C:\CorpusForge\docs\SPRINT_SYNC.md`
2. `C:\CorpusForge\docs\HANDOVER_2026-04-09.md`
3. `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`
4. `C:\CorpusForge\docs\OPERATOR_QUICKSTART.md`
5. `C:\CorpusForge\config\config.yaml`

Current high-signal truths:
- Current clean Forge export: `C:\CorpusForge\data\production_output\export_20260409_0720`
- Current morning/basic V2 import path: `C:\HybridRAG_V2\scripts\import_embedengine.py`
- Single active Forge runtime config is now: `C:\CorpusForge\config\config.yaml`
- Do not assume `config.local.yaml` is part of the live runtime path anymore.
- GUI Save Settings now writes to `config/config.yaml`.
- Hash persistence/resume was recently changed: interrupted work files now persist as `hashed` in the state DB instead of living only in RAM.

If you are working in CorpusForge, the main reference files are:
- Pipeline orchestration: `C:\CorpusForge\src\pipeline.py`
- GUI launch/wiring: `C:\CorpusForge\src\gui\launch_gui.py`
- Main GUI app: `C:\CorpusForge\src\gui\app.py`
- GUI stats/progress: `C:\CorpusForge\src\gui\stats_panel.py`
- Config loading/schema: `C:\CorpusForge\src\config\schema.py`
- Skip/defer rules: `C:\CorpusForge\src\skip\skip_manager.py`
- Parser dispatch: `C:\CorpusForge\src\parse\dispatcher.py`
- Archive leak fix area: `C:\CorpusForge\src\parse\parsers\archive_parser.py`
- Hash/dedup state: `C:\CorpusForge\src\download\hasher.py` and `C:\CorpusForge\src\download\deduplicator.py`
- Precheck tool: `C:\CorpusForge\tools\precheck_workstation_large_ingest.py`
- Export inspection tool: `C:\CorpusForge\tools\inspect_export_quality.py`

If you are working in HybridRAG V2, the main reference files are:
- Sprint board: `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`
- Import path: `C:\HybridRAG_V2\scripts\import_embedengine.py`
- Current web/demo query surface: `C:\HybridRAG_V2\scripts\demo_web_server.py`
- PII scrubber: `C:\HybridRAG_V2\scripts\pii_scrubber.py`

Operator/runtime docs most likely to matter:
- `C:\CorpusForge\docs\OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md`
- `C:\CorpusForge\docs\SOURCE_TO_V2_ASSEMBLY_LINE_GUIDE_2026-04-08.md`
- `C:\CorpusForge\docs\WORKSTATION_SETUP_2026-04-06.md`

Known open items already on record:
- `pipeline.py` provenance / mixed-delta cleanup
- legacy `.ppt` garbage handling
- older Forge 6.1-6.5 QA gate

Do not rediscover these from scratch unless your lane directly touches them.

Before coding:
- run `git status --short` in the repo you own
- preserve unrelated user changes
- prefer `rg` for search
- if you touch tracked docs/scripts, run the repo sanitizer before signoff:
  - `C:\CorpusForge\sanitize_before_push.py`
  - `C:\HybridRAG_V2\sanitize_before_push.py`

If you need prior art from V1:
- look there first for admin-tab UX, toggle patterns, scheduling hooks, and operator-facing controls before building fresh from nothing.
