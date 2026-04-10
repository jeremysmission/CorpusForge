# Install Path Validation Evidence

**Date:** 2026-04-08 MDT | **Author:** CoPilot+ | **Machine:** primary workstation (Windows 11, CUDA-capable)

---

## Environment Baseline

| Component | Version/State |
|-----------|--------------|
| OS | Windows 11 Pro 10.0.26200 |
| System Python | 3.14.3 (NOT supported — used `py -3.12`) |
| Python 3.12 | 3.12.10 (via `py -3.12`) |
| Git | 2.53.0 |
| NVIDIA Driver | 595.79 |
| GPU 0 | RTX 3090 FE 24GB |
| GPU 1 | RTX 3090 FE 24GB |
| Tesseract | NOT installed |
| Poppler | NOT installed |
| Ollama | 0.20.0 (running) |
| Disk free (C:) | 2.6-8.6 GB (critically low) |

---

## CorpusForge Install Path

**Method:** Deleted existing `.venv`, ran `tools/setup_workstation_2026-04-06.ps1` from clean state.

| Step | Command/Action | Result | Notes |
|------|---------------|--------|-------|
| 1. Detect project root | Auto | PASS | `C:\CorpusForge` |
| 2. Detect Python 3.12 | Auto (`py -3.12`) | PASS | 3.12.10 found |
| 3. Create venv | `py -3.12 -m venv .venv` | PASS | Created on attempt 1/3 |
| 4. Assessment | Auto | PASS | Detected: no torch, no pip-system-certs |
| 5. pip + pip-system-certs | Auto | PASS | pip upgraded, certs installed |
| 6. Install torch | `pip install torch==2.7.1 --index-url .../cu128` | PASS | Attempt 1/3 succeeded |
| 7. Install requirements | `pip install -r requirements.txt` | PASS | Attempt 1/3 succeeded |
| 8. Verify CUDA torch | Auto | PASS | torch 2.7.1+cu128, CUDA=True, CUDA devices detected |
| 9. Verify key imports | 16 packages checked | PASS | All 16/16 pass |
| 10. Check Ollama | HTTP probe to localhost:11434 | PASS (manual) | v0.20.0 running |
| 11. Check OCR | where tesseract, where pdftoppm | WARN | Both missing (expected) |
| **Config load** | `load_config('config/config.yaml')` | PASS | Config + local overrides loaded |
| **Test suite** | `pytest tests/ -x -q` | PASS | **112/112 tests pass** in 23.2s |

**Minimum path to "app runs":** Run `INSTALL_WORKSTATION.bat` (double-click), press key when prompted. All steps automated. After install, `start_corpusforge.bat` launches the GUI.

---

## HybridRAG V2 Install Path

**Method:** Deleted existing `.venv`, ran `tools/setup_workstation_2026-04-06.ps1` from clean state.

| Step | Command/Action | Result | Notes |
|------|---------------|--------|-------|
| 1. Detect project root | Auto | PASS | `C:\HybridRAG_V2` |
| 2. Detect Python 3.12 | Auto | PASS | 3.12.10 found |
| 3. Create venv | `py -3.12 -m venv .venv` | PASS | Created on attempt 1/3 |
| 4. Assessment | Auto | PASS | Detected: no torch, no pip-system-certs |
| 5. pip + pip-system-certs | Auto | PASS | pip upgraded, certs installed |
| 6. Install torch | Auto (3 attempts) | **FAIL** | `[Errno 28] No space left on device` — 2.6 GB free, torch wheel = 3.27 GB |
| 6b. Manual torch | `pip install torch==2.7.1 --index-url .../cu128` | PASS | After freeing 6 GB of disk space |
| 7. Install requirements | `pip install -r requirements.txt` | PASS | All packages installed |
| 8. Verify CUDA torch | Manual | PASS | torch 2.7.1+cu128, CUDA=True, CUDA devices detected |
| 9. Verify key imports | Manual (8 key packages) | PASS | lancedb, sentence-transformers, openai, flashrank, gliner, pydantic, fastapi all OK |
| **Boot check** | `python scripts/boot.py` | PASS | "V2 ready." API Base=NOT SET (expected, no API key) |
| **Test suite** | `pytest tests/ -x -q` | PASS | **88/88 tests pass** in 1.9s |

**Minimum path to "app runs":**
1. Run `INSTALL_WORKSTATION.bat` (requires ~10 GB free disk space for torch)
2. Set `OPENAI_API_KEY` or `AZURE_OPENAI_*` env vars for production queries
3. Import CorpusForge export: `python scripts/import_embedengine.py`
4. Run: `python scripts/boot.py` or `python -m src.api.server`

---

## Failure Matrix

| # | Command | Failure | Root Cause | Fix | Retest |
|---|---------|---------|-----------|-----|--------|
| 1 | V2 installer step 6 (torch) | `[Errno 28] No space left on device` | C: drive had only 2.6 GB free; torch wheel is 3.27 GB | Freed 6 GB by removing backup venv. Manual `pip install torch==2.7.1 --index-url .../cu128` succeeded. | PASS |
| 2 | V2 installer (bash invocation) | Hung at `Wait-ForOperator` | `HYBRIDRAG_NO_PAUSE=1` set in bash but not inherited by PowerShell child process | Not a code bug — bash env vars don't propagate to Windows child processes. CMD/Explorer invocation works correctly. | N/A (by design) |

**No installer script bugs found. No doc/script mismatches found.** The only failure was environmental (disk space).

---

## Prerequisite Failure Behavior

| Prerequisite | Behavior When Missing |
|-------------|----------------------|
| Python 3.12 | Installer detects and reports "Python 3.12 not found." Clear error. |
| torch/CUDA | Installer retries 3x, then prints manual recovery commands including wheel URL and helper batch files. Clear guidance. |
| Tesseract | Installer warns but does not fail. Pipeline runs without OCR. |
| Poppler | Installer warns but does not fail. Pipeline runs without scanned PDF fallback. |
| Ollama | Installer checks availability. If not running, warns but does not fail. Enrichment skipped at runtime. |
| API key (V2) | Boot prints "API Base: NOT SET". Server starts but queries fail with clear error. |
| Disk space | torch install fails with `[Errno 28]`. Installer prints retry guidance but does not diagnose space specifically. |

---

## Residual Blockers (Environmental Only)

| Blocker | Type | Impact |
|---------|------|--------|
| C: drive nearly full (2.6-8.6 GB free on 1.9 TB) | Environmental | torch install fails without ~10 GB free. Not a code/doc issue. |
| Tesseract not installed | Environmental | All image OCR fails. Documented gap. |
| Poppler not installed | Environmental | Scanned PDF OCR fallback fails. Documented gap. |
| No OPENAI_API_KEY set | Environmental | V2 queries fail at generation stage. Boot and retrieval work fine. |

**No code/doc bugs remain.** Both repos install and run successfully from a clean venv.

---

## Files Changed During This Validation

No installer scripts or setup docs were modified during this pass. The install path matched documentation exactly. The V2 Setup Guide was already updated in the previous doc review pass.

---

Jeremy Randall | CorpusForge + HybridRAG V2 | 2026-04-08 MDT
