# Nightly Delta / Scheduler / Admin Plan 2026-04-10

Purpose: turn the current nightly-delta operator story into a concrete, testable implementation plan for unattended Forge-to-V2 handoff.

Scope: docs/design lane only. This packet does not change runtime behavior.

## Status

This plan is `READY FOR QA` as a design artifact.

It is grounded in current mainline code, current V2 staging/import behavior, and V1 prior art for operator visibility and interlocks.

## What Is Already Proven

### Forge-side nightly delta building blocks

Current proven code paths:

- `scripts/run_nightly_delta.py`
  - authoritative nightly runner
  - scans source root
  - mirrors only delta files
  - writes scan/transfer/report artifacts
  - runs the normal `Pipeline.run()` on the mirrored subset
  - preserves original source provenance through `source_path_mapper`
- `src/download/delta_tracker.py`
  - durable source-side state in SQLite
  - `hashed` means admitted to delta set but not fully mirrored yet
  - `mirrored` means already copied and safe to skip next scan unless changed
- `scripts/install_nightly_delta_task.py`
  - emits or installs the Windows Task Scheduler task from config
- `src/config/schema.py`
  - active `nightly_delta` config surface already exists:
    - `source_root`
    - `mirror_root`
    - `transfer_state_db`
    - `manifest_dir`
    - `pipeline_output_dir`
    - `pipeline_state_db`
    - `pipeline_log_dir`
    - `stop_file`
    - `canary_globs`
    - `require_canary`
    - `task_name`
    - `task_start_time`
- `tests/test_nightly_delta.py`
  - proves canary accounting
  - proves `hashed` -> `mirrored` reuse
  - proves original source paths survive export
  - proves replay behavior of `2 delta -> 0 delta -> 1 changed`

### V2-side morning handoff building blocks

Current proven code paths:

- `scripts/stage_forge_import.py`
  - deterministic export selection
  - preflight artifact
  - canary export subset
  - delta-validation artifact
  - planned import command
  - durable stage ledger
- `scripts/import_embedengine.py`
  - actual import execution path
  - dry-run and import report artifacts
- `docs/V2_STAGING_IMPORT_RUNBOOK_2026-04-09.md`
  - explicit operator sequence for plan -> canary dry-run -> import
- `tests/test_stage_forge_import.py`
  - proves canary export subset and manifest generation

## What Is Not Solved Yet

The missing piece is not a new pipeline.

The missing piece is one operator-facing contract that ties together:

1. scheduler trigger
2. stop-file semantics
3. latest nightly artifacts
4. GUI visibility
5. morning V2 validation and import

Right now the parts exist, but the operator has to know which script or artifact to inspect at each step.

## End-to-End Nightly Design

### Ownership boundary

Forge owns:

1. source delta detection
2. local mirror/copy
3. dedup
4. parse
5. chunk
6. embed
7. export package creation
8. stop-file handling during the nightly run

V2 owns:

1. deterministic export selection
2. preflight validation
3. canary dry-run
4. import execution
5. import-side artifact trail
6. morning validation and signoff

This split is important because it avoids overlap with:

- the existing durability work inside `Pipeline.run()`
- retrieval-side metadata and config ownership

### Recommended nightly flow

1. Windows Task Scheduler launches `scripts/run_nightly_delta.py` with the active `config/config.yaml`.
2. Forge scans `nightly_delta.source_root` using `NightlyDeltaTracker`.
3. Only delta files are mirrored into `nightly_delta.mirror_root`.
4. Forge writes:
   - `nightly_delta_scan_<ts>.json`
   - `nightly_delta_transfer_<ts>.json`
   - `nightly_delta_input_<ts>.txt`
   - `nightly_delta_report_<ts>.json`
   - log file under `logs/nightly_delta/`
5. Forge runs the normal pipeline on the mirrored subset, not a second bespoke pipeline.
6. Forge writes the normal export package under `nightly_delta.pipeline_output_dir`.
7. Morning operator runs the V2 stage/import flow against that export:
   - `plan`
   - `dry-run` canary
   - `import`

### Why this is the right shape

- the source-side delta state is already durable
- the pipeline stop semantics are already cooperative
- V2 already has the correct operator artifact model
- the plan only needs to join the pieces, not reinvent them

## Scheduler Trigger And Stop-File Behavior

### Scheduler

Keep one explicit scheduler entry only:

- emitted or installed by `scripts/install_nightly_delta_task.py`
- task name comes from `nightly_delta.task_name`
- start time comes from `nightly_delta.task_start_time`
- command path stays visible in the emitted XML

Do not add alternate launch paths for the same job.

The operator should be able to answer:

1. what task runs nightly
2. what config file it uses
3. what script it launches
4. where the run writes artifacts

### Stop file

Current behavior in `scripts/run_nightly_delta.py` is already the correct design basis:

- `StopController` watches signals and `nightly_delta.stop_file`
- stop is cooperative
- stop is checked:
  - during source scan
  - during mirror copy
  - at the Forge pipeline boundary
  - inside `Pipeline.run()` through `should_stop`

