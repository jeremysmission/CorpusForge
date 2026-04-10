# Lane 3 Handoff / Evidence Note - 2026-04-09

Repo: `C:\CorpusForge`

Branch: `master`

Landing result:

- committed: `0d7c5ab` (`docs: add Forge config and GUI reference`)
- pushed: `origin/master`

Task: exhaustive GUI/YAML/operator reference cleanup for Forge.

Files changed:

- `C:\CorpusForge\docs\CONFIG_AND_GUI_REFERENCE_2026-04-09.md`
- `C:\CorpusForge\docs\LANE3_CONFIG_GUI_REFERENCE_HANDOFF_2026-04-09.md`

Exact commands run:

```powershell
git -C C:\CorpusForge status --short
git -C C:\CorpusForge branch --show-current
Get-Content C:\CorpusForge\docs\SOURCE_TO_V2_ASSEMBLY_LINE_GUIDE_2026-04-08.md -TotalCount 260
Get-Content C:\CorpusForge\docs\OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md -TotalCount 320
Get-Content C:\CorpusForge\src\config\schema.py -TotalCount 420
Get-Content C:\CorpusForge\src\gui\app.py -TotalCount 520
Get-Content C:\CorpusForge\src\gui\launch_gui.py -TotalCount 760
Get-Content C:\HybridRAG_V2\src\config\schema.py -TotalCount 360
Get-Content C:\CorpusForge\src\gui\settings_panel.py -TotalCount 420
Get-Content C:\CorpusForge\config\config.yaml -TotalCount 340
Get-Content C:\CorpusForge\docs\HANDOVER_PARALLEL_RECOVERY_2026-04-09.md -TotalCount 260
Get-Content C:\CorpusForge\docs\SPRINT_SYNC.md -TotalCount 420
rg -n "full_reindex|docling_mode|defer_extensions|embed_batch_size|state_db|output_dir|source_dirs|nightly_delta|task_start_time|task_name|transfer_workers|ocr_mode|workers" C:\CorpusForge\src C:\CorpusForge\scripts C:\CorpusForge\tools
rg -n "gpu_index|embed_batch_size|apply_gpu_selection|CUDA_VISIBLE_DEVICES|HYBRIDRAG_OCR_MODE|HYBRIDRAG_DOCLING_MODE|HYBRIDRAG_POPPLER_BIN|TESSERACT_CMD" C:\CorpusForge\src C:\CorpusForge\scripts C:\CorpusForge\tools
rg -n "HYBRIDRAG_EMBED_BATCH|embed_batch_size" C:\CorpusForge
python C:\CorpusForge\scripts\boot.py --config C:\CorpusForge\config\config.yaml
python C:\CorpusForge\sanitize_before_push.py
git -C C:\CorpusForge add docs/CONFIG_AND_GUI_REFERENCE_2026-04-09.md docs/LANE3_CONFIG_GUI_REFERENCE_HANDOFF_2026-04-09.md
git -C C:\CorpusForge commit -m "docs: add Forge config and GUI reference"
git -C C:\CorpusForge push origin master
```

Verification / tests run:

- `python C:\CorpusForge\scripts\boot.py --config C:\CorpusForge\config\config.yaml`
  - result: PASS; live config loaded and printed expected chunk/embed/parse/state values
- `python C:\CorpusForge\sanitize_before_push.py`
  - result: repo-level dry-run returned nonzero because unrelated existing files were still flagged:
    - `docs/CORPUS_ADAPTATION_EVIDENCE_2026-04-09.md`
    - `docs/LANE4_HANDOFF_2026-04-09.md`
  - lane impact: the new Lane 3 docs were not listed by the sanitizer

Artifacts / output paths:

- `C:\CorpusForge\docs\CONFIG_AND_GUI_REFERENCE_2026-04-09.md`
- `C:\CorpusForge\docs\LANE3_CONFIG_GUI_REFERENCE_HANDOFF_2026-04-09.md`

Current status: `READY FOR QA`

Remaining risks / blockers:

1. `hardware.embed_batch_size` is exposed in GUI/YAML/precheck, but the live embedder still reads `HYBRIDRAG_EMBED_BATCH` directly in `src/embed/embedder.py`.
2. `hardware.gpu_index` exists in the schema, but the launcher currently auto-picks the least-used GPU with `apply_gpu_selection()` instead of honoring that field directly.
3. The main GUI `Source` and `Output` widgets still start from hardcoded `data/source` and `data/output` defaults instead of preloading the active config values.

Next step for QA:

1. Read `C:\CorpusForge\docs\CONFIG_AND_GUI_REFERENCE_2026-04-09.md`.
2. Spot-check the code anchors against:
   - `C:\CorpusForge\src\config\schema.py`
   - `C:\CorpusForge\src\gui\app.py`
   - `C:\CorpusForge\src\gui\settings_panel.py`
   - `C:\CorpusForge\src\gui\launch_gui.py`
   - `C:\CorpusForge\src\embed\embedder.py`
3. Verify the documented runtime caveats are truthful and not overstated.

Crash-safety note:

- This lane is no longer local-only.
- The reference and handoff note are committed and pushed in `0d7c5ab`.

Signed: Agent 4 | Lane 3
