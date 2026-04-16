# Golden Production Data + Canary Test Plan

Purpose: rehearse the real CorpusForge -> V2 morning flow with the actual data slices and runtime paths now in use, then scale only after the small run and the meaningful subset are both clean.

This is not a synthetic benchmark plan. It is an operator and QA plan built around the known 53-file dry run, the known Sprint 7 production subset, and the current clean Forge export.

## Fixed References For This Plan

- Active Forge runtime config: `C:\CorpusForge\config\config.yaml`
- GUI Save Settings target: `C:\CorpusForge\config\config.yaml`
- Current clean reference export: `C:\CorpusForge\data\production_output\export_20260409_0720`
- Current preferred V2 import entrypoint: `C:\HybridRAG_V2\scripts\stage_forge_import.py`
- Underlying direct importer: `C:\HybridRAG_V2\scripts\import_embedengine.py`
- Legacy note: `config/config.local.yaml` is not part of the live mainline runtime path

## Test Levels

### Canary

Use the current 53-file morning dry-run sample.

Purpose:

- catch wrong paths, stale settings, and GUI/operator confusion quickly
- prove the end-to-end assembly line still works on a small real sample
- prove reruns and interruption recovery behave the way the current hash/state design says they should

Recommended contents:

- the known 53-file morning sample
- a few intentional duplicates
- at least one archive if archive defer behavior needs confirmation
- at least one scanned PDF only if OCR tools are installed and OCR behavior matters for the run

### Golden

Use the real production subset that is large enough to matter but still inspectable.

Primary golden input:

- the Sprint 7 1000-file production subset

Optional companion run:

- the 90 GB production sample for dedup-only or format-mix confirmation before the full ingest

Purpose:

- validate real-format coverage on production-shaped data
- validate rerun behavior and hash continuity on real files
- validate export/import compatibility with V2
- validate representative query quality before pointing the pipeline at the full 700 GB drop

### Full Production

Use the full 700 GB source only after Canary and Golden are both clean enough to explain any remaining residual risk.

## Preflight

Before either run size:

- confirm `config/config.yaml` contains the intended source path, output path, worker count, parser defer list, GPU setting, and batch sizes
- if using the GUI, save once and verify the expected settings landed in `config/config.yaml`
- do not assume `config/config.local.yaml` is active
- verify Tesseract and Poppler only if scanned-PDF or OCR behavior matters for this run
- verify Ollama only if enrichment is enabled for this run
- confirm free disk space for export plus rerun evidence
- record the repo, branch, GPU choice, input path, and output path before launch

## Expected Stage Behavior

- low GPU usage during parse is usually expected because parse is mostly CPU, I/O, and OCR bound
- GPU usage should rise during embed and optional enrichment
- parser failures must be visible in reports; they are not allowed to disappear into aggregate counts
- repeated runs on unchanged inputs should skip cleanly rather than duplicate work
- interrupted work should persist as `hashed` in the state DB and resume cleanly on rerun; the plan should no longer rely on RAM-only hash state

## Canary Procedure

1. Run the 53-file sample through the normal Forge path you expect the operator to use that morning.
2. Confirm the chosen input path, output path, worker count, and parser defer settings in `config/config.yaml`.
3. Let the run finish end to end: dedup, parse, chunk, optional enrich, embed, export.
4. Confirm the export package lands where expected and the run report is readable without extra cleanup.
5. Re-run the same sample without changing the inputs and confirm skip/hash behavior looks stable.
6. If recovery behavior is part of the lane being validated, interrupt one run midstream, restart it, and confirm the state DB resumes from persisted `hashed` state.
7. Import the resulting export into V2 with `scripts/import_embedengine.py`.
8. Run a small representative query check in V2 against the imported data.

## Canary Pass Gates

- no manual recovery needed to complete the run
- GUI or CLI path is understandable enough that the operator does not have to guess what happened
- live stage/progress updates are visible if the GUI path is used
- dedup output, reports, and export files land in the selected output location
- rerunning unchanged input does not duplicate chunks or vectors
- interrupted-run recovery, if tested, resumes from persisted state rather than starting blind
- V2 import accepts the export package without path surgery or schema repair

## Golden Procedure

1. Run the Sprint 7 1000-file production subset through the intended mainline morning path.
2. If dedup behavior or file-mix expectations still need confirmation, run the 90 GB companion sample in dedup-only mode first.
3. Use the same runtime path the operator will use for the full ingest: `config/config.yaml`, real parser defer settings, real batch sizes, real output root.
4. Compare the resulting export against the known clean reference export at `C:\CorpusForge\data\production_output\export_20260409_0720`.
5. Import the golden export into V2 using `C:\HybridRAG_V2\scripts\import_embedengine.py`.
6. Run representative real queries, not only happy-path synthetic prompts.
7. If the run is interrupted or re-run, confirm state DB continuity and stable chunk/export counts.

## Golden Pass Gates

- dedup reduction is explainable against the known corpus shape
- parse success rate is in family with the known production subset unless the input mix materially changed
- chunk counts and export counts stay stable across reruns
- export package structure is complete and coherent
- V2 import succeeds without manual repair
- representative query results look plausible on real questions
- any tested interruption resumes from persisted `hashed` state cleanly

## What To Verify By Stage

### Source

- input path is correct
- duplicate families are expected
- file mix matches what the workstation can really parse today

### Dedup

- `_N` suffix duplicates collapse the way we expect
- identical content under different names collapses
- `canonical_files.txt`, `dedup_report.json`, and `run_report.txt` match reality
- the tail-file count bug stays fixed even when the final file is duplicate or unchanged

### Parse

- text-first files parse cleanly
- scanned PDFs only parse when OCR prerequisites are present
- low GPU during parse is treated as expected behavior, not as a false alarm by itself
- failures are reported with enough detail to classify them later

### Chunk + Embed

- `chunk_id` stays deterministic
- repeated runs on unchanged inputs do not create duplicate chunks
- vectors exist for every kept chunk
- OOM backoff or batch reduction is visible if it happens

### Export + V2 Import

- `chunks.jsonl`, `vectors.npy`, `manifest.json`, `skip_manifest.json`, and `run_report.txt` are present as appropriate
- `entities.jsonl` is present when extraction is enabled
- import reads the export package without path confusion
- imported chunk count matches the export count closely enough to explain any delta

## Evidence To Capture

- repo, branch, date/time, GPU assignment, input path, output path, and config path
- whether OCR tools were present
- whether enrichment was enabled
- export directory name
- key counts from dedup, parse, chunk, embed, and import
- whether low GPU during parse was observed and whether embed later ramped as expected
- whether rerun/interrupt recovery passed the persisted `hashed`-state check
- representative V2 queries and whether they returned usable sources

## Real Baselines We Already Have

- Canary reference set: the 53-file morning dry-run sample
- Golden reference set: the Sprint 7 1000-file production subset
- Dedup companion sample: 90 GB production slice
- Current clean Forge export: `C:\CorpusForge\data\production_output\export_20260409_0720`
- Dedup on the 90 GB sample: 49.7% duplicate rate
- Parse on the 1000-file production subset: 94.7% success rate
- Chunking quality: 77% in target size range
- Embedding throughput: about 305 chunks/sec on the RTX 3090 workstation
- Enrichment A/B lift in the measured sample: 67% retrieval quality improvement

Use those as baselines, not guarantees.

## Expansion Rule

1. Run the Canary first.
2. If the Canary is clean, run the Golden subset.
3. If the Golden subset is clean, move to the full 700 GB ingest.
4. If any step fails, fix the operator path, config drift, or code/doc mismatch before scaling up.
