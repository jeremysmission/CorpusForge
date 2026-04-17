# CorpusForge — Design Proposal

**Author:** Jeremy Randall (CoPilot+)
**Repo:** CorpusForge
**Date:** 2026-04-04 MDT
**Companion to:** HybridRAG_V2 (query plane)
**Role:** Nightly ingest plane — forges raw documents into query-ready artifacts

---

## 1. Executive Summary

CorpusForge is a standalone application that transforms raw source documents (PDFs, spreadsheets, emails, presentations, scanned images, and 30+ other formats) into structured, enriched, indexed artifacts ready for consumption by HybridRAG V2.

It runs nightly on a dedicated GPU workstation. Operators never interact with it directly — it is fully automated, scheduled, and self-recovering.

**What it produces:**
- Chunked text passages with contextual enrichment
- 768-dimensional embedding vectors (nomic-embed-text v1.5)
- First-pass entity extraction results (GLiNER2)
- Export package that HybridRAG V2 imports on startup

**What it replaces:**
- V1's monolithic indexer (embedded inside the query app)
- V1's mixed embedding backends (CUDA → ONNX → Ollama fallback chain)
- V1's nonexistent enrichment and entity extraction

---

## 2. Why a Separate Application?

V1 combined indexing and querying in one app. This caused:

1. **Daytime indexing competed with queries** — GPU memory contention, latency spikes
2. **Config complexity** — offline/online mode switching, 6 user modes, embedder fallback chains
3. **Deployment coupling** — can't update the indexer without redeploying the query app
4. **Testing difficulty** — can't test indexing quality without booting the full query pipeline

CorpusForge eliminates all four problems by running as a separate process on a separate schedule.

---

## 3. Pipeline Architecture

```
SOURCE FILES (420K files, 700GB, 67+ formats)
       |
       v
[1] DOWNLOAD & SYNC
    Fetch new/updated files from configured network sources
    Delta detection: only download changed files
    Landing zone: data/source/
       |
       v
[2] HASH & DEDUPLICATE
    SHA-256 content hashing per file
    _1 suffix duplicate detection (54% of corpus is duplicated)
    File state tracking in SQLite (hash, mtime, size, status)
    Skip unchanged files on subsequent runs
       |
       v
[3] PARSE (32+ formats)
    Format detection → appropriate parser
    Per-file timeout: 60 seconds (configurable)
    Parse quality scoring: 0.0-1.0 per file
    OCR fallback for scanned PDFs (pytesseract + Poppler)
    Error isolation: single file failure never crashes pipeline
       |
       v
[4] CHUNK
    Fixed-size: 1200 characters, 200 character overlap
    Smart boundary: split at sentence boundaries, not mid-word
    Deterministic IDs: SHA-256(file_path + chunk_index)
    INSERT OR IGNORE: crash-safe resume, no duplicates
       |
       v
[5] CONTEXTUAL ENRICHMENT
    phi4:14B (local GPU, free, unlimited)
    Prepends document-level context to each chunk:
    "[From: {filename}, Section: {heading}, Topic: {summary}]"
    Published research: up to 67% retrieval failure reduction
    Incremental: only enrich new/changed chunks
       |
       v
[6] EMBED
    nomic-embed-text v1.5 (768 dimensions)
    CUDA backend (primary) with ONNX CPU fallback
    Token-budget batching: dynamic batch sizing for GPU memory
    OOM backoff: automatic batch size reduction on GPU OOM
    Output: float16 vectors (50% storage savings)
       |
       v
[7] FIRST-PASS ENTITY EXTRACTION
    GLiNER2 (205M params, CPU, zero-shot NER)
    Extracts: part numbers, people, sites, dates, organizations, failure modes
    Outputs candidate entities with confidence scores
    Does NOT validate or normalize — that's HybridRAG V2's job
       |
       v
[8] EXPORT
    Package written to configured output directory:
    - chunks.jsonl        (text, metadata, enriched_text, source_path)
    - vectors/            (768-dim float16, LanceDB-ready format)
    - entities.jsonl      (GLiNER2 first-pass candidates)
    - manifest.json       (chunk count, model versions, timestamp, run stats)
    - run_report.json     (files processed, skipped, failed, timing)
```

