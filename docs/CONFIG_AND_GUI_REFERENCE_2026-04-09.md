# CorpusForge Config and GUI Reference - 2026-04-09

Purpose: document the live operator-facing Forge controls and the YAML settings that materially change runtime behavior.

Audience: operators running Forge from the GUI or headless scripts, plus developers who need the code anchor for each setting.

Scope rule: this is a practical reference, not a theory note. It covers the knobs that actually change run shape, restart behavior, output location, or hardware usage. It does not try to re-document every internal model field.

## Current Runtime Truths

1. The live Forge runtime config is `config/config.yaml`, loaded by `load_config()` in `src/config/schema.py:345-406`.
2. The main GUI `Source` and `Output` boxes are per-run inputs. They are not part of `Save Settings`, and they start with hardcoded widget defaults (`data/source`, `data/output`) in `src/gui/app.py:237-277`.
3. `Save Settings` writes only the settings-panel fields listed in `src/gui/settings_panel.py:220-236`, then updates the in-memory config in `src/gui/launch_gui.py:646-663`.
4. Parser env vars can override YAML at runtime:
   - `HYBRIDRAG_OCR_MODE`
   - `HYBRIDRAG_DOCLING_MODE`
   Code: `src/pipeline.py:137-160`, `src/parse/parsers/pdf_parser.py:19-40`, `src/parse/parsers/docling_bridge.py:25-30`.
5. GPU choice is auto-selected at process start with `apply_gpu_selection()`, which sets `CUDA_VISIBLE_DEVICES`. Code: `src/gpu_selector.py:18-74`, `src/gui/launch_gui.py:601-603`, `scripts/run_pipeline.py:152`.

## Normal Single-GPU Baseline

For a normal workstation ingest, the conservative baseline is:

- `paths.output_dir`: dedicated writable parent folder for export packages
- `paths.state_db`: one stable SQLite path for this corpus lane
- `pipeline.full_reindex: false`
- `pipeline.workers`: logical CPU thread count for the machine
- `chunk.size: 1200`
- `chunk.overlap: 200`
- `parse.ocr_mode: auto`
- `parse.docling_mode: off`
- `embed.enabled: true`
- `enrich.enabled: false`
- `extract.enabled: false`
- `embed.device: cuda`
- `hardware.embed_batch_size: 256`
- `nightly_delta.enabled: false` unless you are intentionally running the scheduled delta lane

That matches the current large-ingest guidance in `docs/OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md` and the schema defaults in `src/config/schema.py`.

## What The GUI Actually Controls

### Source

- What it does: tells the GUI runner which file or folder to ingest for this run.
- Typical safe value: a local folder containing raw source material. Use a file only for narrow repro work.
- When to change it: every run, unless you always ingest from the same landing folder.
- Where it lives:
  - GUI widget: `src/gui/app.py:239-257`
  - Passed into the runner: `src/gui/app.py:424-429`
  - Applied to runtime config in memory only: `src/gui/launch_gui.py:392-400`
- Operator note: this field is not saved by `Save Settings`. It starts at `data/source` every GUI launch in the current build.

### Output

- What it does: chooses the parent directory where Forge creates `export_YYYYMMDD_HHMM...` packages.
- Typical safe value: a dedicated writable folder with enough free space for the export, logs, and skip manifest.
- When to change it: when switching between proof runs, production runs, or separate operators/machines.
- Where it lives:
  - GUI widget: `src/gui/app.py:259-277`
  - Passed into the runner: `src/gui/app.py:424-429`
  - Applied to runtime config in memory only: `src/gui/launch_gui.py:392-400`
  - Packager output root: `src/pipeline.py:220`
- Operator note: like `Source`, this is a per-run field. `Save Settings` does not persist it.

### Start Pipeline

- What it does: launches the background pipeline thread using the current path boxes plus the current settings-panel values.
- Typical safe use: after `Run Precheck` on large ingests.
- When to change it: not a persistent setting; this is the run trigger.
- Where it lives: `src/gui/app.py:283-287`, `src/gui/app.py:375-429`, `src/gui/launch_gui.py:612-615`.

### Run Precheck

