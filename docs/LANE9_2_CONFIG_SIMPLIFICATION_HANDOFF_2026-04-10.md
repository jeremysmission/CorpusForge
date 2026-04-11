# Lane 9.2 Handoff — Config Simplification / Operator Clarity — 2026-04-10

## Repo

- `C:\CorpusForge`

## Branch

- `master`

## Exact Files Changed

- `C:\CorpusForge\config\CONFIG_INVENTORY_2026-04-10.md`
- `C:\CorpusForge\config\config.yaml`
- `C:\CorpusForge\config\skip_list.yaml`
- `C:\CorpusForge\src\config\schema.py`
- `C:\CorpusForge\src\gui\app.py`
- `C:\CorpusForge\src\gui\settings_panel.py`
- `C:\CorpusForge\src\gui\launch_gui.py`
- `C:\CorpusForge\tools\precheck_workstation_large_ingest.py`
- `C:\CorpusForge\tests\test_config.py`
- `C:\CorpusForge\tests\test_gui_dedup_only.py`
- `C:\CorpusForge\tests\test_gui_button_smash.py`
- `C:\CorpusForge\docs\CONFIG_AND_GUI_REFERENCE_2026-04-09.md`
- `C:\CorpusForge\docs\OPERATOR_QUICKSTART.md`
- `C:\CorpusForge\docs\OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md`
- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- `C:\CorpusForge\docs\LANE9_2_CONFIG_SIMPLIFICATION_HANDOFF_2026-04-10.md`

## Runtime Truth Map

### Active runtime config surface

- Live runtime file: `config/config.yaml`
  - `config/config.yaml:1-5`
  - `config/config.yaml:13`
- Default runtime loader and relative-path resolution:
  - `src/config/schema.py:43-47`
  - `src/config/schema.py:348-359`

### GUI surface

- Main GUI default config path:
  - `src/gui/launch_gui.py:24`
- GUI Save Settings writes the active config file and updates the in-memory config:
  - `src/gui/launch_gui.py:736-755`
- Settings panel tells the operator which file is live and what Save Settings actually persists:
  - `src/gui/settings_panel.py:26-27`
  - `src/gui/settings_panel.py:189-196`
  - `src/gui/settings_panel.py:258-279`
- Status bar shows runtime config plus skip/defer counts:
  - `src/gui/app.py:346-350`
  - `src/gui/app.py:577-588`
  - `src/gui/app.py:612-613`

### CLI surface

- Boot validation default:
  - `scripts/boot.py:19-31`
- Headless pipeline default:
  - `scripts/run_pipeline.py:107-109`
  - `scripts/run_pipeline.py:135`
- Dedup GUI default:
  - `src/gui/launch_dedup_gui.py:25`
  - `src/gui/launch_dedup_gui.py:166-173`

### Precheck surface

- GUI precheck launches the tool with the active config path:
  - `src/gui/launch_gui.py:406-419`
- Precheck now resolves `--config` against repo root before reporting it, so external cwd no longer lies about the runtime config path:
  - `tools/precheck_workstation_large_ingest.py:95-104`
  - `tools/precheck_workstation_large_ingest.py:134-135`
  - `tools/precheck_workstation_large_ingest.py:233-266`
  - `tools/precheck_workstation_large_ingest.py:297-301`

### Quarantined / legacy surfaces

- `config/skip_list.yaml` is explicitly labeled legacy:
  - `config/skip_list.yaml:1-6`
- Checked-in config inventory classifies the remaining files:
  - `config/CONFIG_INVENTORY_2026-04-10.md:5-21`
  - `config/CONFIG_INVENTORY_2026-04-10.md:23-35`
- Active operator docs point the mainline story at `config/config.yaml`, not `config.local.yaml`:
  - `docs/CONFIG_AND_GUI_REFERENCE_2026-04-09.md:7-17`
  - `docs/CONFIG_AND_GUI_REFERENCE_2026-04-09.md:29-38`
  - `docs/CONFIG_AND_GUI_REFERENCE_2026-04-09.md:145-163`
  - `docs/OPERATOR_QUICKSTART.md:151-166`
  - `docs/OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md:73-104`
  - `docs/OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md:255-263`

## Consolidation Result

- Mainline runtime now has one obvious operator file: `config/config.yaml`.
- `paths.skip_list` intentionally still points at `config/config.yaml` so skip/defer policy lives in the same runtime file.
- `config/skip_list.yaml` remains only as a quarantined historical reference.
- GUI `Save Settings` remains intentionally limited to the settings-panel fields; `Source` and `Output` stay per-run fields.
- No pipeline durability, embed, or resume logic was changed in this lane.

## Exact Commands Run

```powershell
cmd /c git status --short
cmd /c git branch --show-current
cmd /c rg -n -e "config\.local\.yaml" -e "config/config\.yaml" -e "load_config" -e "Save Settings" config src tools docs
cmd /c .\.venv\Scripts\python.exe -m pytest tests\test_config.py -q
cmd /c .\.venv\Scripts\python.exe -m pytest tests\test_gui_dedup_only.py -q
cmd /c .\.venv\Scripts\python.exe -m pytest tests\test_gui_button_smash.py -q
cmd /c C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\scripts\boot.py --config config/config.yaml
cmd /c C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\tools\precheck_workstation_large_ingest.py --config config/config.yaml --source {USER_HOME} --output {USER_HOME}\AppData\Local\Temp\cf_cfg_lane_out --workers 1 --ocr-mode auto --embed-enabled 0 --enrich-enabled 0 --extract-enabled 0 --embed-batch-size 8
```

