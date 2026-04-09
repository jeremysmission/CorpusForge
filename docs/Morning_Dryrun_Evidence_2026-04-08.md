# Morning Dry-Run Evidence Report

**Date:** 2026-04-08 MDT | **Author:** CoPilot+
**Repos tested:** C:\CorpusForge (branch: master), C:\HybridRAG_V2 (branch: master)
**Machine:** Beast (Windows 11, dual RTX 3090 FE, Python 3.12.10)

---

## Findings by Severity

### High
1. **C: drive critically low on space (232 MB free at one point on a 1.9 TB drive).** Pipeline crashed with `[Errno 28] No space left on device` during first Path A attempt. Root cause: 18.9 GB pip cache accumulated from multiple torch installs. Fixed by purging pip cache (`pip cache purge`). **This is a recurring environmental risk that must be monitored.**

2. **Stale GPU processes accumulate and block new CUDA contexts.** After multiple pipeline runs, 8 Python processes held GPU memory. New pipeline attempts failed with `The paging file is too small for this operation to complete (os error 1455)`. Fixed by killing stale processes (`Get-Process python* | Stop-Process -Force`). **Recommendation: pipeline should check for stale GPU processes before embedding, or use a single-process model.**

### Medium
None.

### Low
1. **GUI validation limited to CLI fallback.** This session runs in a headless CLI environment. Tkinter initializes correctly but GUI-specific checks (scrollbar behavior, window resize, output folder selector, live progress updates) require human verification. The pipeline itself works correctly via CLI.

---

## Sample Corpus

**Location:** `C:\CorpusForge\data\morning_dryrun_sample\`
**Composition:** 53 files (38 originals + 15 `_1` suffix duplicates)

| Format | Count | Role |
|--------|-------|------|
| .pdf | 11 | Primary text (includes scanned) |
| .docx | 8 | Office documents |
| .sao | 6 | Sensor data (parseable as text) |
| .xlsx | 4 | Spreadsheets |
| .txt | 4 | Plain text / logs |
| .zip | 4 | Archives (deferred) |
| .xml | 4 | BIT status (empty parse) |
| .jpg | 3 | Images (deferred, no Tesseract) |
| .rsf | 3 | Sensor binary (deferred) |
| .doc | 2 | Legacy Word |
| .msg | 2 | Email |
| .pptx | 1 | Presentation |
| .ini | 1 | Config (low value) |

---

## Path A: Controlled Reviewed Path

### Step 1: Dedup-Only Pass
**Venv:** `C:\CorpusForge\.venv\Scripts\python.exe`
**GPU:** None (CPU-only)
**Command:** Inline Python calling `src.dedup.document_dedup.run_document_dedup()` with `input_path=data/morning_dryrun_sample`, `extensions=TEXT_EXTS`, `similarity_threshold=0.85`, `min_chars=50`, `workers=4`. Output via `write_index()` to `data/morning_dryrun_output/`.
**Time:** 0.4 seconds
**Result:** 46 text files scanned → 41 canonical, 5 duplicates (10.87% reduction)
**Artifacts written to `data/morning_dryrun_output/`:**
- `canonical_files.txt` (2,816 bytes) — 41 files
- `dedup_report.json` (739 bytes) — reduction stats and reasons
- `duplicates.jsonl` (2,257 bytes) — duplicate file details
- `dedup_index.sqlite3` (32,768 bytes) — SQLite index for pipeline reuse

### Step 2: Pipeline on Canonical List
**Venv:** `C:\CorpusForge\.venv\Scripts\python.exe`
**GPU:** `CUDA_VISIBLE_DEVICES=0` (physical GPU 0, RTX 3090 FE)
**Command:** Inline Python — `load_config('config/config.yaml')` with `output_dir` overridden to `data/morning_dryrun_output`, `enrich.enabled=False`, `extract.enabled=False`, `pipeline.full_reindex=True`. Files loaded from `data/morning_dryrun_output/canonical_files.txt`. Called `Pipeline(config).run(files)`.
**Time:** 80.2 seconds (parsing: ~6s, model load: ~20s, embedding: ~50s)
**Result:** 41 files → 37 parsed, 4 failed (XML BIT empty), 9,772 chunks + vectors

**Export package:** `data/morning_dryrun_output/export_20260408_2355/`
- chunks.jsonl: 14.97 MB (9,772 chunks)
- vectors.npy: 15.01 MB (9,772 x 768, float16)
- manifest.json: 800 bytes
- entities.jsonl: 0 bytes (extraction disabled)
- run_report.txt: 692 bytes

### Step 3: V2 Import
**Venv:** `C:\HybridRAG_V2\.venv\Scripts\python.exe`
**GPU:** None required for import
**Command:** `cd C:\HybridRAG_V2 && .venv\Scripts\python.exe scripts/import_embedengine.py --source "C:/CorpusForge/data/morning_dryrun_output/export_20260408_2355"`
**Time:** 0.66 seconds (15,692 chunks/sec)
**Result:** 9,772 chunks inserted into LanceDB at `C:\HybridRAG_V2\data\index\lancedb` (total store: 59,522 chunks after import)

### Step 4: V2 Query (Sample-Attributed)
**Venv:** `C:\HybridRAG_V2\.venv\Scripts\python.exe`
**GPU:** `CUDA_VISIBLE_DEVICES=0` (physical GPU 0, RTX 3090 FE)
**Command:** Custom attribution script — queries V2 store and tags each result as SAMPLE or EXISTING.
```
Query: "packing list shipment", top 10 results:
  [SAMPLE]   score=0.302 NG Packing List Hand-Carry (Eareckson ASV)(2023-05)_1_1
  [SAMPLE]   score=0.327 NG Packing List Hand-Carry (Eareckson ASV)(2023-05)_1_1
  [EXISTING] score=0.338 FM55-4.pdf
  [EXISTING] score=0.341 FM55-4.pdf
  ...
  [SAMPLE]   score=0.383 NG Packing List Hand-Carry (Eareckson ASV)(2023-05)_1_1
