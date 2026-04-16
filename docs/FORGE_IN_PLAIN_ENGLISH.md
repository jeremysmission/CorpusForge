# CorpusForge in Plain English

**Audience:** operators, PMs, reviewers, or anyone who has to touch Forge without reading the source code.
**Date:** 2026-04-13 MDT
**Author:** CoPilot+ | Jeremy Randall

---

## What is CorpusForge?

CorpusForge (Forge for short) is the **ingest pipeline** for HybridRAG V2. Its job is to take a pile of raw documents — PDFs, Word docs, spreadsheets, images, email exports, ZIP archives, scanned reports — and turn them into a clean, searchable package that HybridRAG V2 can load and query.

Think of it like a lumber mill:

- **Input:** a source folder full of mixed-format files (the "logs")
- **Output:** a neat, labeled export folder of chunks + vectors + manifests (the "finished boards")
- **HybridRAG V2** is the carpenter that builds answers out of those boards

Forge does not answer questions. V2 does. Forge just makes sure V2 has good raw material.

---

## What Forge does, in order

1. **Hash** every file so we can tell which ones we've seen before.
2. **Dedup** so the same file at two paths does not get processed twice.
3. **Skip / defer** anything the skip list says to ignore (e.g., CAD files, SAO ionograms).
4. **Parse** each file with the right parser (PDF, DOCX, XLSX, image OCR, archive unzip, etc.).
5. **Chunk** the parsed text into retrieval-sized pieces.
6. **Enrich** the chunks with optional contextual text (can be off).
7. **Embed** each chunk on the GPU into a 768-dimensional vector with the `nomic-embed-text` model.
8. **Extract** optional entities with GLiNER (can be off).
9. **Export** everything into a timestamped folder that V2 knows how to read.

Stages 6 and 8 are optional. Stages 1–5, 7, and 9 always run when you do a full ingest.

---

## What Forge outputs for V2

Every successful run produces a folder like:

```
C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM\
    chunks.jsonl      — one JSON row per chunk (text, source_path, chunk_id, ...)
    vectors.npy       — float16 numpy array, shape [num_chunks, 768]
    entities.jsonl    — optional, only when entity extraction is enabled
    manifest.json     — counts, model name, timestamps, status
    skip_manifest.json — what was skipped or deferred and why
```

A `latest` symlink/junction points at the most recent successful export. V2's importer reads from either the explicit timestamped folder or from `latest`.

The current canonical export used by V2 is:

```
C:\CorpusForge\data\production_output\export_20260409_0720
```

---

## What is manual vs automatic

### Automatic (Forge does this for you)

- Hashing, dedup, skip checks, parse, chunk, embed, export, checkpointing
- GPU selection when `CUDA_VISIBLE_DEVICES` is set
- Resume from a partial run if a checkpoint is present
- Skip-list enforcement and archive defer-token matching
- Writing `manifest.json` and `skip_manifest.json`

### Manual (you do this)

- Staging the source folder into `C:\CorpusForge\ProductionSource\verified\source` (or pointing Forge at the right input folder in the GUI).
- Running `PRECHECK_WORKSTATION_700GB.bat` before a large ingest so you know OCR tools are wired up and disk is sufficient.
- Editing `config\config.yaml` if you need to change workers, batch sizes, or enable/disable enrichment or extraction.
- Starting the run (GUI or CLI).
- Handing the resulting export folder to the V2 side via `scripts\stage_forge_import.py` in the V2 repo.
- Installing **Tesseract** and **Poppler** if you want image OCR and scanned-PDF OCR (see the OCR section below).

---

## Installation and setup — the short version