---

## 4. Reuse from V1

CorpusForge reuses significant code from HybridRAG3_Educational:

| V1 Module | V1 Location | CorpusForge Reuse | Notes |
|---|---|---|---|
| 32 file parsers | `src/core/indexer.py` (inline) | `src/parse/parsers/` (split out) | Each parser becomes its own file, <500 lines |
| Chunker | `src/core/chunker.py` | `src/chunk/chunker.py` | Copy with minor cleanup |
| Embedder (CUDA tier) | `src/core/embedder.py` | `src/embed/embedder.py` | Keep CUDA + ONNX, drop Ollama |
| Token-budget batching | `src/core/embedder.py` | `src/embed/batch_manager.py` | Copy as-is, battle-tested |
| OOM backoff | `src/core/embedder.py` | `src/embed/batch_manager.py` | Copy as-is |
| File hashing | `src/core/chunk_ids.py` | `src/download/hasher.py` | SHA-256 deterministic IDs |
| Parse quality scoring | `src/core/indexer.py` | `src/parse/quality_scorer.py` | Split out into own module |
| OCR pipeline | `src/core/indexer.py` | `src/parse/ocr.py` | pytesseract + Poppler |

**Estimated reuse: 60-70% of CorpusForge's core logic comes from V1.** The main new work is:
- Contextual enrichment module (new)
- GLiNER2 entity extraction (new)
- Export packaging (new)
- GUI for monitoring (new, simple)
- Download/sync module (new)

---

## 5. Technology Stack

### 5.1 Carry Forward (Already Approved)

| Package | Version | License | Origin | Role |
|---|---|---|---|---|
| Python | 3.11.9 | PSF-2.0 | USA | Runtime |
| numpy | 1.26.4 | BSD-3 | USA | Vector math |
| pdfplumber | 0.11.9 | MIT | USA | PDF text extraction |
| pytesseract | 0.3.13 | Apache 2.0 | USA | OCR bridge |
| python-docx | 1.2.0 | MIT | USA | Word reader |
| openpyxl | 3.1.5 | MIT | USA | Excel reader |
| python-pptx | 1.0.2 | MIT | USA | PowerPoint reader |
| pillow | 12.1.0 | HPND | USA | Image processing |
| pydantic | 2.11.1 | MIT | USA | Config validation |
| pyyaml | 6.0.2 | MIT | USA | Config parsing |
| structlog | 24.4.0 | MIT | Germany | Logging |
| rich | 13.9.4 | MIT | UK | Console formatting |
| tqdm | 4.67.3 | MIT | USA | Progress bars |
| sqlite3 | stdlib | Public domain | USA | File state tracking |
| All 32 V1 parsers | Various | MIT/BSD/Apache | USA/UK | Document parsing |

### 5.2 Applying (YELLOW — Waiver in Progress)

| Package | Version | License | Origin | Role |
|---|---|---|---|---|
| sentence-transformers | 5.3.0 | Apache 2.0 | USA | Embedding engine |
| torch (CUDA) | 2.x | BSD-3 | USA | GPU embedding + enrichment |
| onnxruntime | 1.24.4 | MIT | Microsoft/USA | CPU embedding fallback |
| optimum | 2.1.0 | Apache 2.0 | HuggingFace/USA | ONNX bridge |
| pytest | 9.0.2 | MIT | Germany | Testing |
| psutil | 7.2.2 | BSD-3 | USA | GPU/memory monitoring |

### 5.3 New Waivers Required (1-2 packages)

| Package | Version | License | Origin | Role | Notes |
|---|---|---|---|---|---|
| gliner | latest | Apache 2.0 | France (NATO) | Zero-shot NER, first-pass | Same waiver as HybridRAG V2 |
| Ollama | latest | MIT | USA | phi4:14B host for enrichment | Already YELLOW on V1 waiver sheet |