Recommended operator contract:

- `Stop Safely` means: request stop, finish the current safe unit, write state, exit cleanly
- `Pause` should not be a second implementation with different semantics
- for this lane, `Pause` should be treated as the same thing as `Stop Safely`
- `Resume` means rerun the same nightly command against the same:
  - `transfer_state_db`
  - `mirror_root`
  - `pipeline_state_db`
  - output root

### Proven vs planned semantics

Proven now:

- source-side delta resume via `hashed` / `mirrored`
- transfer stop via `BulkSyncer.should_stop`
- pipeline cooperative stop via `Pipeline.run(... should_stop=...)`

Do not overclaim yet:

- true mid-file pause
- arbitrary in-memory resume without rerun
- GUI-managed resume state separate from the runner artifacts

## Admin Panel / GUI Plan

### Do not convert Forge GUI into a notebook

Current Forge GUI is a vertically stacked section layout in `src/gui/app.py`, not a tabbed admin shell.

That matters.

The low-risk implementation is:

- add one more labeled section or thin panel into the existing layout
- add one more runner class in `src/gui/launch_gui.py`
- keep all state in the nightly runner artifacts

Do not spend this slice converting the Forge GUI into a notebook or a multi-view shell.

### Recommended Forge GUI surface

Add a new `Nightly Delta` section in `src/gui/app.py`.

Suggested file ownership for the GUI slice:

- `src/gui/app.py`
- new `src/gui/nightly_delta_panel.py`
- `src/gui/launch_gui.py`

Recommended controls:

- `Run Nightly Now`
- `Scan Only`
- `Transfer Only`
- `Chunk-Only Proof`
- `Stop Safely`
- `Resume Last`
- `Open Latest Report`
- `Open Latest Export`
- `Open V2 Stage Runbook`

Recommended visible fields:

- source root
- mirror root
- transfer state DB
- stop file path
- scheduler task name
- scheduler start time
- latest scan totals:
  - total
  - delta
  - new
  - changed
  - resumed hashed
  - deleted
  - canary matches
- latest transfer totals:
  - copied
  - skipped
  - failed
  - stop requested
- latest pipeline totals:
  - parsed
  - skipped
  - failed
  - chunks created
  - export dir
- latest V2 handoff hint:
  - recommended command
  - last known staged export path if available

### Recommended GUI behavior

The panel should shell out to `scripts/run_nightly_delta.py` instead of re-implementing runner logic in Tkinter.

Reason:

- scheduler and GUI must share one command path
- stop-file semantics stay identical
- artifact layout stays identical
- the GUI remains a control surface, not a second orchestrator

Concrete behavior:

- `Run Nightly Now` starts a subprocess for `scripts/run_nightly_delta.py`
- `Stop Safely` creates the configured sentinel file and updates the UI to `Stopping...`
- `Resume Last` deletes the stale stop file if present, then reruns the same command with the same config
- the panel polls the latest report/log/artifact files for status text

### Interlocks

Reuse V1-style interlock thinking, not V1 automation.

Do:

- disable Nightly Delta start while a manual Forge pipeline run is active
- disable manual Forge pipeline start while Nightly Delta is active on the same mirror/output scope
- show the reason in plain operator text

Do not:

- auto-chain hidden operations in the GUI
- hide competing runs behind optimistic status labels

## V1 Prior Art To Reuse

Use these patterns, not their full architecture.

### Good prior art

- `C:\HybridRAG3_Educational\src\gui\panels\panel_registry.py`
  - stable panel registration and one clear admin surface
- `C:\HybridRAG3_Educational\src\gui\panels\api_admin_tab.py`
  - scrollable, section-based admin view with explicit save points
- `C:\HybridRAG3_Educational\src\gui\panels\data_panel.py`
  - operator-visible status fields such as run ID, stop acknowledgment, and last manifest reason
- `C:\HybridRAG3_Educational\src\gui\panels\index_panel.py`
  - disabled-state reason text instead of silent graying out
- `C:\HybridRAG3_Educational\tests\test_transfer_index_interlock.py`
  - transfer/index interlock tests that keep concurrent operator actions honest

### Prior art to avoid

- `C:\HybridRAG3_Educational\tools\monitor_and_reindex.py`
  - old watcher style that auto-triggers the next step with weak artifact visibility

Use the visibility patterns, not the hidden automation pattern.

## Morning Validation Flow

The morning operator flow should stay explicit and artifact-backed.

### Step 1: Verify the nightly handoff

Check the latest Forge artifacts:

- latest `nightly_delta_report_*.json`
- latest log under `logs/nightly_delta/`
- export directory path from the nightly report

Confirm:

1. status is not a stop/failure state
2. canary gate passed if required
3. transfer failures are zero or explicitly understood
4. export path exists

### Step 2: Stage the export in V2 without writing

```powershell
.\.venv\Scripts\python.exe scripts\stage_forge_import.py `
  --source-root C:\CorpusForge\data\production_output `
  --select latest `
  --mode plan