1. Clone CorpusForge to `C:\CorpusForge`.
2. From the repo root, run `INSTALL_WORKSTATION.bat`. This calls `tools\setup_workstation_2026-04-06.ps1`, creates `.venv`, installs Python dependencies, and prints an OCR readiness summary.
3. Run the preflight: `PRECHECK_WORKSTATION_700GB.bat`. Expect `RESULT: PASS`. Warnings about scanned-PDF OCR are survivable; failures are not.
4. Open the GUI (`start_corpusforge.bat`) or use the CLI entrypoints under `scripts\` to kick off a run.

The installer and precheck are the two gates. If either one is unhappy, fix it before you start a large ingest — you will lose hours otherwise.

---

## OCR on this workstation (important gotcha)

Forge supports OCR for two cases:

1. **Image files** (`.jpg`, `.png`, etc.) — handled by Tesseract.
2. **Scanned PDFs** — handled by Tesseract **plus** Poppler's `pdftoppm.exe` (to rasterize pages first).

On this machine:

- **Tesseract** is typically installed at `C:\Program Files\Tesseract-OCR\tesseract.exe` and may be off-PATH. Forge resolves it through the `TESSERACT_CMD` env var, PATH, or a known fallback path, so image OCR works even when `where.exe tesseract` returns nothing.
- **Poppler** may not be installed. If `pdftoppm.exe` cannot be found, scanned-PDF OCR is unavailable and those files fall back to non-OCR parsing. The precheck will emit a clear WARNING for this case — it is not a crash, but it is a quality hit on scanned corpora.

To fix scanned-PDF OCR, install Poppler and either:

- place it on PATH, or
- set `HYBRIDRAG_POPPLER_BIN` to the directory containing `pdftoppm.exe`.

Then re-run the precheck.

---

## Navigating from zero to a successful run

If you are brand new, follow the breadcrumb trail:

1. [`___OnboardingInfo_2026_04_09.md`](../___OnboardingInfo_2026_04_09.md) — repo roots, canonical config, and the read-order for current truth docs.
2. [`docs/OPERATOR_QUICKSTART.md`](OPERATOR_QUICKSTART.md) — CLI / GUI / nightly usage.
3. [`docs/MORNING_OPERATOR_QUICKSTART_2026-04-09.md`](MORNING_OPERATOR_QUICKSTART_2026-04-09.md) — short version for a normal work morning.
4. [`PRECHECK_WORKSTATION_700GB.bat`](../PRECHECK_WORKSTATION_700GB.bat) — the one-click environment check before a large run.
5. [`src/pipeline.py`](../src/pipeline.py) — the orchestrator. Read the class docstring at line ~175 (`class Pipeline`) for the stage-by-stage architecture.
6. [`src/export/packager.py`](../src/export/packager.py) — exactly what files land in the export folder and in what format.
7. [`docs/FORGE_V2_METADATA_CONTRACT_2026-04-12.md`](FORGE_V2_METADATA_CONTRACT_2026-04-12.md) — the contract between Forge exports and V2 ingest. Read this if you are adding fields or debugging import mismatches.

For the V2 side of the handoff:

- `C:\HybridRAG_V2\scripts\stage_forge_import.py` — the **preferred** operator path from a Forge export into V2.
- `C:\HybridRAG_V2\docs\V2_STAGING_IMPORT_RUNBOOK_2026-04-09.md` — the runbook for that staging script.

---

## Common things people get wrong

1. **Editing the wrong config.** The live runtime config is `C:\CorpusForge\config\config.yaml`. `config.local.yaml` is not part of the live path anymore. The GUI "Save Settings" button writes to `config.yaml` directly.
2. **Running from a clone.** Any `C:\Users\jerem\codex_tmp\...` copy of CorpusForge is a study or recovery clone, not canonical. Edits there do not land.
3. **Skipping the precheck.** It takes under a minute and will save hours if OCR or disk is broken.
4. **Assuming Poppler is installed.** It frequently is not. Check the precheck output, not assumptions.
5. **Running in the wrong Python.** Use the repo-local `.venv\Scripts\python.exe`, never the system Python. QA and local validation require the repo-local venv.
6. **Confusing the GUI settings persistence.** Settings persist to `config\config.yaml`. Close the GUI before editing the file by hand.

---

## What Forge is not

- Not a search engine. It does not answer questions.
- Not a vector database. It writes `vectors.npy`; LanceDB lives in V2.
- Not a retrieval system. It does not rank, rerank, or route.
- Not a web service. It is a local pipeline driven by CLI or a desktop GUI.
- Not a production deployment target. It is a local workstation ingest stage.

Its one job is **producing a clean, inspectable, reproducible export folder** that V2 can consume.

---

## One-line summary

> Forge converts a folder of messy documents into a labeled export (`chunks.jsonl` + `vectors.npy` + manifests) that HybridRAG V2 imports to power retrieval and answer generation.

---

Signed: CoPilot+ | CorpusForge | 2026-04-13 MDT
