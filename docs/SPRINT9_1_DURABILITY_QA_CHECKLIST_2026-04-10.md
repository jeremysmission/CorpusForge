# Sprint 9.1 Durability QA Checklist

## Setup

1. Use repo root `C:\CorpusForge`.
2. Use repo-local venv: `C:\CorpusForge\.venv\Scripts\python.exe`.
3. Pin GPU 1 for this lane:
   `set CUDA_VISIBLE_DEVICES=1`

## Proof Re-run

1. Run:
   `C:\CorpusForge\.venv\Scripts\python.exe C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\run_hardware_proof.py`
2. The runner is replayable and refreshes the fixed proof root in place, so the same absolute command can be rerun from any working directory.
3. Open:
   `C:\CorpusForge\data\sprint9_lane1_validation_20260410_171433\hardware_proof_report.json`

## Required Checks

1. CUDA environment is real:
   - `environment.cuda_visible_devices` is `"1"`
   - `environment.cuda_available` is `true`
   - `environment.visible_device_count` is `1`
   - `environment.rerun_mode` is `"fixed proof root refreshed in place"`
2. Live embed happened before parse finished:
   - `live_embed_run.live_embed_evidence.snapshot.files_parsed < live_embed_run.files_parsed`
   - `live_embed_run.live_embed_evidence.snapshot.vectors_created > 0`
   - `len(live_embed_run.live_embed_evidence.nvidia_smi_samples) == 5`
   - `live_embed_run.live_embed_evidence.nvidia_smi.memory_used_mb > environment.physical_gpu_1_before.memory_used_mb`
   - `live_embed_run.live_embed_evidence.torch_cuda_memory_reserved_mb > 0`
3. Stop left a real checkpoint:
   - `stop_run.stop_requested` is `true`
   - `stop_run.export_dir` is empty
   - `stop_run.checkpoint_exists` is `true`
   - `stop_run.docs_partial_lines > 0`
   - `stop_run.chunks_partial_lines > 0`
   - `stop_run.checkpoint_manifest.status` is `stopped_before_export`
4. Resume reused the checkpoint:
   - `resume_run.resume_details` contains `Resumed`
   - `resume_run.checkpoint_cleared` is `true`
5. Export integrity is aligned:
   - `resume_run.manifest_chunk_count == resume_run.jsonl_chunk_count == resume_run.vector_rows`
   - `live_embed_run.manifest_chunk_count == live_embed_run.jsonl_chunk_count == live_embed_run.vector_rows`
   - `resume_run.vector_dim == 768`
   - `live_embed_run.vector_dim == 768`
6. Dedup-only portable copy still works:
   - `dedup_only.unique_files == 4`
   - `dedup_only.duplicates_found == 4`
   - `dedup_only.portable_files_copied == 4`
   - `dedup_only.portable_relative_matches_canonical` is `true`

## Regression Slice

1. Run:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_pipeline_e2e.py -q`
2. Expect:
   - `23 passed`
3. Run:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_gui_button_smash.py -q`
4. Expect:
   - `16 passed`

## Known Environment Limitation

1. If you run this command from `{USER_HOME}`:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_gui_dedup_only.py -q`
2. On this workstation today it passed in isolation: `14 passed`.
3. The reproducible Tk blocker is the combined slice from `C:\CorpusForge`:
   `C:\CorpusForge\.venv\Scripts\python.exe -m pytest C:\CorpusForge\tests\test_pipeline_e2e.py C:\CorpusForge\tests\test_gui_button_smash.py C:\CorpusForge\tests\test_gui_dedup_only.py -q`
4. That combined slice fails at the shared `tests/test_gui_dedup_only.py::root` fixture with `_tkinter.TclError: invalid command name "tcl_findLibrary"`.
5. Treat that as an environment blocker unless the lane claims Tk repair.

## Signoff Rule

1. If all required checks pass and the combined-slice Tk issue is recorded as environment-only, Sprint 9.1 is QA-ready on the durability/live-embed scope.

Signed: reviewer
