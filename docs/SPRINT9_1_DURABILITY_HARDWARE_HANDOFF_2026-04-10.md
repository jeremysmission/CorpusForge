# Sprint 9.1 Durability / Live-Embed Hardware Handoff

- Date: `2026-04-10`
- Repo: `C:\CorpusForge`
- Branch: `master`
- Agent: `reviewer`
- GPU assignment: `physical GPU 1`, pinned with `CUDA_VISIBLE_DEVICES=1`
- Status: `READY FOR QA`

## Scope

- Validate the current durability/checkpointing lane on real hardware against real files.
- Prove live CUDA embedding on GPU 1 before parse completes.
- Prove cooperative stop leaves a durable `_checkpoint_active`.
- Prove compatible rerun resumes from checkpointed parse/chunk state instead of reparsing completed docs.
- Prove final export integrity.
- Prove dedup-only portable source copy still preserves source-relative layout.

## Lane Files Under Validation

- `C:\CorpusForge\src\pipeline.py`
- `C:\CorpusForge\src\export\chunk_checkpoint.py`
- `C:\CorpusForge\tests\test_pipeline_e2e.py`
- `C:\CorpusForge\tests\test_gui_button_smash.py`

## Docs Added For This Packet

- `C:\CorpusForge\docs\SPRINT9_1_DURABILITY_HARDWARE_HANDOFF_2026-04-10.md`
- `C:\CorpusForge\docs\SPRINT9_1_DURABILITY_QA_CHECKLIST_2026-04-10.md`

## Exact Files Changed For This Lane Packet

- `C:\CorpusForge\docs\SPRINT_SYNC.md`
- `C:\CorpusForge\docs\SPRINT9_1_DURABILITY_HARDWARE_HANDOFF_2026-04-10.md`
- `C:\CorpusForge\docs\SPRINT9_1_DURABILITY_QA_CHECKLIST_2026-04-10.md`
- `C:\CorpusForge\___WAR_ROOM_BOARD_2026_04_10.md`
- `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`

## Exact Commands Run

1. Baseline GPU check:
   `nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader`
2. Proof runner syntax check:
   `C:\CorpusForge\.venv\Scripts\python.exe -m py_compile C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`
3. Real hardware proof from `{USER_HOME}`:
   `C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`
4. Replay of the same proof command from `{USER_HOME}` to confirm the fixed proof root refreshes in place:
   `C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`
5. Replay of the same proof command again after hardening live GPU sampling:
   `C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`
6. Targeted pipeline regression slice:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_pipeline_e2e.py -q`
7. Targeted stop-plumbing GUI test slice:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_gui_button_smash.py -q`
8. Isolated dedup-only GUI slice from `{USER_HOME}`:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_gui_dedup_only.py -q`
9. Combined targeted slice from `C:\CorpusForge`:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_pipeline_e2e.py C:\CorpusForge\tests\test_gui_button_smash.py C:\CorpusForge\tests\test_gui_dedup_only.py -q`
10. Syntax check for current pipeline files plus proof runner:
   `C:\CorpusForge\.venv\Scripts\python.exe -m py_compile C:\CorpusForge\src\pipeline.py C:\CorpusForge\src\export\chunk_checkpoint.py C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`
11. Repo sanitizer dry-run after board/doc updates:
   `C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\sanitize_before_push.py`

## Test Results

- `tests/test_pipeline_e2e.py`: `23 passed`
- `tests/test_gui_button_smash.py`: `16 passed`
- `tests/test_gui_dedup_only.py` from `{USER_HOME}`: `14 passed`
- `sanitize_before_push.py` dry-run: `All files are clean. Ready to push.`
- Combined targeted slice: `40 passed, 13 errors`
  - all 13 errors came from `tests/test_gui_dedup_only.py`
  - failure mode: workstation Tk runtime is broken in the shared combined-slice fixture path, not a durability code assertion
  - reproduction shape: the isolated `tests/test_gui_dedup_only.py` command passed, but the combined slice failed at `tests/test_gui_dedup_only.py::root`
  - representative error: `_tkinter.TclError: invalid command name "tcl_findLibrary"`

## Real-Hardware Proof Inputs

- Proof root: `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433`
- Proof runner artifact: `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`
- Real subset root: `C:\CorpusForge\data\sprint9_lane1_hardware_proof_20260410\subset`
- Proof runner behavior: each invocation clears only the generated proof artifacts under the fixed proof root and refreshes the packet in place
- Subset shape: `8 real files`
  - `2 x .doc`
  - `2 x .txt`
  - `2 x .docx`
  - `2 x .pdf`
- Duplicate structure: four duplicate pairs, so dedup reduces pipeline work to four canonicals

## Key Proof Outcomes

### 1. CUDA was used on a real embed-enabled run

