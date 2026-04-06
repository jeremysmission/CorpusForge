# CorpusForge — Repository Rules

**Author:** Jeremy Randall (CoPilot+)
**Date:** 2026-04-04 MDT

---

## 1. Code Rules

- **500 lines max per class** (comments excluded)
- **Pin openai SDK to v1.x** if used — NEVER upgrade to 2.x
- **DO NOT use `pip install sentence-transformers[onnx]`** — nukes CUDA torch
- **All file I/O must use `encoding="utf-8"` or `encoding="utf-8-sig"` for reads** — corporate environments produce BOM-prefixed files
- **All file writes must use `encoding="utf-8", newline="\n"`** — no BOM, Unix line endings

## 2. Corporate Environment Requirements

### 2.1 Proxy Bypass

All scripts and batch files must set:
```batch
set "NO_PROXY=127.0.0.1,localhost"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
```

PowerShell equivalent:
```powershell
$env:NO_PROXY = 'localhost,127.0.0.1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

### 2.2 pip Install Commands

All `pip install` commands must include trusted-host flags for corporate proxy:
```batch
set "TRUSTED=--trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org"
pip install <package> %TRUSTED%
```

### 2.3 pip.ini (Auto-Generated in .venv)

```ini
[global]
trusted-host =
    pypi.org
    files.pythonhosted.org
timeout = 120
retries = 3
```

**Critical:** pip.ini must be written WITHOUT BOM bytes. Use `[System.IO.File]::WriteAllText()` in PowerShell, NOT `Out-File -Encoding UTF8` (which adds BOM in PS 5.1 and breaks pip).

### 2.4 pip-system-certs

Install early in setup to trust Windows certificate store:
```batch
pip install pip-system-certs %TRUSTED%
```

### 2.5 SSL Certificate Support

Code that makes HTTP requests must respect these environment variables:
- `REQUESTS_CA_BUNDLE` — path to enterprise CA bundle
- `SSL_CERT_FILE` — path to enterprise CA bundle
- `CURL_CA_BUNDLE` — path to enterprise CA bundle

### 2.6 Offline Model Flags

When models are pre-downloaded, set:
```batch
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
```

## 3. File Naming Convention

All documents: `Intuitive_Title_YYYY-MM-DD.ext`

## 4. Sanitization Before Remote Push

Run `python sanitize_before_push.py` before every push. This includes anything that will be used on workstations or by workstation operators.
The script is the final catchall, not the sole sanitizer. Workstation-bound content should already be authored in sanitized form before the script runs.
See HybridRAG V2 Repo_Rules for the full sanitization standard.

## 5. Waiver Compliance

Same rules as HybridRAG V2. Check `requirements.txt` for approved/pending packages.

## 6. Git Rules

Same rules as HybridRAG V2. Never commit data files, secrets, or large binaries.

---

Jeremy Randall | CorpusForge | 2026-04-04 MDT