- What it does: runs the workstation precheck tool against the current source/output/settings before you start a large run.
- Typical safe use: always use it before a large ingest or after changing workers, OCR mode, or output/state paths.
- When to change it: not a setting; run it before riskier jobs.
- Where it lives:
  - GUI button: `src/gui/app.py:289-293`
  - Precheck runner command wiring: `src/gui/launch_gui.py:339-353`
  - Actual precheck checks: `tools/precheck_workstation_large_ingest.py:95-177`, `tools/precheck_workstation_large_ingest.py:241-270`

### Stop Safely

- What it does: requests a cooperative stop. Forge stops admitting new work, finishes the current safe boundary, and either packages valid completed work or exits with no export if nothing packageable exists yet.
- Typical safe use: use it for operator stop, not as a pause.
- When to change it: not a persistent setting; this is the live stop control.
- Where it lives: `src/gui/app.py:295-299`, `src/gui/app.py:431-444`, `src/gui/launch_gui.py:405`, `src/gui/launch_gui.py:551-557`.

### Save Settings

- What it does: writes the settings-panel values back to `config/config.yaml` and updates the live config object.
- Typical safe use: after changing worker count, OCR mode, chunking, or stage toggles that you want to keep for later runs.
- When to change it: whenever you want the next GUI launch or headless run to inherit the same settings.
- Where it lives:
  - Validation and payload: `src/gui/settings_panel.py:186-249`
  - Actual file write and live config update: `src/gui/launch_gui.py:61-72`, `src/gui/launch_gui.py:646-663`
- Important limit: this does not save `Source`, `Output`, `state_db`, `full_reindex`, `defer_extensions`, `docling_mode`, or nightly settings.

### Reset To Defaults

- What it does: reloads control values from `config/config.yaml` into the GUI widgets.
- Typical safe use: when you have been experimenting in the GUI and want to snap back to the file-backed baseline.
- When to change it: before a production run if the controls no longer reflect what you think is in YAML.
- Where it lives: `src/gui/settings_panel.py:251-285`
- Important limit: it does not write anything until you click `Save Settings`.

## Settings Panel Fields

### Pipeline workers (`pipeline.workers`)

- What it does: controls parse-stage parallelism.
- Typical safe values: match logical CPU threads on the machine; `1` only for debugging or deterministic repro.
- When to change it: machine class changed, the box is oversubscribed, or you need to keep the workstation more interactive.
- Where it lives:
  - GUI control: `src/gui/settings_panel.py:29-55`
  - Saved by GUI: `src/gui/settings_panel.py:220-236`, `src/gui/launch_gui.py:652`
  - Schema: `src/config/schema.py:189-205`
  - Precheck warning logic: `tools/precheck_workstation_large_ingest.py:146-170`

### OCR (`parse.ocr_mode`)

- What it does: controls scanned-PDF and image OCR behavior.
- Typical safe values:
  - `auto`: normal baseline
  - `skip`: fastest text-first run when OCR is intentionally disabled
  - `force`: only for OCR-heavy proof work or when you know the corpus is mostly scans
- When to change it: OCR dependencies are missing, the corpus is mostly digital text, or you explicitly need OCR everywhere.
- Where it lives:
  - GUI control: `src/gui/settings_panel.py:57-68`
  - Schema validation: `src/config/schema.py:66-87`
  - Runtime env override and export to parser env: `src/pipeline.py:137-160`
  - PDF parser OCR gate: `src/parse/parsers/pdf_parser.py:73-77`

### Chunk size (`chunk.size`)

- What it does: target chunk length in characters before overlap and heading logic are applied.
- Typical safe values: `1200` is the current baseline; lower only for short-form or table-heavy experiments; higher only if retrieval needs larger context windows.
- When to change it: retrieval quality testing shows chunks are too short or too fragmented.
- Where it lives:
  - GUI control: `src/gui/settings_panel.py:70-84`
  - Schema: `src/config/schema.py:49-60`
  - Used by chunker: `src/pipeline.py:215-219`

### Overlap (`chunk.overlap`)

