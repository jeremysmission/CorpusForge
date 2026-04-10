# Dedup-Only Pass — Operator Guide

**Date:** 2026-04-08
**Author:** Jeremy Randall (CoPilot+)
**Purpose:** Run a fast dedup pass on fresh source data BEFORE spending GPU time on embedding. This identifies duplicates, junk, and sidecars so you only index clean canonical files.

---

## Option A: GUI (Recommended for First Time)

### Step 1: Open CorpusForge GUI
```
cd C:\CorpusForge
.venv\Scripts\python.exe scripts/boot.py
```

### Step 2: Configure for Dedup-Only
In the **Settings** panel:
- **Source folder:** Point to your 700GB staging directory
- **Embedding:** UNCHECK (disabled)
- **Enrichment:** UNCHECK (disabled)
- **Entity Extraction:** UNCHECK (disabled)
- **Workers:** Set to max for your machine (primary workstation: 16, Desktop: 32, Laptop: 20)
- Click **Save Settings**

### Step 3: Run
- Click **Start Pipeline**
- Watch the stats panel — you'll see files discovered, parsed, skipped, and deduped
- No GPU will be used — this is CPU-only, fast
- 700GB should take 1-3 hours depending on file types

### Step 4: Review Results
- When done, check the **export directory** (shown in GUI log)
- Open `run_report.txt` — shows files found, parsed, skipped, duplicates, format coverage
- Open `skip_manifest.json` — shows every skipped file and why
- Open `chunks.jsonl` — these are your deduped chunks (no vectors yet)

### Step 5: Decide
- If skip/dedup numbers look reasonable: proceed to full pipeline with embedding enabled
- If too many skips or unexpected formats: review skip_manifest.json and adjust config/skip_list.yaml

---

## Option B: Command Line (Headless / Overnight)

### Step 1: Edit Config
Open `config/config.yaml` and set:
```yaml
embed:
  enabled: false    # No GPU embedding

enrich:
  enabled: false    # No Ollama enrichment

extract:
  enabled: false    # No GLiNER extraction
```

Or if you have a `config/config.local.yaml`, override there instead (doesn't touch the shared config).

### Step 2: Run
```bash
cd C:\CorpusForge
.venv\Scripts\activate

python scripts/run_pipeline.py --input "D:\path\to\700gb\source" --full-reindex --log-file logs/dedup_pass.log
```

### Step 3: Monitor
```bash
# In another terminal — watch progress
tail -f logs/dedup_pass.log

# Or check GPU to confirm it's NOT being used (should be 0%)
nvidia-smi
```

### Step 4: Check Results
```bash
# Quick summary
python scripts/audit_corpus.py

# Or read the run report directly
type data\output\export_*\run_report.txt

# Check what was skipped and why
type data\output\export_*\skip_manifest.json
```

---

## What You'll See in the Report

| Field | What It Means |
|-------|--------------|
| Files found | Total files discovered in source directory |
| Files after dedup | Files remaining after hash-based duplicate removal |
| Files parsed | Successfully parsed to text |
| Files skipped | Deferred formats, sidecars, encrypted, zero-byte |
| Files failed | Parse errors (timeout, corrupt, encoding) |
| Chunks created | Text chunks produced (no vectors in dedup-only mode) |
| Vectors created | Should be 0 (embedding disabled) |
| Entities extracted | Should be 0 (extraction disabled) |
| Format coverage | File count per extension (.pdf, .docx, .xlsx, etc.) |
| Skip reasons | Why each file was skipped (deferred format, sidecar, encrypted, etc.) |

---

## After the Dedup Pass

### If results look good:
1. Re-enable embedding in config: `embed.enabled: true`
2. Run again — dedup state is saved, so unchanged files will be skipped automatically
3. This time GPU will activate and produce vectors
4. Export will contain chunks.jsonl + vectors.npy ready for V2 import

### If too many duplicates:
1. Check `skip_manifest.json` for duplicate families
2. Run the dedup review tool: `python scripts/review_dedup_samples.py`
3. Approve/reject duplicate families
4. Generate `canonical_files.txt`: the approved clean file list
5. Re-run with: `python scripts/run_pipeline.py --input-list canonical_files.txt --strict-input-list`

### If unexpected format skips:
1. Check `config/skip_list.yaml` — is the format listed as deferred or placeholder?
2. To add a format: remove it from skip_list.yaml (or add a real parser)
3. To keep it skipped: leave it — the skip manifest documents the decision

---

## Quick Reference

| Machine | Workers | Command |
|---------|---------|---------|
| primary workstation (16 threads) | 16 | `python scripts/run_pipeline.py --input "path" --full-reindex --log-file logs/dedup.log` |
| Work Desktop (32 threads) | 32 | Same command — workers set via config.local.yaml |
| Work Laptop (20 threads) | 20 | Same command — workers set via config.local.yaml |

**Time estimate:** ~1-3 hours for 700GB depending on file types (PDFs with emoji cmaps are slow).

---

Jeremy Randall (CoPilot+) | 2026-04-08
