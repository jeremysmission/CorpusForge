# CorpusForge — Theory of Operations (Technical)

**Author:** Jeremy Randall (CoPilot+)
**Date:** 2026-04-08 MDT
**Audience:** Software engineers, system administrators
**Status:** Current — reflects Sprint 7 proven architecture

---

## 1. System Overview

CorpusForge is an offline, GPU-accelerated document processing pipeline that transforms raw source files into query-ready artifacts consumed by HybridRAG V2. It runs as a scheduled nightly task or on-demand via GUI or CLI on a dedicated workstation.

**Input:** 420K+ source files across 60+ supported formats (700GB)
**Output:** Export package containing chunked text, embedding vectors, and candidate entity extractions
**Runtime:** Windows 10/11, Python 3.12+, CUDA-capable GPU (RTX 3090 FE recommended)

---

## 2. Pipeline Stages

### 2.1 Download and Sync

- Copies new/updated files from configured network source directories to local landing zone
- Delta detection via mtime and file size comparison
- Landing zone configurable per-machine via `config.local.yaml`

### 2.2 Hash and Deduplicate

- SHA-256 content hash per file, stored in SQLite state DB (`file_state.sqlite3`)
- Unchanged files (same hash as previous run) are skipped entirely
- `_1` suffix duplicate detection: if `Report.docx` and `Report_1.docx` have identical content hashes, the `_1` version is skipped
- **Measured impact on 90GB production sample:** 49.7% of files are exact duplicates (all `_1` suffix pattern). Zero cross-format duplicates found at the byte level.
- Hash state persists across runs for incremental skip continuity

### 2.3 Skip and Defer

- Config-driven format decisions via `config/skip_list.yaml` (no hardcoded format decisions in Python)
- **Deferred formats:** Hashed and recorded in skip manifest but not parsed (e.g., `.dwf`)
- **Placeholder formats:** Hashed with identity-card text only (e.g., `.dwg`, `.prt`, `.sldprt`)
- **OCR sidecar suffixes:** 17 patterns matching metadata junk from scanning tools
- **Skip conditions:** Encrypted files (magic-byte detection), zero-byte, over-size (500 MB), temp files (`~$` prefix, `.tmp`/`.partial`/`.bak`/`.swp`)
- **Runtime deferrals:** `parse.defer_extensions` in config allows per-run format exclusion (e.g., demo text-only preset defers images, archives, sensor data)
- All skipped/deferred files recorded in `skip_manifest.json` with path, SHA-256, size, and reason

### 2.4 Parse

- Format dispatcher routes files to appropriate parser by extension
- 31 parser implementations covering: PDF, DOCX, DOC, XLSX, XLS, PPTX, PPT, CSV, TXT, MD, MSG, EML, HTML, RTF, JSON, XML, YAML, EPUB, OpenDocument, Visio, DXF, STL, STEP, IGES, Access DB, PSD, EVTX, PCAP, certificates, archives, and images (OCR)
- Per-file timeout: 60 seconds (configurable), prevents hung parsers from blocking pipeline
- OCR fallback: scanned PDFs detected by low text-to-page ratio, routed through pytesseract + Poppler (requires native binaries on PATH)
- Parse quality scoring: 0.0-1.0 per file based on text coherence, character distribution, and formatting preservation
- Error isolation: try/except per file, error logged, pipeline continues
- **Measured on 1000-file production sample:** 94.7% parse success rate. Failures: 64% scanned PDFs (needs Tesseract), 26% DOCX form templates (content controls), 10% edge-case PDFs.

### 2.5 Chunk

- Fixed-size: 1200 characters with 200 character overlap
- Smart boundary: splits at sentence endings (`. `, `! `, `? `) rather than mid-word
- Heading-aware: detects short uppercase lines as heading boundaries
- Deterministic chunk IDs: `SHA-256(canonical_file_path + chunk_index)`
- INSERT OR IGNORE semantics: crash-safe resume, no duplicate chunks on restart
- **Measured quality:** 77% of chunks in 900-1300 char target range. Zero tiny chunks (<200). 50% hit the 1100-1300 sweet spot.