- What it does: carries some characters from one chunk into the next to reduce hard boundary loss.
- Typical safe values: `200` is the current baseline. Keep it well below chunk size.
- When to change it: chunks are losing sentence continuity at boundaries, or you need to cut index size.
- Where it lives:
  - GUI control: `src/gui/settings_panel.py:86-100`
  - Schema validation: `src/config/schema.py:52-60`
  - Used by chunker: `src/pipeline.py:215-219`

### Embedding (`embed.enabled`)

- What it does: turns vector generation on or off.
- Typical safe values:
  - `true`: normal Forge-to-V2 handoff
  - `false`: chunk-only proof or CPU-safe dry run
- When to change it: you want a chunk-only export, you are doing a parser-only proof, or GPU work is intentionally deferred.
- Where it lives:
  - GUI toggle: `src/gui/settings_panel.py:106-118`
  - Saved by GUI: `src/gui/settings_panel.py:227`, `src/gui/launch_gui.py:656`
  - Schema: `src/config/schema.py:103-128`
  - Pipeline lazy model loading: `src/pipeline.py:236-246`

### Enrichment (`enrich.enabled`)

- What it does: turns the Ollama enrichment stage on or off.
- Typical safe values:
  - `false`: normal ingest baseline unless you specifically want enriched text
  - `true`: targeted enrichment runs with Ollama available
- When to change it: you are testing retrieval lift from enriched text and Ollama is healthy.
- Where it lives:
  - GUI toggle: `src/gui/settings_panel.py:120-124`
  - GUI readiness probe: `src/gui/app.py:379-422`
  - Saved by GUI: `src/gui/settings_panel.py:228-230`, `src/gui/launch_gui.py:657-658`
  - Schema: `src/config/schema.py:129-149`
  - Pipeline pre-flight fail-loud: `src/pipeline.py:248-259`

### Entity Extraction (`extract.enabled`)

- What it does: turns the GLiNER entity extraction stage on or off.
- Typical safe values:
  - `false`: normal ingest baseline
  - `true`: later-pass extraction or explicit NER runs
- When to change it: you are intentionally producing `entities.jsonl` and have budget for the extra pass.
- Where it lives:
  - GUI toggle: `src/gui/settings_panel.py:126-130`
  - Saved by GUI: `src/gui/settings_panel.py:232-234`, `src/gui/launch_gui.py:659-660`
  - Schema: `src/config/schema.py:152-186`
  - Lazy extractor load: `src/pipeline.py:291-307`

### Enrich concurrent (`enrich.max_concurrent`)

- What it does: limits how many concurrent Ollama enrichment requests Forge will make.
- Typical safe values: `2` is the conservative baseline; `2-3` is the stated workstation range in the schema.
- When to change it: Ollama is underutilized and stable, or VRAM pressure requires fewer concurrent requests.
- Where it lives:
  - GUI control: `src/gui/settings_panel.py:136-152`
  - Saved by GUI: `src/gui/settings_panel.py:228-230`, `src/gui/launch_gui.py:658`
  - Schema: `src/config/schema.py:141-149`

### Extract batch (`extract.batch_size`)

- What it does: sets how many chunks GLiNER receives in one batch.
- Typical safe values: `16` is the schema default. Larger values can be faster but use more RAM.
- When to change it: extraction throughput needs tuning and you are actually running extraction.
- Where it lives:
  - GUI control: `src/gui/settings_panel.py:154-162`
  - Saved by GUI: `src/gui/settings_panel.py:232-234`, `src/gui/launch_gui.py:660`
  - Schema: `src/config/schema.py:175-180`
  - Extractor config wiring: `src/pipeline.py:295-305`

### Embed batch (`hardware.embed_batch_size`)

- What it does: operator-facing batch-size hint exposed in the GUI, saved to YAML, and used by precheck reporting.
- Typical safe values: `256` is the current conservative baseline.
- When to change it: only when you are investigating embed throughput or memory pressure.
- Where it lives:
  - GUI control: `src/gui/settings_panel.py:164-172`
  - Saved by GUI: `src/gui/settings_panel.py:236`, `src/gui/launch_gui.py:661`
  - Schema: `src/config/schema.py:286-290`
  - Precheck reporting: `tools/precheck_workstation_large_ingest.py:172-176`, `tools/precheck_workstation_large_ingest.py:253-264`
