# CorpusForge Config Inventory — 2026-04-10

Purpose: one operator-facing inventory of every config file currently checked into `C:\CorpusForge\config`.

## Current operator rule

- Live runtime config: `config/config.yaml`
- GUI `Save Settings` target: `config/config.yaml`
- Skip/defer rule source in mainline: `paths.skip_list: config/config.yaml`
- No local-only config file is checked into this repo on mainline.

## Inventory

| File | Class | Keep? | Why |
|------|-------|-------|-----|
| `config.yaml` | runtime | Yes | Mainline runtime config loaded by `src/config/schema.py::load_config`, launched by `scripts/boot.py`, `scripts/run_pipeline.py`, `src/gui/launch_gui.py`, and used by `tools/precheck_workstation_large_ingest.py`. |
| `skip_list.yaml` | legacy | Yes, quarantined | Historical skip/defer reference file. Mainline no longer points operators here; active skip/defer rules now load from `config.yaml` through `src/skip/skip_manager.py::_load_skip_source`. |
| `config.proof_sample.yaml` | preset | Yes | Tiny proof preset used for the Sprint 6.6 archive-defer mechanism check. Not a live operator config. |
| `config.hash_skip_drawings.yaml` | legacy | Yes | Older rebuild/profile preset for drawing-heavy runs. Keep only for historical reproducibility. |
| `config.aws_probe_fast.yaml` | legacy | Yes | Older probe/timing preset. Keep only for historical reproducibility. |
| `nightly_task.xml` | preset | Yes | Windows Task Scheduler XML template, consumed by the scheduler helper path rather than the normal runtime loader. |

## Local-only status

- `config.local.yaml`: local-only by intent, but not present in this checked-in mainline config folder.
- If a side experiment or clone lane needs a local-only override, keep it out of the mainline operator story unless code explicitly wires it back in.

## Code anchors

- Runtime config load: `src/config/schema.py::load_config`
- GUI save path: `src/gui/launch_gui.py::_save_gui_settings_override`
- GUI settings payload: `src/gui/settings_panel.py::_handle_save_settings`
- Precheck runtime config use: `tools/precheck_workstation_large_ingest.py::_collect_results`
- Skip/defer source load: `src/skip/skip_manager.py::_load_skip_source`
- Run-time defer merge: `src/pipeline.py::__init__` and `src/pipeline.py::run`