- Environment proof from `hardware_proof_report.json`:
  - `cuda_visible_devices = 1`
  - `cuda_available = true`
  - `visible_device_count = 1`
  - `visible_device_name = NVIDIA GeForce RTX 3090`
  - `rerun_mode = fixed proof root refreshed in place`
- Live embed proof before parse finished:
  - file: `live_embed_run.live_embed_evidence`
  - snapshot captured with `files_parsed = 1` out of `4 work files`
  - same snapshot had `vectors_created = 1`
  - GPU-memory evidence on physical GPU 1:
    - baseline before the run: `36 MiB`
    - live embed capture: `2111 MiB`
    - sampled `nvidia-smi` window: `5` snapshots saved in the report
    - `torch_cuda_memory_allocated_mb = 279.6`
    - `torch_cuda_memory_reserved_mb = 1792.0`
- Stage trace confirms live embed flush events occurred before parse finished:
  - file: `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\live_stages.json`
  - first embed event: `GPU live flush 1/1 vectors (...)`
  - it appears before parse reaches `4/4`

### 2. Cooperative stop left a durable checkpoint

- Stop run status:
  - `stop_requested = true`
  - `export_dir = ""`
  - `checkpoint_dir = C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\stop_resume_output\output\_checkpoint_active`
- `_checkpoint_active` contents at stop:
  - `docs.partial.jsonl`: `2` lines
  - `chunks.partial.jsonl`: `59` lines
  - `parsed_sources.txt`: `2` paths
  - `checkpoint_manifest.json` status: `stopped_before_export`
  - manifest counters: `checkpointed_files = 2`, `checkpointed_chunks = 59`

### 3. Compatible rerun resumed instead of reparsing completed docs

- Replayability proof:
  - the same absolute proof command was invoked repeatedly from `{USER_HOME}`
  - each replay refreshed the fixed proof root in place instead of failing on stale state
- Resume stage evidence:
  - file: `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\resume_stages.json`
  - parse stage detail: `Resumed 2 files / 59 chunks from checkpoint.`
- Resume run exported successfully:
  - export: `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\stop_resume_output\output\export_20260410_1716`
- Checkpoint cleanup after successful export:
  - `_checkpoint_active` removed
  - `checkpoint_cleared = true`

### 4. Final export integrity passed

- Resume export:
  - `manifest_chunk_count = 62`
  - `jsonl_chunk_count = 62`
  - `vector_rows = 62`
  - `vector_dim = 768`
- Separate live-embed export:
  - `manifest_chunk_count = 62`
  - `jsonl_chunk_count = 62`
  - `vector_rows = 62`
  - `vector_dim = 768`
- `.doc` content still exported after the checkpoint/resume changes:
  - `doc_source_exported = true` in both exports

### 5. Dedup-only portable copy still worked

- Dedup-only proof:
  - `files_scanned = 8`
  - `unique_files = 4`
  - `work_files = 4`
  - `duplicates_found = 4`
  - `portable_files_copied = 4`
  - `portable_relative_matches_canonical = true`
- Portable copy root:
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\dedup_only_output\dedup_only_20260410_171612\deduped_sources`

## Artifact Paths

- Master report:
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\hardware_proof_report.json`
- Raw stage traces:
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\stop_stages.json`
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\resume_stages.json`
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\live_stages.json`
- Raw stats snapshots:
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\stop_snapshots.json`
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\resume_snapshots.json`
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\live_snapshots.json`
- Run logs:
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\logs\stop_before_embed.log`
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\logs\resume_same_output.log`
  - `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\logs\live_embed_flush.log`

## Residual Risks / Blockers

- The combined targeted pytest slice is blocked on this workstation by a Tk runtime issue at the shared `tests/test_gui_dedup_only.py::root` fixture (`_tkinter.TclError: invalid command name "tcl_findLibrary"`). The isolated `tests/test_gui_dedup_only.py -q` command passed from `{USER_HOME}`.
- This proof subset is real, but small. It proves checkpoint correctness and real CUDA use on actual files, not full-corpus wall-clock durability.
- The proof runner under `data/sprint9_lane1_validation_20260410_171433\run_hardware_proof.py` is an evidence artifact, not production code.

## Push / Retention Status

- Current status: `READY FOR QA`
- Repo docs and boards are updated locally in this working tree, but this lane was not pushed from this session.
- QA evidence depends on the local proof artifact root `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433`.
- If the workstation is lost before promotion, the proof root above is the primary lane artifact path at risk.

## Next Step For QA

- Use `C:\CorpusForge\docs\SPRINT9_1_DURABILITY_QA_CHECKLIST_2026-04-10.md`.
- Re-run the exact absolute proof command on GPU 1 from any working directory if you want fresh evidence; the runner now refreshes the fixed proof root in place.
- Verify the JSON report fields directly; no inference from console logs should be required.

Signed: reviewer
