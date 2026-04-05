# CorpusForge — Theory of Operations (Technical)

**Author:** Jeremy Randall (CoPilot+)
**Date:** 2026-04-04 MDT
**Audience:** Software engineers, system administrators
**Status:** Preliminary

---

## 1. System Overview

CorpusForge is an offline, GPU-accelerated document processing pipeline that transforms raw source files into query-ready artifacts consumed by HybridRAG V2. It runs nightly as a scheduled task on a dedicated workstation.

**Input:** 420K+ source files across 67+ formats (700GB)
**Output:** Export package containing chunked text, embedding vectors, enriched context, and candidate entity extractions
**Runtime:** Windows 10/11, Python 3.11.9, CUDA-capable GPU (3090 FE recommended)

---

## 2. Pipeline Stages

### 2.1 Download & Sync

- Copies new/updated files from configured network source directories to local landing zone
- Delta detection: only transfers files with changed mtime or size
- Landing zone: `data/source/`

### 2.2 Hash & Deduplicate

- SHA-256 content hash per file, stored in SQLite state DB (`file_state.sqlite3`)
- Unchanged files (same hash as previous run) are skipped entirely
- `_1` suffix duplicate detection: if `Report.docx` and `Report_1.docx` have identical content hashes, the `_1` version is skipped
- Measured impact: eliminates 54% of corpus from redundant processing

### 2.3 Parse

- Format dispatcher routes files to appropriate parser by extension
- 32+ parsers covering: PDF, DOCX, XLSX, PPTX, CSV, TXT, MD, MSG, HTML, RTF, JSON, XML, and more
- Per-file timeout: 60 seconds (configurable), prevents hung parsers from blocking pipeline
- OCR fallback: scanned PDFs detected by low text-to-page ratio, routed through pytesseract + Poppler
- Parse quality scoring: 0.0-1.0 per file based on text coherence, character distribution, and formatting preservation
- Error isolation: try/except per file, error logged, pipeline continues

### 2.4 Chunk

- Fixed-size: 1200 characters with 200 character overlap
- Smart boundary: splits at sentence endings (`. `, `! `, `? `) rather than mid-word
- Deterministic chunk IDs: `SHA-256(canonical_file_path + chunk_index)`
- INSERT OR IGNORE semantics: crash-safe resume, no duplicate chunks on restart

### 2.5 Contextual Enrichment

- Model: phi4:14B-q4_K_M hosted on local Ollama instance
- Generates 1-2 sentence context prefix per chunk describing document topic, section, and key entities
- Prepended to chunk text before embedding: `[context prefix]\n[original text]`
- GPU allocation: phi4:14B uses ~9GB VRAM on one GPU, embedding uses the other
- Incremental: only new/changed chunks enriched, with checkpoint tracking for resume
- Fallback: if Ollama unavailable, chunk proceeds with original text (no enrichment)

### 2.6 Embed

- Model: nomic-embed-text v1.5 (768 dimensions, Nomic AI, USA, Apache 2.0)
- Backend hierarchy: CUDA (primary) → ONNX CPU (fallback)
- Token-budget batching: dynamically sizes batches to fit GPU VRAM
- OOM backoff: on CUDA OOM, automatically halves batch size and retries
- Output format: float16 (50% storage savings, negligible quality loss on normalized vectors)
- Embedding input: enriched text (context prefix + original) if available, otherwise original text

### 2.7 First-Pass Entity Extraction

- Model: GLiNER2 (205M params, Apache 2.0, France/NATO, CPU inference)
- Entity types extracted: PART_NUMBER, PERSON, SITE, DATE, ORGANIZATION, FAILURE_MODE, ACTION
- Confidence scores per entity
- Output: candidate entities only — NOT validated or normalized
- Validation, quality gating, and normalization happen in HybridRAG V2's import pipeline
- CPU-only: does not compete with GPU for embedding/enrichment

### 2.8 Export

- Output directory: `data/output/export_YYYYMMDD_HHMM/`
- Symlink `data/output/latest/` points to most recent successful export
- Package contents:
  - `chunks.jsonl` — chunk ID, text, enriched text, source path, metadata, quality score
  - `vectors.npy` — float16 numpy array, shape [N, 768]
  - `entities.jsonl` — candidate entities with confidence scores
  - `manifest.json` — version, timestamp, model info, chunk count, run stats
  - `run_report.json` — files processed/skipped/failed, timing per stage, error summary

---