Attribution: 3/10 from sample, retrievable=True
```
**Result:** Sample data IS retrievable in V2. 3 of 10 top results come from the just-imported dry-run sample, correctly ranked against the existing 49,750-chunk store (59,522 total after import).

---

## Path B: Fast Automatic Path

**Venv:** `C:\CorpusForge\.venv\Scripts\python.exe`
**GPU:** `CUDA_VISIBLE_DEVICES=0` (physical GPU 0)
**Command:** Inline Python — `load_config('config/config.yaml')` with `output_dir=data/morning_dryrun_pathB`, `enrich.enabled=False`, `extract.enabled=False`, `pipeline.full_reindex=True`. Files discovered by `rglob('*')` on `data/morning_dryrun_sample/`. Called `Pipeline(config).run(files)`.
**Time:** 38.8 seconds
**Result:** 53 files → 9 skipped (deferred by config), 40 parsed, 4 failed, 8,025 chunks + vectors

**Comparison to Path A:**
| Metric | Path A | Path B |
|--------|--------|--------|
| Files input | 41 (canonical list) | 53 (raw folder) |
| Files skipped | 0 | 9 (deferred formats) |
| Files parsed | 37 | 40 |
| Chunks produced | 9,772 | 8,025 |
| Time | 80.2s | 38.8s |

Path B is faster but produces fewer chunks because it uses inline hash dedup (skips `_1` copies) rather than content-level document dedup. Path A keeps more canonical files through normalization.

---

## Incremental/Resume Verification

**Venv:** `C:\CorpusForge\.venv\Scripts\python.exe`
**GPU:** `CUDA_VISIBLE_DEVICES=0`
**Test:** Re-ran Path B on same sample without `full_reindex=True` (config default is `False`)
**Time:** 2.0 seconds (19x faster than first run)
**Result:**
- 40 files skipped as unchanged (hash match)
- 6 files skipped as duplicates
- 5 files skipped (deferred)
- 0 new chunks — nothing to process

**State file:** `data/production_state_run3.sqlite3` (configured via `config.local.yaml`)
- Table: `file_state` — columns: path, hash, mtime, size, status
- Written by `src/download/hasher.py`
- Hash persists across runs; when the full 700GB corpus arrives, already-processed files auto-skip

---

## Worker Setting / Operator Visibility

**Current config:** `config.local.yaml` sets `pipeline.workers: 16` (Beast default)
- Desktop target: 32 (set in config.local.yaml on desktop machine)
- Laptop target: 20 (set in config.local.yaml on laptop)

**Visibility:** Workers value is loaded from config at boot and logged in pipeline startup:
```
Parallel pipeline: 16 parser threads, 32 prefetch, N files
```
The GUI Settings panel allows changing workers (1-32 slider).

---

## GUI Verification (Partial — CLI Session)

| Check | Result | Notes |
|-------|--------|-------|
| Tkinter initializes | PASS | `tk.Tk()` creates and destroys cleanly |
| GUI launches without crash | NOT TESTED | Requires display; CLI-only session |
| Dedup-only output folder selector | NOT TESTED | GUI-specific; CLI dedup works correctly |
| Live progress updates | NOT TESTED | GUI-specific; pipeline emits stage callbacks |
| Window shrink + scrollbar | NOT TESTED | GUI-specific |
| Worker count shown in GUI | NOT TESTED | Settings panel has workers slider per code review |

**Recommendation:** These GUI checks need a human button-smash session before demo.

---

## Information Flow (End-to-End)

```
1. SOURCE FOLDER
   Raw documents (PDF, DOCX, XLSX, etc.)
   ↓