- Important current limitation: the embedder's live batch manager still reads `HYBRIDRAG_EMBED_BATCH` from the environment and defaults to `256`, rather than reading `hardware.embed_batch_size` directly. Code: `src/embed/embedder.py:61-64`. In practice, leaving both at `256` is safe. Treat changes here as an operator hint until runtime wiring is unified.

## YAML-Only Settings That Still Matter

### State DB (`paths.state_db`)

- What it does: stores durable file hash state and processing status for restart safety and incremental skip.
- Typical safe value: one stable SQLite file per corpus lane or experiment lane.
- When to change it: you want a clean continuity boundary, a new corpus lane, or a totally separate proof run.
- Where it lives:
  - Schema: `src/config/schema.py:35-38`
  - Path resolution: `src/config/schema.py:365-384`
  - Hasher creation: `src/pipeline.py:196`, `src/gui/launch_gui.py:246`
- Operator note: this is not a GUI settings-panel field.

### Full reindex (`pipeline.full_reindex`)

- What it does: bypasses the unchanged/duplicate skip in dedup so Forge reprocesses all discovered files.
- Typical safe value: `false`.
- When to change it: parser rules changed, chunking rules changed, or you intentionally want a rebuild from the same source tree.
- Where it lives:
  - Schema: `src/config/schema.py:192-205`
  - CLI flag: `scripts/run_pipeline.py:105-109`, `scripts/run_pipeline.py:155-156`
  - Runtime effect: `src/pipeline.py:350-365`
- Important nuance: `full_reindex: true` does not bypass the later skip/defer stage. Files can still be deferred or skipped after dedup.

### Defer extensions (`parse.defer_extensions`)

- What it does: hashes and accounts for selected extensions without parsing them in this run.
- Typical safe value: dotted lowercase extensions only, limited to formats you intentionally want to push out of the parser lane.
- When to change it: you know a family is low-value for this run, too expensive, or intentionally reserved for another workflow.
- Where it lives:
  - Schema and normalization: `src/config/schema.py:76-100`
  - Current runtime merge with skip rules: `src/pipeline.py:192-203`, `src/gui/launch_gui.py:447-449`, `scripts/run_pipeline.py:163`
  - Operator visibility in GUI log: `src/gui/launch_gui.py:495-503`
- Operator note: deferred files remain visible in `skip_manifest.json`; they are not silently discarded.

### Docling mode (`parse.docling_mode`)

- What it does: enables the optional Docling conversion lane for PDFs and image-like docs.
- Typical safe values:
  - `off`: normal baseline
  - `fallback`: only try Docling when other extraction is weak
  - `prefer`: try Docling first
- When to change it: you are explicitly testing Docling fidelity and the dependency is installed.
- Where it lives:
  - Schema validation: `src/config/schema.py:71-95`
  - Runtime env resolution: `src/pipeline.py:144-150`
  - Docling mode reader: `src/parse/parsers/docling_bridge.py:25-35`
  - PDF parser usage: `src/parse/parsers/pdf_parser.py:51-71`
- Personal/dev-only note: this is not exposed in the GUI settings panel and is best treated as a deliberate developer or trial setting.

### Parse timeout (`parse.timeout_seconds`)

- What it does: caps per-file parser time before the watchdog treats a parser as hung.
- Typical safe values: default `60`. Raise only for known slow but legitimate formats.
- When to change it: false timeouts on large parseable documents, or you need a tighter runaway cap.
- Where it lives:
  - Schema: `src/config/schema.py:66`
  - Dispatcher wiring: `src/pipeline.py:209-214`

### Max chars per file (`parse.max_chars_per_file`)

- What it does: clamps extremely large extracted text before chunking.
- Typical safe values: default `5_000_000`.
- When to change it: extreme long-form documents are truncating too early or memory pressure requires a tighter cap.
- Where it lives:
  - Schema: `src/config/schema.py:75`
  - Dispatcher wiring: `src/pipeline.py:209-214`

### Embed device (`embed.device`)

- What it does: requests CUDA or CPU for embedding.
- Typical safe values:
  - `cuda`: baseline on GPU workstations
  - `cpu`: fallback or proof mode only