## 3. Hardware Configuration

### 3.1 Beast Workstation (Primary)

```
CPU: High-core-count (for parsing, CPU NER)
GPU 0: RTX 3090 FE (24GB) — compute: embedding + enrichment
GPU 1: RTX 3090 FE (24GB) — display (available for overflow compute)
RAM: 128GB (planned)
Storage: 2TB NVMe (C: drive)
```

GPU allocation strategy:
- phi4:14B enrichment on GPU 0 (~9GB VRAM)
- nomic-embed-text embedding on GPU 0 (~2GB VRAM) — sequential with enrichment, not concurrent
- GLiNER2 entity extraction on CPU (no GPU needed)
- Always check `nvidia-smi` before heavy compute to verify GPU 0 is available

### 3.2 Laptop (Secondary — Reduced Mode)

- No GPU: ONNX CPU embedding only
- No enrichment: skip contextual enrichment stage
- Useful for small test runs and development

---

## 4. Scheduling

### Windows Task Scheduler Configuration

```
Task Name:    CorpusForge Nightly Pipeline
Trigger:      Daily at 02:00 AM
Action:       python C:\CorpusForge\scripts\run_pipeline.py --config config\config.yaml
Working Dir:  C:\CorpusForge
User:         Run whether user is logged on or not
Timeout:      Stop if running longer than 12 hours
```

### Typical Nightly Timing (Incremental)

```
02:00  Download & sync         ~5-15 min
02:15  Hash & deduplicate      ~5 min
02:20  Parse new files         ~10-60 min (depends on volume)
03:00  Chunk                   ~5 min
03:05  Contextual enrichment   ~10-30 min (only new chunks)
03:30  Embed                   ~5-15 min (only new chunks)
03:45  Entity extraction       ~5-15 min (CPU, parallel with nothing)
04:00  Export                  ~5 min
04:05  Done
```

Full re-index (all 420K files): 2-4 days continuous.

---

## 5. Corporate Environment

### 5.1 Network Configuration

All scripts set:
```
NO_PROXY=127.0.0.1,localhost
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
HF_HUB_OFFLINE=1          (when models pre-downloaded)
TRANSFORMERS_OFFLINE=1     (when models pre-downloaded)
```

### 5.2 pip Configuration

Virtual environment `pip.ini` includes:
```ini
[global]
trusted-host =
    pypi.org
    files.pythonhosted.org
timeout = 120
retries = 3
```

Written WITHOUT BOM bytes (critical for pip parsing).

`pip-system-certs` installed to trust Windows certificate store.

### 5.3 SSL Certificate Handling

HTTP clients respect environment variables:
- `REQUESTS_CA_BUNDLE` — enterprise CA bundle path
- `SSL_CERT_FILE` — enterprise CA bundle path
- `CURL_CA_BUNDLE` — enterprise CA bundle path

### 5.4 UTF-8 Handling

- All file reads: `encoding="utf-8-sig"` (strips BOM if present)
- All file writes: `encoding="utf-8", newline="\n"` (clean UTF-8, Unix line endings)
- Environment: `PYTHONUTF8=1` enforces UTF-8 as default encoding

---

## 6. Error Handling and Recovery

| Failure | Detection | Recovery |
|---|---|---|
| Single file parse error | try/except per file | Log error, skip file, continue pipeline |
| GPU OOM during embedding | RuntimeError catch | Automatic batch size halving, retry |
| phi4:14B crash | Ollama connection error | Skip enrichment for affected chunks, use raw text |
| Disk full | OSError on write | Alert in run_report.json, operator clears space |
| Network down during download | Connection timeout | Process existing files, retry download next run |
| Pipeline crash mid-run | Incomplete export | Deterministic chunk IDs enable safe resume on restart |
| SQLite locking | Busy timeout | WAL mode with 30-second busy timeout |

---

## 7. Data Flow to HybridRAG V2

```
CorpusForge produces:              HybridRAG V2 consumes:
  data/output/latest/                data/source/ (V2's landing zone)
    chunks.jsonl       ------->       Load into LanceDB
    vectors.npy        ------->       Load into LanceDB
    entities.jsonl     ------->       GPT-4o 2nd pass + quality gate + normalize
    manifest.json      ------->       Version check, model compatibility verify
```

V2 detects new exports by comparing `manifest.json` timestamps. Import is triggered on V2 startup or via manual trigger.

---

Jeremy Randall | CorpusForge | 2026-04-04 MDT