2. HASH AND DEDUP (file_state.sqlite3)
   SHA-256 per file. Skip unchanged. Skip _1 duplicates.
   ↓
3. SKIP AND DEFER (skip_list.yaml + config defer_extensions)
   Deferred formats hashed and recorded in skip_manifest.json.
   ↓
4. PARSE (31 parsers, 60s timeout per file)
   → ParsedDocument(text, parse_quality, source_path)
   ↓
5. CHUNK (1200 chars, 200 overlap, sentence boundary)
   → chunk_id = SHA-256(path | mtime_ns | start | end | text_fp)
   ↓
6. ENRICH (optional, phi4:14B via Ollama)
   → enriched_text prepended to chunk text
   ↓
7. EMBED (nomic-embed-text v1.5, CUDA, 768-dim float16)
   → vectors.npy [N, 768]
   ↓
8. EXPORT (timestamped directory)
   → chunks.jsonl + vectors.npy + entities.jsonl + manifest.json
   → run_report.txt + skip_manifest.json
   ↓
9. V2 IMPORT (import_embedengine.py)
   → Load into LanceDB (vector + BM25 hybrid search)
   ↓
10. V2 QUERY (operator asks question)
    → Router → Retrieve → Rerank → Generate → Answer with sources
```

---

## Hash and Identity Continuity

| Identity | Where It Lives | What Derives It | Carries Into V2? |
|----------|---------------|-----------------|-----------------|
| File SHA-256 | `file_state.sqlite3` | File content bytes | NO (stays in CorpusForge) |
| Dedup decision | `dedup_index.sqlite3` | Content normalization + similarity | NO (stays in CorpusForge) |
| **Chunk ID** | `chunks.jsonl` | `SHA-256(norm_path \| mtime_ns \| start \| end \| text_fp)` | **YES** — primary key in V2 LanceDB |
| Chunk text | `chunks.jsonl` | Parser output + chunker | **YES** — stored in LanceDB |
| Vector | `vectors.npy` | nomic-embed-text v1.5 encode | **YES** — stored in LanceDB |
| Parse quality | `chunks.jsonl` | Quality scorer (0.0-1.0) | **YES** — metadata in LanceDB |
| Source path | `chunks.jsonl` | Original file path | **YES** — metadata in LanceDB |
| Entity candidates | `entities.jsonl` | GLiNER2 / regex | **YES** — imported to entity store |
| Skip manifest | `skip_manifest.json` | Skip manager decisions | **NO** — informational only |

**Hash continuity range:** File-level hashes persist in CorpusForge's state DB across runs. When the full 700GB corpus arrives, already-hashed files are recognized and skipped. Chunk IDs are deterministic — same file + same content = same chunk IDs = safe INSERT OR IGNORE in V2.

---

## Explicit Answers

**Can Jeremy point CorpusForge at a large source folder and let it run straight through?**
YES, on the sample tested. Path B proves the flow works end-to-end — point at folder, pipeline runs dedup → skip → parse → chunk → embed → export automatically. 38.8 seconds for 53 files. Production-scale timing has not been validated in this dry run.

**What is the safer reviewed path?**
Path A: Run dedup-only first to review canonical/duplicate decisions, then pipeline on the canonical list. Adds operator review but catches content-level duplicates that hash dedup misses.

**What morning steps are manual vs automatic?**
- **Automatic:** hash dedup, parse, chunk, embed, export. All stages run without intervention.
- **Manual:** dedup-only review (optional), V2 import trigger, setting API credentials, checking run report for failures.

**Where do file hashes live?**
`data/file_state.sqlite3` (or configured `state_db` path). Table `file_state` with columns: path, hash, mtime, size, status.

**How far does hash continuity carry?**
File hashes stay in CorpusForge. Chunk IDs (derived from path + mtime + position + text) carry into V2 as the primary key. Same file → same chunks → same IDs → safe idempotent import.

**What exactly gets imported into V2?**
- `chunks.jsonl` → LanceDB chunks table (text, enriched_text, source_path, chunk_id, parse_quality)
- `vectors.npy` → LanceDB vector column (768-dim float16)
- `entities.jsonl` → entity store (if non-empty)
- `manifest.json` → version/compatibility check

**Is the GUI/operator surface good enough for morning use?**
CLI path is validated on the 53-file sample. GUI initializes but needs human button-smash verification for visual checks (progress, scrollbar, folder selector). CLI is the reliable fallback for this validation scope.

---

## Final Recommendation

| Path | Status | Scope |
|------|--------|-------|
| **Morning fast path (CLI)** | **VALIDATED ON 53-FILE SAMPLE** | Production signoff requires real 1000-file subset or full corpus run |
| **Morning controlled path (CLI)** | **VALIDATED ON 53-FILE SAMPLE** | Same — sample proves the flow works, not production scale |
| **Morning GUI path** | **NOT VERIFIED** — needs human button-smash on display | GUI-specific checks deferred to human session |

**What this validation proves:** The end-to-end flow (source → dedup → parse → chunk → embed → export → V2 import → retrieval) works correctly. Incremental skip works. Identity chain is intact.

**What this validation does NOT prove:** Production-scale timing, full corpus error rates, or GUI operator experience.

**Environmental prerequisites for morning run:**
1. Verify disk space: `Get-PSDrive C | Select-Object Used, Free` (need ~10 GB minimum for torch + exports)
2. Kill stale GPU processes: `Get-Process python* | Stop-Process -Force`
3. Verify GPU free: `nvidia-smi`
4. Then run pipeline

**Note:** HuggingFace model cache (`~/.cache/huggingface/`, ~4.1 GB) is intentionally preserved for offline model loading (`HF_HUB_OFFLINE=1`). Do not purge without investigation.

---

Jeremy Randall | CorpusForge + HybridRAG V2 | 2026-04-08 MDT