### 2.6 Contextual Enrichment (Optional)

- Model: phi4:14B-q4_K_M hosted on local Ollama instance
- Generates 1-2 sentence context prefix per chunk describing document topic, section, and key entities
- Prepended to chunk text before embedding: `[context prefix]\n[original text]`
- **Measured improvement:** 67% retrieval quality gain vs plain text (Sprint 3 A/B test)
- Fallback: if Ollama unavailable, chunk proceeds with original text (no enrichment)
- Concurrent workers: 2-3 on Beast (configurable per-machine)
- Can be disabled per-run via `--strip-enrichment` or config

### 2.7 Embed

- Model: nomic-embed-text v1.5 (768 dimensions, Nomic AI, USA, Apache 2.0)
- Backend hierarchy: CUDA via sentence-transformers (primary) → ONNX CPU (fallback)
- Token-budget batching: dynamically sizes batches to fit within 49K token window
- OOM backoff: on CUDA OOM, automatically halves batch size and retries
- Output format: float16 (50% storage savings, negligible quality loss on normalized vectors)
- **Measured throughput:** 305 chunks/sec on RTX 3090 (CUDA). 83,022 chunks embedded in ~4.5 minutes.

### 2.8 First-Pass Entity Extraction (Optional)

Two-pass strategy proven on production data:

**Pass 1: Regex (instant, always run)**
- 15 compiled patterns covering CONTACT, DATE, PART_NUMBER, PO, labeled SITE/PERSON
- **Measured coverage:** 94.2% of chunks yield at least 1 entity. 3,311 chunks/sec throughput.

**Pass 2: GLiNER2 (selective, CPU)**
- Model: urchade/gliner_multi-v2.1 (205M params, Apache 2.0, CPU inference)
- Entity types: PART_NUMBER, PERSON, SITE, DATE, ORGANIZATION, FAILURE_MODE, ACTION
- Run selectively on chunks where regex found zero entities
- **Measured value-add:** 82 unique entities found by GLiNER that regex missed (PERSON, ORG, SITE in prose text). 0.9 chunks/sec CPU throughput.
- Confidence scores per entity; validation and normalization happen in HybridRAG V2

### 2.9 Export

- Output directory: `data/output/export_YYYYMMDD_HHMM/`
- Symlink `data/output/latest/` points to most recent successful export
- Package contents:
  - `chunks.jsonl` — chunk ID, text, enriched text, source path, metadata, quality score
  - `vectors.npy` — float16 numpy array, shape [N, 768]
  - `entities.jsonl` — candidate entities with confidence scores
  - `manifest.json` — version, timestamp, model info, chunk count, run stats
  - `run_report.txt` — human-readable summary with format coverage, skip reasons, deferred extension breakdown
  - `skip_manifest.json` — every skipped/deferred file with path, hash, size, and reason

---

## 3. Hardware Configuration

### 3.1 Beast Workstation (Primary Development)

```
CPU:     High-core-count (16+ threads, 2 reserved for user interaction)
GPU 0:   RTX 3090 FE (24GB) — compute: embedding
GPU 1:   RTX 3090 FE (24GB) — display (available for overflow compute)
RAM:     128GB (planned)
Storage: 2TB NVMe (C: drive)
```

GPU allocation strategy:
- Embedding on GPU 0 (~24GB VRAM at peak during batch encoding)
- GLiNER entity extraction on CPU (no GPU needed)
- CPU reservation: 3-layer (affinity + priority + thread cap) — cores 0-1 reserved for user, process priority below-normal

### 3.2 Workstation Deployment

- GPU workstation: full pipeline with CUDA embedding
- Laptop (no GPU): ONNX CPU embedding only, no enrichment
- Useful for small test runs and development

### 3.3 Native Tool Dependencies