## Tests Run

- `tests/test_config.py` — `19 passed`
- `tests/test_gui_dedup_only.py` — `14 passed`
- `tests/test_gui_button_smash.py` — `16 passed`

Total focused lane tests: `49 passed`

## GUI Harness Status

- Tier A-C automated GUI coverage: complete via `tests/test_gui_button_smash.py` and `tests/test_gui_dedup_only.py`
- Tier D human button smash by a non-author: **pending before signoff**
- Required Tier D completion fields:
  - Tester: `<non-author>`
  - Duration: `<minutes>`
  - Report path: `<doc or QA post>`
  - Result: `PASS` / `FAIL`
- Recommended Tier D scope for this lane:
  1. launch the main GUI against `config/config.yaml`
  2. verify the status bar shows the runtime config path and skip/defer counts
  3. verify the Settings panel banner names the live runtime config
  4. click `Save Settings` with a safe/no-op change and confirm the log calls out `config/config.yaml`
  5. run `Run Precheck` and confirm the output reports `Runtime cfg` and `Skip/defer src` as `C:\CorpusForge\config\config.yaml`

## CLI / GUI / Precheck Proof

- GUI save / operator wording proof:
  - `tests/test_gui_dedup_only.py::test_save_settings_writes_config_yaml`
  - `tests/test_gui_dedup_only.py::test_save_settings_log_calls_out_live_runtime_config`
  - `tests/test_gui_dedup_only.py::test_corpusforge_status_bar_defaults_to_live_runtime_config`
  - `tests/test_gui_dedup_only.py::test_precheck_button_passes_current_gui_settings`
- CLI load proof:
  - `scripts/boot.py --config config/config.yaml` run from `{USER_HOME}` completed successfully and loaded the live config.
- Precheck agreement proof:
  - `tools/precheck_workstation_large_ingest.py --config config/config.yaml ...` run from `{USER_HOME}` reported:
    - `Runtime cfg:    C:\CorpusForge\config\config.yaml`
    - `Skip/defer src: C:\CorpusForge\config\config.yaml`
    - `RESULT: PASS`

## Artifact / Output Paths

- `C:\CorpusForge\config\CONFIG_INVENTORY_2026-04-10.md`
- `C:\CorpusForge\docs\CONFIG_AND_GUI_REFERENCE_2026-04-09.md`
- `C:\CorpusForge\docs\OPERATOR_QUICKSTART.md`
- `C:\CorpusForge\docs\OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md`
- `C:\CorpusForge\logs\precheck_workstation_20260410_171600.txt`

## Current Status

- `READY FOR QA`
- automated GUI/CLI/precheck proof is complete
- non-author Tier D human GUI button smash is still required before signoff

## Remaining Risks Or Blockers

- Historical/evidence docs still contain `config.local.yaml` references where they are describing old runs, clone lanes, or prior recovery notes. They were not promoted back into the active mainline operator story in this lane.
- The proof precheck run used `workers=1` on purpose, so the report includes a worker-count warning. That is not a lane defect.
- The proof machine still lacks `pdftoppm` on PATH, so the precheck report includes a Poppler warning. That is an environment warning, not a config-surface mismatch.
- `sanitize_before_push.py` dry-run is currently clean.
- Tier D human button smash by a non-author is still pending, so this lane is not signoff-clean yet.
- The repo has unrelated dirty work outside this lane, so this handoff is local-only unless a coordinator chooses to isolate and commit the lane files.

## Next Step For QA Or Next Coder

1. Re-run the three focused pytest files.
2. Re-run `scripts/boot.py --config config/config.yaml` from outside `C:\CorpusForge`.
3. Re-run the precheck command from outside `C:\CorpusForge` and confirm the report still prints `C:\CorpusForge\config\config.yaml` for both runtime and skip/defer paths.
4. Complete Tier D manual GUI button smash with a non-author and record `Tester`, `Duration`, `Report path`, and `Result`.
5. Spot-check the GUI status bar and Settings panel wording against the truth map above.

## Crash Note

Before commit/push, the local changes at risk in this lane are:

- `C:\CorpusForge\config\CONFIG_INVENTORY_2026-04-10.md`
- `C:\CorpusForge\config\config.yaml`
- `C:\CorpusForge\config\skip_list.yaml`
- `C:\CorpusForge\src\config\schema.py`
- `C:\CorpusForge\src\gui\app.py`
- `C:\CorpusForge\src\gui\settings_panel.py`
- `C:\CorpusForge\src\gui\launch_gui.py`
- `C:\CorpusForge\tools\precheck_workstation_large_ingest.py`
- `C:\CorpusForge\tests\test_config.py`
- `C:\CorpusForge\tests\test_gui_dedup_only.py`
- `C:\CorpusForge\tests\test_gui_button_smash.py`
- `C:\CorpusForge\docs\CONFIG_AND_GUI_REFERENCE_2026-04-09.md`
- `C:\CorpusForge\docs\OPERATOR_QUICKSTART.md`
- `C:\CorpusForge\docs\OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md`
- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- `C:\CorpusForge\docs\LANE9_2_CONFIG_SIMPLIFICATION_HANDOFF_2026-04-10.md`

Signed: reviewer | Lane 9.2