```

Review:

- `source_selection.json`
- `preflight_report.json`
- `delta_validation.json`
- `planned_import_command.txt`

### Step 3: Run the canary dry-run

```powershell
.\.venv\Scripts\python.exe scripts\stage_forge_import.py `
  --source-root C:\CorpusForge\data\production_output `
  --select latest `
  --canary-limit 2000 `
  --mode dry-run
```

Review:

- `stage_result.json`
- dry-run import report path from `mode_result.report_path`
- canary export manifest when present

### Step 4: Full import only after the canary looks sane

```powershell
.\.venv\Scripts\python.exe scripts\stage_forge_import.py `
  --source C:\CorpusForge\data\production_output\export_<timestamp> `
  --mode import `
  --create-index
```

### Step 5: Morning validation questions

Run a small fixed validation pack:

1. one canary/source-identity check
2. one operational row lookup
3. one aggregate/list query
4. one narrative reference query
5. one known source-citation sanity check

This should stay small and repeatable.

## Exact Safe Implementation Slices

### Slice 9.4A — Artifact contract cleanup

Repo: Forge  
Risk: low  
Goal: make the latest nightly run trivial for the GUI and operator to discover.

Files:

- `scripts/run_nightly_delta.py`
- optional new small helper under `src/ops/` or `src/gui/`

Deliverable:

- write a stable `latest` pointer artifact for the most recent nightly run
- include latest scan/transfer/report/export/log paths

Reason:

- current timestamped artifacts are good for audit
- GUI polling becomes much simpler if one fixed path exists

### Slice 9.4B — Forge GUI read-only status + button shell

Repo: Forge  
Risk: medium  
Goal: add a thin operator panel without changing runner semantics.

Files:

- `src/gui/app.py`
- new `src/gui/nightly_delta_panel.py`
- `src/gui/launch_gui.py`
- focused GUI tests

Deliverable:

- section-based `Nightly Delta` panel
- subprocess launch of `scripts/run_nightly_delta.py`
- stop button that uses the sentinel file
- status labels fed from latest artifacts

### Slice 9.4C — Forge interlocks and honest messaging

Repo: Forge  
Risk: medium  
Goal: stop operators from launching conflicting workflows.

Files:

- `src/gui/app.py`
- `src/gui/nightly_delta_panel.py`
- `src/gui/launch_gui.py`
- new focused tests

Deliverable:

- prevent Nightly Delta vs manual Pipeline overlap on the same scope
- visible disabled reason text
- stop/resume status text that matches actual runner state

### Slice 9.4D — V2 morning validation pack

Repo: V2  
Risk: low  
Goal: keep the morning flow deterministic and QA-friendly.

Files:

- `docs/V2_STAGING_IMPORT_RUNBOOK_2026-04-09.md` or a small addendum
- optional small helper script only if the runbook is too manual

Deliverable:

- exact morning sequence
- fixed minimum validation questions
- required artifact list for signoff

### Slice 9.4E — Optional later V2 operator visibility

Repo: V2  
Risk: medium  
Goal: only if operators truly need it, expose the last staged import run in the V2 UI.

This is not required for the first implementation wave.

Avoid expanding into a V2 GUI admin project during this lane.

## QA Checklist

### Existing tests that should stay green

Forge:

- `tests/test_nightly_delta.py`

V2:

- `tests/test_stage_forge_import.py`

### New focused tests to add when implementation starts

Forge:

1. GUI panel renders current nightly status from a latest-pointer artifact
2. `Stop Safely` writes the stop file and transitions to `Stopping...`
3. `Resume Last` removes stale stop file and relaunches the same command
4. interlock blocks manual pipeline start during Nightly Delta activity
5. interlock blocks Nightly Delta start during conflicting manual pipeline activity

V2:

1. morning validation helper or runbook examples stay aligned with `stage_forge_import.py`
2. artifact paths surfaced to the operator remain deterministic

### Manual QA

1. scheduler XML emission looks correct
2. GUI panel shows the same roots/paths as config
3. scan-only run produces a report without transfer/pipeline
4. transfer-only run writes transfer manifest and input list
5. stop-file request during a run produces a clean stop and durable artifacts
6. rerun resumes without recopying already mirrored files
7. morning canary dry-run writes the expected V2 stage artifacts

## Safe Follow-On Recommendations

1. Treat `Pause` as UI wording over `Stop Safely + Resume`, not a separate execution model.
2. Add a stable latest-pointer artifact before building the GUI panel.
3. Keep the first GUI slice Forge-only; V2 already has the right CLI artifact model.
4. Do not promise chunk-checkpoint resume in this lane; rely on the existing durability lane where that behavior is owned.

## Tiny Config-Surface Improvement Note

No new config keys are required to start the implementation.

If the GUI slice needs one small improvement, the safest optional addition is:

- `nightly_delta.latest_status_path`

That would let the panel read one fixed JSON pointer instead of globbing timestamped files. It is optional and should not block the first implementation wave.

Signed: Agent Four | Lane 4