| Tool | Required For | Install |
|------|-------------|---------|
| Python 3.12+ | Pipeline runtime | python.org or system package manager |
| Tesseract OCR | Image and scanned PDF OCR | UB-Mannheim installer, add to PATH |
| Poppler (pdftoppm) | PDF-to-image for OCR fallback | GitHub release, add to PATH |
| Ollama | Contextual enrichment (optional) | ollama.com/download |
| CUDA Toolkit 12.8 | GPU embedding | developer.nvidia.com |

---

## 4. Configuration Architecture

### 4.1 Config Loading Order

1. `config/config.yaml` — base settings (committed to git)
2. `config/config.local.yaml` — machine-specific overrides (gitignored)
3. Pydantic defaults for any missing fields

`config.local.yaml` deep-merges over `config.yaml`. Use it for machine-specific settings: workers, GPU index, paths, batch sizes.

### 4.2 Demo Presets

`config/config.demo_text_only.yaml` — defers images, archives, sensor data, and XML BIT files by config. Keeps PDFs and all Office/email/text formats. Disables enrichment and extraction for speed. OCR mode set to skip.

Use: `python scripts/run_pipeline.py --config config/config.demo_text_only.yaml`

---

## 5. Scheduling

### Windows Task Scheduler Configuration

```
Task Name:    CorpusForge Nightly Pipeline
Trigger:      Daily at 02:00 AM
Action:       python scripts/run_pipeline.py --config config/config.yaml
Working Dir:  C:\CorpusForge
User:         Run whether user is logged on or not
Timeout:      Stop if running longer than 12 hours
```

### Typical Nightly Timing (Incremental, Text-Only)

```
02:00  Hash and deduplicate     ~15 min (420K files at 200 files/sec)
02:15  Parse new text files     ~30 min (depends on volume)
02:45  Chunk                    ~5 min
02:50  Embed (GPU)              ~5 min (42K chunks at 305 chunks/sec)
02:55  Regex extraction         ~15 sec
02:56  Export                   ~1 min
03:00  Done
```

Full re-index (all text files, no enrichment): approximately 55 minutes.
Full re-index with OCR + enrichment: 2-4 days.

---

## 6. Corporate Environment

### 6.1 Network Configuration

All scripts set:
```
NO_PROXY=127.0.0.1,localhost
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
HF_HUB_OFFLINE=1          (when models pre-downloaded)
TRANSFORMERS_OFFLINE=1     (when models pre-downloaded)
```

### 6.2 pip Configuration

Virtual environment `pip.ini` includes trusted hosts and 120-second timeout. Written WITHOUT BOM bytes (critical for pip parsing on Windows). `pip-system-certs` installed to trust Windows certificate store.

### 6.3 UTF-8 Handling

- All file reads: `encoding="utf-8-sig"` (strips BOM if present)
- All file writes: `encoding="utf-8", newline="\n"` (clean UTF-8, Unix line endings)

---

## 7. Error Handling and Recovery

| Failure | Detection | Recovery |
|---------|-----------|---------|
| Single file parse error | try/except per file | Log error, skip file, continue pipeline |
| GPU OOM during embedding | RuntimeError catch | Automatic batch size halving, retry |
| Ollama crash | Connection error | Skip enrichment for affected chunks, use raw text |
| Disk full | OSError on write | Alert in run report, operator clears space |
| Pipeline crash mid-run | Incomplete export | Deterministic chunk IDs enable safe resume on restart |
| SQLite locking | Busy timeout | WAL mode with 30-second busy timeout |

---

## 8. Data Flow to HybridRAG V2

```
CorpusForge produces:              HybridRAG V2 consumes:
  data/output/latest/                data/source/ (V2 landing zone)
    chunks.jsonl       ------->       Load into LanceDB
    vectors.npy        ------->       Load into LanceDB
    entities.jsonl     ------->       Quality gate + normalize + promote
    manifest.json      ------->       Version check, model compatibility verify
```

V2 detects new exports by comparing `manifest.json` timestamps. Import is triggered on V2 startup or via manual trigger.

---

Jeremy Randall | CorpusForge | 2026-04-08 MDT