**Note:** GLiNER waiver is shared with HybridRAG V2 — one waiver covers both repos. Ollama is already in the V1 waiver pipeline for hosting phi4:14B locally. CorpusForge may need 0-1 truly new waivers.

---

## 6. Contextual Enrichment (Key Innovation)

### 6.1 What It Does

Before embedding, each chunk gets a document-level context prefix generated by phi4:14B:

**Before enrichment:**
```
"The connector failed twice in March and once in April. Replacement ordered."
```

**After enrichment:**
```
"[From: Ascension_Maintenance_Report_2024Q1.pdf, Section 4.2 Equipment Failures,
  Topic: connector replacement history at Ascension site]
 The connector failed twice in March and once in April. Replacement ordered."
```

### 6.2 Why It Matters

- Published research shows up to 67% reduction in retrieval failures
- Solves the synonym problem: "calibration" in the query matches "alignment protocol" in the enriched context
- Solves the context loss problem: a chunk about "the connector" now specifies which connector, at which site, in which report
- Zero API cost (phi4:14B runs locally on GPU)
- Zero rate limiting (local inference, no API throttling)

### 6.3 Performance

- phi4:14B on 3090 FE (24GB VRAM): ~50-100 chunks/minute for enrichment
- Full corpus (27.6M chunks): ~5-9 days for initial enrichment
- Incremental (nightly): only new/changed files — minutes per run
- GPU memory: phi4:14B uses ~9GB VRAM, leaves room for embedding on second GPU

---

## 7. File Structure

```
CorpusForge/
  src/
    __init__.py
    config/
      __init__.py
      schema.py              # Pydantic config validation
      config.yaml            # Pipeline settings
    download/
      __init__.py
      syncer.py              # Fetch new/updated files from sources
      hasher.py              # SHA-256 content hashing
      deduplicator.py        # _1 suffix and content-hash dedup
    parse/
      __init__.py
      dispatcher.py          # Route files to correct parser
      quality_scorer.py      # Parse quality 0.0-1.0
      ocr.py                 # pytesseract + Poppler OCR pipeline
      parsers/
        __init__.py
        pdf_parser.py         # pdfplumber + OCR fallback
        docx_parser.py        # python-docx
        xlsx_parser.py        # openpyxl
        pptx_parser.py        # python-pptx
        csv_parser.py
        txt_parser.py
        msg_parser.py         # Outlook .msg
        html_parser.py
        # ... (each parser < 500 lines)
    chunk/
      __init__.py
      chunker.py             # 1200/200 fixed + sentence boundary
      chunk_ids.py           # Deterministic SHA-256 IDs
    enrich/
      __init__.py
      enricher.py            # phi4:14B contextual enrichment
      ollama_client.py       # Local Ollama API client
    embed/
      __init__.py
      embedder.py            # CUDA primary, ONNX fallback
      batch_manager.py       # Token-budget batching + OOM backoff
    extract/
      __init__.py
      ner_extractor.py       # GLiNER2 first-pass entity extraction
    export/
      __init__.py
      packager.py            # Build export package for V2
      manifest.py            # Generate manifest.json
    gui/
      __init__.py
      app.py                 # Main Tkinter monitoring app
      progress_panel.py      # Pipeline progress display
      status_panel.py        # Run status, file counts, errors
      theme.py               # Shared color scheme with V2
    pipeline.py              # Orchestrator: runs all stages in sequence
  tests/
    test_parsers.py
    test_chunker.py
    test_enricher.py
    test_embedder.py
    test_extractor.py
    test_deduplicator.py
    test_packager.py
  scripts/
    run_pipeline.py          # CLI entry point for nightly run
    run_single_file.py       # Test pipeline on one file
    audit_index.py           # "What did we process?" report
    schedule_nightly.py      # Set up Windows Task Scheduler job
  docs/
    (this document and others)
  config/
    config.yaml
  data/
    source/                  # Landing zone for downloaded files
    output/                  # Export packages for V2
  requirements.txt
  sanitize_before_push.py
  CoPilot+.md
  README.md
```

