# CorpusForge Config and GUI Reference - 2026-04-10

Purpose: give operators one practical config story for mainline Forge.

Audience: GUI operators, headless operators, and developers tracing where a setting is consumed.

## Runtime Truth

1. The live mainline runtime config is `config/config.yaml`.
2. The GUI `Save Settings` path writes back to `config/config.yaml`.
3. The GUI `Source` and `Output` boxes are per-run fields. They are not persisted by `Save Settings`.
4. Mainline skip/defer rules also load from `config/config.yaml` through `paths.skip_list`.
5. `config/skip_list.yaml` is no longer the live mainline operator file. It remains only as a quarantined legacy reference.

## Config Inventory

See `config/CONFIG_INVENTORY_2026-04-10.md` for the full checked-in inventory and file classification.

Short version:

- `config/config.yaml` = runtime
- `config/skip_list.yaml` = legacy reference
- `config/config.proof_sample.yaml` = preset
- `config/config.hash_skip_drawings.yaml` = legacy
- `config/config.aws_probe_fast.yaml` = legacy
- `config/nightly_task.xml` = preset
- `config.local.yaml` = local-only by intent, but not present in checked-in mainline

## Code Anchors

- Runtime config load: `src/config/schema.py::load_config`
- GUI save path: `src/gui/launch_gui.py::_save_gui_settings_override`
- GUI save payload: `src/gui/settings_panel.py::_handle_save_settings`
- GUI runtime banner and precheck launch: `src/gui/launch_gui.py::main`, `src/gui/launch_gui.py::PrecheckRunner._run`
- GUI status bar: `src/gui/app.py::_build_status_bar`, `src/gui/app.py::_update_status_bar`
- Skip/defer source load: `src/skip/skip_manager.py::_load_skip_source`
- Runtime defer merge: `src/pipeline.py::__init__`, `src/pipeline.py::run`
- Precheck config summary: `tools/precheck_workstation_large_ingest.py::_collect_results`, `tools/precheck_workstation_large_ingest.py::_render_report`

## What The GUI Actually Controls

### Saved to `config/config.yaml`

- `pipeline.workers`
- `parse.ocr_mode`
- `chunk.size`
- `chunk.overlap`
- `embed.enabled`
- `enrich.enabled`
- `enrich.max_concurrent`
- `extract.enabled`
- `extract.batch_size`
- `hardware.embed_batch_size`

These are collected in `src/gui/settings_panel.py::_handle_save_settings` and written in `src/gui/launch_gui.py::_save_gui_settings_override`.

### Not saved by `Save Settings`

- `Source`
- `Output`
- `paths.state_db`
- `pipeline.full_reindex`
- `parse.defer_extensions`
- `parse.docling_mode`
- all `nightly_delta.*` fields

`Source` and `Output` are run-time-only GUI fields in `src/gui/app.py::_build_control_panel`. They are applied to the in-memory config only when the run starts in `src/gui/launch_gui.py::PipelineRunner.start`.

## Operator Settings That Matter Most

### Worker count

- Setting: `pipeline.workers`
- Where operator sees it:
  - GUI settings panel spinner in `src/gui/settings_panel.py`
  - GUI status bar in `src/gui/app.py::_build_status_bar`
  - precheck report in `tools/precheck_workstation_large_ingest.py::_collect_results`
- Where runtime consumes it:
  - `src/pipeline.py::Pipeline.__init__`
  - `src/pipeline.py::_parallel_parse_and_chunk`
  - `src/gui/launch_gui.py::TransferRunner._run`

Practical rule:

- use logical CPU threads, not physical cores
- desktop target: `32`
- laptop target: `20`

### Run-time defer list

- Setting: `parse.defer_extensions`
- Where operator edits it: `config/config.yaml`
- Where operator sees it:
  - precheck report in `tools/precheck_workstation_large_ingest.py::_collect_results`
  - GUI startup/runtime banner in `src/gui/launch_gui.py::main`
  - pipeline logs and skip accounting in `src/gui/launch_gui.py::PipelineRunner._do_run`
- Where runtime consumes it:
  - merged into the live parser/skip path in `src/pipeline.py::__init__`
  - merged into discovery/preview logging in `src/gui/launch_gui.py::PipelineRunner._do_run`
  - merged into headless discovery logging in `scripts/run_pipeline.py::main`

Practical rule:

- use dotted lowercase extensions only, for example `.sao`, `.rsf`, `.jpg`
- deferred files are still hashed and accounted for

### Static skip/defer policy

- Settings: `skip.*` block inside `config/config.yaml`
- Includes:
  - `skip.deferred_formats`
  - `skip.placeholder_formats`
  - `skip.ocr_sidecar_suffixes`
  - `skip.image_asset_extensions`
  - `skip.encrypted_filename_tokens`
  - `skip.skip_conditions`
- Where runtime consumes it:
  - loaded from the configured source file in `src/skip/skip_manager.py::_load_skip_source`
  - applied in `src/skip/skip_manager.py::SkipManager.__init__`
  - enforced in `src/skip/skip_manager.py::SkipManager.should_skip`

Practical rule:

- use `parse.defer_extensions` for temporary per-run defers
- use `skip.*` for durable mainline policy

## Precheck Story

The precheck uses the same runtime config path the operator will use for the actual run.

- GUI launch path: `src/gui/launch_gui.py::PrecheckRunner._run`
- tool entry: `tools/precheck_workstation_large_ingest.py::main`
- effective settings snapshot: `tools/precheck_workstation_large_ingest.py::_collect_results`

Precheck now surfaces:

- live runtime config path
- skip/defer source path
- worker count
- current `parse.defer_extensions`
- stage toggles and embed batch size

## Headless Story

For headless and script-driven runs, the operator path is still `config/config.yaml`.

Primary consumers:

- `scripts/boot.py`
- `scripts/run_pipeline.py`
- `scripts/backfill_skipped_file_state.py`
- `scripts/install_nightly_delta_task.py`
- `scripts/nightly_delta_ingest.py`

## Legacy / Quarantined Files

These files are still in the repo but are not the live mainline runtime path:

- `config/skip_list.yaml`
- `config/config.proof_sample.yaml`
- `config/config.hash_skip_drawings.yaml`
- `config/config.aws_probe_fast.yaml`
- `config/nightly_task.xml`

Reason to keep them:

- reproducibility for prior proof lanes
- historical reference while older notes are being retired
- scheduler preset packaging

Operator rule:

- do not treat any of those files as the mainline runtime source unless a specific lane explicitly rewires code to use them

## Recommended Operator Check Before A Large Run

1. Open `config/config.yaml`.
2. Confirm `pipeline.workers`.
3. Confirm `parse.ocr_mode`.
4. Confirm `parse.defer_extensions`.
5. Confirm the `skip:` block reflects the durable skip/defer policy you want.
6. Run GUI `Run Precheck` or `tools/precheck_workstation_large_ingest.py`.
7. Start the run only after those match the intended lane.

Signed: CoPilot+
