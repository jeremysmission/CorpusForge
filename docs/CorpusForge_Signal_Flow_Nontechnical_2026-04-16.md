# CorpusForge — Signal Flow, Module To Module (Non-Technical)

**Author:** CoPilot+ | Jeremy Randall
**Date:** 2026-04-16 MDT
**Audience:** managers, PMs, executives, reviewers — people who need to understand what Forge does without reading code
**Format:** chalkboard walkthrough, front-of-room style
**Companion doc:** `CorpusForge_Signal_Flow_Technical_2026-04-16.md`

---

## Before The Walkthrough — The One-Sentence Version

> CorpusForge takes a folder of messy documents and hands back a clean, searchable package that HybridRAG V2 uses to answer questions. Forge is the **lumber mill**. V2 is the **carpenter**.

If you only remember one slide, remember that one.

---

## Block Diagram — The Whole Thing On One Chalkboard

```
                            OPERATOR
                 (clicks Start in GUI, or runs CLI)
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   LAUNCH + CONFIG                │
             │   start_corpusforge.bat          │
             │   GUI app  OR  run_pipeline.py   │
             │   config.yaml is read            │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   GPU SELECTOR                   │
             │   picks which graphics card      │
             │   the math will run on           │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   PIPELINE CONDUCTOR             │
             │   (src/pipeline.py)              │
             │   runs the 9 stages in order     │
             └──────────────────────────────────┘
                              │
   ┌──────────────────────────┼──────────────────────────┐
   ▼                          ▼                          ▼
 STAGE 1                   STAGE 2                    STAGE 3
 HASH                      DEDUP                      SKIP / DEFER
 fingerprint every         drop copies of the         drop or delay
 file                      same content               formats we don't
                                                      handle today
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   STAGE 4 — PARSE                │
             │   one reader per file format     │
             │   PDF, Word, Excel, email,       │
             │   images (OCR), ZIP, CAD, etc.   │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   STAGE 5 — CHUNK                │
             │   cut clean text into            │
             │   retrieval-sized pieces         │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   CHECKPOINT (safety net)        │
             │   write parsed + chunked state   │
             │   to disk so a crash doesn't     │
             │   lose hours of work             │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   STAGE 6 — ENRICH (optional)    │
             │   add context around each chunk  │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   STAGE 7 — EMBED                │
             │   turn each chunk into a         │
             │   768-number "meaning" vector    │
             │   on the GPU                     │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   STAGE 8 — EXTRACT (optional)   │
             │   pull named entities out of     │
             │   each chunk                     │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   STAGE 9 — EXPORT               │
             │   write the clean package:       │
             │   chunks.jsonl                   │
             │   vectors.npy                    │
             │   manifest.json                  │
             │   skip_manifest.json             │
             └──────────────────────────────────┘
                              │
                              ▼
             ┌──────────────────────────────────┐
             │   HAND-OFF TO HYBRIDRAG V2       │
             │   V2's importer reads this       │
             │   folder and builds the          │
             │   search index                   │
             └──────────────────────────────────┘
                              │
                              ▼
                    OPERATOR SEES "DONE"
              (stats panel + export folder +
               skip manifest they can review)
```

---

## The Walkthrough — Module By Module, As If Drawn On A Chalkboard

*Imagine me at the board with a marker. I draw each box as I describe it.*

### 1. The Operator Pushes A Button

Everything starts with an operator at a workstation. They either:

- Click **Start** in the Forge desktop GUI, or
- Run a command-line script for overnight / scheduled jobs

That button press is the "query" — the request that says *"go turn this folder of documents into something V2 can use."*

*(Draws: a stick figure, an arrow pointing to the first box.)*

### 2. Launch + Config — "What Are The Rules Today?"

The launcher reads one single file: `config\config.yaml`. That file answers:

- Which folder holds the source documents?
- Where should the finished export go?
- How many workers can run in parallel?
- Is enrichment on? Is entity extraction on?
- What formats are we deferring today?