**Design rule:** Every source file < 500 lines of code (comments excluded).

---

## 8. GUI

CorpusForge has a simple Tkinter monitoring GUI (shared aesthetic with HybridRAG V2):

- **Pipeline status panel:** current stage, files processed/remaining, elapsed time
- **Progress bar:** overall completion percentage
- **Error panel:** list of files that failed parsing with error messages
- **Run history:** last 10 runs with stats (files processed, chunks created, duration)
- **Manual trigger button:** "Run Now" to start pipeline outside scheduled time
- **Config display:** shows current settings (source paths, output path, chunk size)

The GUI is for monitoring only — the pipeline runs headless via scheduled task for nightly automation.

---

## 9. Scheduling

### Windows Task Scheduler (Beast Workstation)

```
Task: CorpusForge Nightly Pipeline
Trigger: Daily at 02:00 AM
Action: python C:\CorpusForge\scripts\run_pipeline.py --config config/config.yaml
Working Dir: C:\CorpusForge
Run whether user is logged on or not: Yes
Stop task if running longer than: 12 hours
```

### Pipeline Stages Run Sequentially

```
02:00  Download & sync (minutes)
02:15  Hash & deduplicate (minutes)
02:30  Parse new files (minutes to hours, depends on volume)
04:00  Chunk (fast, minutes)
04:15  Contextual enrichment (GPU, minutes for incremental)
04:30  Embed (GPU, minutes for incremental)
05:00  Entity extraction (CPU, minutes for incremental)
05:15  Export package
05:20  Done — V2 picks up export on next startup
```

Full re-index (all 420K files): 2-4 days. Normal nightly (incremental): 30-90 minutes.

---

## 10. Deduplication Strategy

54% of the corpus consists of `_1` suffix duplicates (measured during index analysis). CorpusForge handles this at two levels:

### 10.1 Filename Deduplication

Files with identical names except for `_1` suffix are flagged:
- `Report.docx` and `Report_1.docx` — content-hash compared
- If identical hash: skip the `_1` version, log as duplicate
- If different hash: keep both (genuine revisions), flag in metadata

### 10.2 Content Deduplication

Files with identical SHA-256 content hashes are processed only once, regardless of filename or path. The second copy gets a reference to the first copy's chunks.

---

## 11. Error Handling and Recovery

| Failure | Impact | Recovery |
|---|---|---|
| Single file parse failure | That file skipped | Error logged, pipeline continues, retry next run |
| GPU OOM during embedding | Batch fails | Automatic batch size reduction (OOM backoff), retry |
| phi4:14B crash during enrichment | Enrichment pauses | Restart Ollama, resume from last checkpoint |
| Disk full during export | Export incomplete | Alert in run report, operator clears space, re-run |
| Network down during download | No new files | Pipeline processes existing files, retries download next run |
| Pipeline crash mid-run | Partial processing | Deterministic chunk IDs + INSERT OR IGNORE = safe resume |

---

## 12. Acknowledged Tradeoffs

### T1: phi4:14B enrichment takes 5-9 days for full corpus

**Justification:** One-time cost. Incremental runs process only new/changed files (minutes). The 67% retrieval improvement is worth the initial compute investment. Can run over a weekend.

### T2: GLiNER2 first-pass extraction is approximate

**Justification:** CorpusForge only does first-pass extraction. Quality gating, validation, and normalization happen in HybridRAG V2. CorpusForge produces candidates; V2 filters them. This keeps CorpusForge simple and fast.

### T3: Separate application adds operational complexity

**Justification:** The alternative (V1's monolithic approach) caused GPU contention, config complexity, and deployment coupling. Two simple apps are easier to operate than one complex app. Scheduling via Windows Task Scheduler is a one-time setup.

### T4: 32 parsers is a lot of code to maintain

**Justification:** They're copied from V1 where they've been battle-tested on 420K files. Each parser is isolated (<500 lines). Parser failures never crash the pipeline. Adding a new format means adding one file.

---

Jeremy Randall | CorpusForge | 2026-04-04 MDT