- When to change it: no usable GPU is available or you are intentionally testing CPU behavior.
- Where it lives:
  - Schema validation: `src/config/schema.py:112-128`
  - Embedder init path: `src/embed/embedder.py:72-85`

### Embed token budget (`embed.max_batch_tokens`)

- What it does: limits token budget per embedding batch before the batch manager splits work.
- Typical safe value: default `49152`.
- When to change it: only for embedder performance experiments or repeated OOM investigations.
- Where it lives:
  - Schema: `src/config/schema.py:116-124`
  - Embedder batch manager config: `src/embed/embedder.py:61-64`
- Developer note: this is a low-level tuning field, not a normal operator knob.

### GPU index (`hardware.gpu_index`)

- What it does: schema-level GPU hint.
- Typical safe value: leave the default alone unless the runtime wiring is intentionally changed.
- When to change it: only if code is later updated to honor it directly.
- Where it lives:
  - Schema: `src/config/schema.py:286-290`
  - Printed by boot validation: `scripts/boot.py:42`
- Important current limitation: the live launcher chooses the least-used GPU with `apply_gpu_selection()` and sets `CUDA_VISIBLE_DEVICES`; it does not read `hardware.gpu_index`. Code: `src/gpu_selector.py:18-74`, `src/gui/launch_gui.py:601-603`, `scripts/run_pipeline.py:152`.

## Nightly / Delta Settings

These are operator-facing only if you run the scheduled delta lane. They are not part of the main GUI settings panel.

### `nightly_delta.enabled`

- What it does: marks the nightly delta lane as active in the runtime config.
- Typical safe value: `false` for normal ad hoc GUI runs.
- When to change it: only when you are using the nightly delta scripts.
- Where it lives: `src/config/schema.py:208-213`, `config/config.yaml`, `scripts/run_nightly_delta.py:111`.

### `nightly_delta.source_root` and `nightly_delta.mirror_root`

- What they do: define the upstream source to scan and the local mirror root that receives copied delta files.
- Typical safe values: machine-local absolute or repo-relative paths, never hidden shortcuts.
- When to change them: new source share, new mirror location, or new machine.
- Where they live:
  - Schema: `src/config/schema.py:212-219`
  - Path resolution: `src/config/schema.py:385-402`
  - Nightly runner: `scripts/run_nightly_delta.py:121-124`

### `nightly_delta.transfer_state_db`

- What it does: stores source-scan and mirror-resume state for the nightly lane.
- Typical safe value: a dedicated SQLite file separate from the main pipeline state DB.
- When to change it: separate nightly lanes or separate machines.
- Where it lives: `src/config/schema.py:220-223`, `scripts/run_nightly_delta.py:126-139`.

### `nightly_delta.manifest_dir` and `nightly_delta.pipeline_log_dir`

- What they do: collect scan manifests, transfer manifests, reports, input lists, and log files.
- Typical safe values: dedicated folders under `data/nightly_delta` and `logs/nightly_delta`.
- When to change them: if you want another artifact root or separate proof runs from production-like runs.
- Where they live: `src/config/schema.py:224-239`, `scripts/run_nightly_delta.py:124-150`.

### `nightly_delta.pipeline_output_dir` and `nightly_delta.pipeline_state_db`

- What they do: optionally override the normal Forge export root and state DB for nightly runs.
- Typical safe values: leave unset to inherit normal pipeline paths unless you intentionally want nightly isolation.
- When to change them: nightly lane must not share the same output or continuity DB as daytime work.
- Where they live:
  - Schema: `src/config/schema.py:228-235`
  - Resolver: `scripts/run_nightly_delta.py:110-114`
  - Applied to pipeline config copy: `scripts/run_nightly_delta.py:235-239`

### `nightly_delta.stop_file`

- What it does: sentinel file path that requests a clean stop at the next stage boundary.
- Typical safe value: a stable repo-local path.
- When to change it: only if your scheduler or operator tooling expects another sentinel location.
- Where it lives: `src/config/schema.py:240-243`, `scripts/run_nightly_delta.py:30-56`, `scripts/run_nightly_delta.py:127-130`.

### `nightly_delta.transfer_workers`