Think of this as the **rules sheet** for this specific run. No code needs to change between runs — the operator just edits the rules sheet.

### 3. GPU Selector — "Which Engine Are We Using?"

Forge does heavy math in Stage 7 (Embed). That math wants to run on a graphics card (GPU), not the main CPU, because the GPU is roughly 50–100× faster at it.

The GPU selector picks which card to use and pins the run to it. On the Beast workstation there are two GPUs — one is kept free for the desktop, the other does the work.

### 4. The Conductor — `src/pipeline.py`

This is the single module that runs the show. Every other module is a station on the assembly line. The conductor calls each station in order, passes results from one to the next, and keeps score.

If something goes wrong, this module is who decides: keep going, stop gracefully, or crash loudly.

### 5. Stage 1 — Hash (Fingerprint Every File)

The pipeline walks the source folder and fingerprints every file it finds. Think of it like giving every file a unique barcode based on its contents. Two files with the same contents — even if they have different names or sit in different folders — get the same barcode.

This is what makes Stage 2 possible.

### 6. Stage 2 — Dedup (Drop The Copies)

We get massive corpus shipments. People email the same contract around three times. People save a file in three formats. We do **not** want to embed the same contract three times because then search results will show three copies of everything.

The dedup module uses those fingerprints from Stage 1 and says: *"I've already seen this one — skip it."*

### 7. Stage 3 — Skip / Defer (Drop What We Can't Handle Today)

Not every file deserves to go into the V2 search index. Skip rules say things like:

- Password-protected files → skip (can't read them)
- CAD drawings → defer (we'll handle them in a later release)
- Temp files, lock files, corrupted files → skip (noise)

Every skipped or deferred file gets written to `skip_manifest.json` so the operator can see what was held back and why. Nothing silently vanishes.

### 8. Stage 4 — Parse (Read The Documents)

This is the biggest and most varied part of the system. Forge has a different reader for every common file format:

- **PDF parser** — real text first; if it's a scanned PDF, OCR it with Tesseract + Poppler
- **Word parser** (.docx, .doc, .rtf, .odt) — native reader with three-strategy fallbacks
- **Spreadsheet parser** (.xlsx, .xls, .csv) — sheet by sheet
- **Slide parser** (.pptx, .ppt) — one slide per chunk
- **Email parser** (.eml, .msg, .mbox) — body + attachments + thread metadata
- **Image parser** — OCR first; falls back to metadata if there's no readable text
- **Archive parser** (ZIP, TAR, 7z) — unwraps safely, defers members that are too big or too deep
- **Web / structured parser** (HTML, JSON, XML)
- **Placeholder parser** — everything else gets recorded as "seen but not yet supported"

A traffic cop called `dispatcher.py` picks the right reader for each file based on its extension.

A separate `quality_scorer.py` rates how clean the result is. A bad score can flag a file for review without blocking the run.

### 9. Stage 5 — Chunk (Cut Into Retrieval-Sized Pieces)

A 500-page PDF is too big to search as one piece. Forge cuts each document into overlapping chunks — roughly the size of a few paragraphs — so V2 can find the relevant passage instead of the relevant 500 pages.

Each chunk gets a stable ID so V2 can trace any search hit back to the original document, page, and position.

### 10. The Checkpoint (Safety Net Between Stages)

Here's a story: the team lost a 700GB ingest because the pipeline crashed *after* parsing but *before* saving final output. All that work was gone.

Forge now writes a **checkpoint** after Stage 5 — a durable snapshot of the parsed and chunked state. If a crash or stop happens later, the next run resumes from the checkpoint instead of re-parsing everything. On a big run, that's the difference between losing an hour and losing an overnight.

### 11. Stage 6 — Enrich (Optional)

Optional step that adds a short context window around each chunk — helps V2 understand a chunk that reads like "and then we shipped them" by attaching surrounding sentences so it knows *what* "them" refers to.

Off by default for speed. Operators flip it on for higher-quality corpora.

### 12. Stage 7 — Embed (The GPU Heavy Lifting)

This is the part that actually needs the GPU. Forge runs every chunk through a model called **nomic-embed-text**. For each chunk it produces a list of 768 numbers. Those 768 numbers are the chunk's "meaning fingerprint."

Two chunks about the same topic get similar number lists, even if they use different words. This is what makes V2's search *semantic* instead of *keyword-only*.

The batch manager packs many chunks into one GPU call for speed, and backs off automatically if memory gets tight.

### 13. Stage 8 — Extract (Optional)

Optional step that pulls out named entities — people, companies, contracts, part numbers — using a model called GLiNER. Useful for structured filtering later (e.g., "only logistics documents from 2024").

Off by default. Extra cost, only worth it for high-value corpora.

### 14. Stage 9 — Export (Hand V2 The Finished Boards)

The final station. It writes a timestamped folder containing:

- **`chunks.jsonl`** — every chunk with its text, source path, chunk ID, and metadata
- **`vectors.npy`** — a tight array of all the 768-number vectors
- **`manifest.json`** — run summary: counts, timestamps, model name, status
- **`skip_manifest.json`** — everything skipped or deferred, with reason

A `latest` shortcut points at the newest successful export.

### 15. Hand-Off Back To The Operator (And To V2)

Two things happen at the end:

1. The **operator** sees the run finish in the GUI. The stats panel shows totals (files parsed, chunks made, vectors written). They can open the export folder, open the manifest, open the skip manifest, and spot-check anything that looks off.
2. The **V2 importer** (a separate tool that lives in the HybridRAG V2 repo) reads the export folder and loads those vectors into the V2 search index. From that point on, V2 can answer questions against this corpus.

This is the "back to query" moment. The operator asked *"process this folder"* and now holds a clean, inspectable export plus a search index that can be queried.

---

## Two Modules I Haven't Drawn Yet (Off To The Side)

These don't run during a normal ingest but matter for operations.

### Nightly Delta Lane — `scripts/nightly_delta_ingest.py`

A scheduled overnight job that only processes *new or changed* files since the last run. Saves hours on large corpora that only gain a few files a day.

### Analysis Toolkit — `src/analysis/*` + `scripts/audit_corpus.py`

Run-after-the-fact tools an operator uses to:

- Profile what's actually in the source corpus before a big run
- Audit a finished export for integrity
- Confirm the export follows the V2 metadata contract

Think of these as **inspection tools**, not assembly-line stations.

---

## How To Read A Live Run

When an operator watches the GUI during a run, they see:

1. **"Hashing…"** → Stage 1
2. **"Dedup…"** → Stage 2
3. **"Skip/defer decisions made"** → Stage 3, with `skip_manifest.json` building up
4. **"Parsing N of M files"** → Stage 4, longest visible phase
5. **"Chunking…"** → Stage 5
6. **"Checkpoint written"** → the safety net
7. **"Embedding on GPU N"** → Stage 7, GPU memory spikes, nvidia-smi shows usage
8. **"Writing export…"** → Stage 9
9. **"Done. Export at C:\CorpusForge\data\production_output\export_YYYYMMDD_HHMM"**

If any stage fails, the GUI shows **where** and **why**, and the checkpoint file is preserved so the operator can rerun without losing the earlier work.

---

## The Three Things I Want A Manager To Walk Away With

1. **Forge is deterministic and inspectable.** Every decision (skip, defer, parse, embed) leaves a manifest entry. There's no black box.
2. **Forge is resumable.** The checkpoint between Stages 5 and 7 means an overnight crash doesn't cost the whole night.
3. **Forge doesn't answer questions — V2 does.** Forge's only job is to produce a clean, labeled export. The minute an export is written, Forge is done and V2 takes over.

---

Signed: CoPilot+ | CorpusForge | 2026-04-16 MDT