- What it does: parallel copy worker count for source-to-mirror transfer.
- Typical safe values: `4-8` unless copy throughput testing justifies more.
- When to change it: transfer lane is bottlenecked or source/destination storage cannot sustain the current concurrency.
- Where it lives: `src/config/schema.py:244-249`, `scripts/run_nightly_delta.py:191-207`.

### `nightly_delta.canary_globs` and `nightly_delta.require_canary`

- What they do: define canary filename patterns and optionally fail the run if no canary file appears in the detected delta set.
- Typical safe value: `require_canary: false` until your process truly depends on that gate.
- When to change them: you are formalizing canary discipline for the nightly lane.
- Where they live: `src/config/schema.py:250-257`, `scripts/run_nightly_delta.py:169-175`.

### `nightly_delta.max_files`

- What it does: caps the delta file count for proof runs.
- Typical safe value: unset for real nightly operations.
- When to change it: you want a controlled proof or smoke run.
- Where it lives: `src/config/schema.py:258-262`, `scripts/run_nightly_delta.py:156-159`.

### `nightly_delta.task_name` and `nightly_delta.task_start_time`

- What they do: feed the scheduled-task installer with the Windows task name and daily start time.
- Typical safe values: human-readable task name and an off-hours `HH:MM` time such as `02:00`.
- When to change them: scheduler naming or start window changes.
- Where they live:
  - Schema and time validation: `src/config/schema.py:263-283`
  - Install helper: `scripts/install_nightly_delta_task.py:79-89`

## Developer / Operator Boundary Notes

### GUI settings panel vs YAML file

The settings panel covers only:

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

Code: `src/gui/settings_panel.py:220-236`.

That means the following still require YAML or CLI changes:

- `paths.state_db`
- `pipeline.full_reindex`
- `parse.docling_mode`
- `parse.defer_extensions`
- `parse.timeout_seconds`
- `embed.device`
- all `nightly_delta.*` settings

### Source/Output path truth

The main GUI path boxes are run-time inputs. The runner copies them into `config.paths.source_dirs` and `config.paths.output_dir` only after you click `Start Pipeline`. Code: `src/gui/launch_gui.py:392-400`.

For headless use, `load_config()` resolves the YAML paths before runtime. Code: `src/config/schema.py:345-406`.

### Remote-safe vs personal/dev-only

Treat these as normal operator settings:

- `output_dir`
- `state_db`
- `full_reindex`
- `workers`
- `chunk size`
- `overlap`
- `embed.enabled`
- `enrich.enabled`
- `extract.enabled`
- `defer_extensions`
- nightly delta paths and canary rules

Treat these as personal/dev-only or trial settings unless there is a specific reason:

- `parse.docling_mode`
- parser env overrides (`HYBRIDRAG_OCR_MODE`, `HYBRIDRAG_DOCLING_MODE`)
- `embed.max_batch_tokens`
- `hardware.gpu_index` in the current codebase

## Forge To V2 Handoff Boundary

Forge writes export packages under the chosen output root. V2 then imports the completed export as a separate step.

Relevant V2 config anchors:

- `paths.embedengine_output`: where V2 expects Forge export packages to live (`C:\\HybridRAG_V2\\src\\config\\schema.py:35-38`)
- `paths.lance_db`: vector/BM25 store root (`C:\\HybridRAG_V2\\src\\config\\schema.py:27-30`)
- `paths.entity_db`: validated entity store (`C:\\HybridRAG_V2\\src\\config\\schema.py:31-34`)
- V2 path resolution: `C:\\HybridRAG_V2\\src\\config\\schema.py:165-190`

Operator rule: hand off the whole `export_YYYYMMDD_HHMM...` folder, not individual files.

## Recommended QA Checks For This Reference

1. Confirm the doc matches the actual current GUI controls in `src/gui/app.py` and `src/gui/settings_panel.py`.
2. Confirm every YAML-only item listed here is still YAML-only.
3. Confirm the two current runtime caveats are still true:
   - `hardware.embed_batch_size` is not yet wired directly into `src/embed/embedder.py`
   - `hardware.gpu_index` is not the active GPU selector in the current launcher path

Signed: Agent 4 | Lane 3
