# CorpusForge Workstation Setup

Date: 2026-04-06

## Ready Status

CorpusForge is now ready for workstation install.

Before this update, the repo had the right intent documented in `Repo_Rules_2026-04-04.md`, but the actual installer did not yet enforce all of it. The installer now does.

## Installer Features

`INSTALL_WORKSTATION.bat` and `tools\setup_workstation_2026-04-06.ps1` now provide:

- PowerShell process bypass
- UTF-8-safe setup handling
- `NO_PROXY=localhost,127.0.0.1`
- `pip-system-certs`
- trusted-host pip installs
- auto-generated `.venv\pip.ini` without BOM
- pinned `torch==2.7.1` on the CUDA 12.8 wheel index for NVIDIA workstations
- OCR tool warnings for Tesseract and Poppler
- optional Docling dev-only install path that does not block normal workstation bring-up

## Proven Workstation Lessons Carried Forward

These are the prior workstation bring-up patterns now treated as standard:

- detect proxy settings before package bootstrap
- write proxy-aware repo-local `.venv\pip.ini`
- install `pip-system-certs` in this repo `.venv`
- install large dependencies in smaller retryable steps on work networks
- verify the actual torch/CUDA outcome after install
- keep `NO_PROXY=127.0.0.1,localhost` for local-only services

Practical meaning:

- a working torch install in another repo does not prove this repo is healthy
- rerunning the workstation installer should act as diagnosis plus repair
- session proxy variables help, but repo-local pip configuration is the more durable layer

## Sanitization Policy

This rule applies to everything that is going to a workstation or any remote repository used by workstation operators.

The sanitization script is not the primary sanitizer.
It is the final catchall before push.

Required intent:

- write workstation-facing docs and scripts in already-sanitized form
- avoid banned provenance or internal-process wording in the first draft
- treat the script as the last-minute backstop, not the only line of enterprise

Operational rule:

- sanitize by authoring choices first
- run the script immediately before push second

## Recommended Path

Laptop:

```text
{USER_HOME}\Desktop1\CorpusForge
```

Desktop:

```text
<your stable desktop repo root>\CorpusForge
```

The exact desktop path can differ. CorpusForge resolves its project root from the installer location, so it does not need to live at `C:\CorpusForge`.

## Install Steps

1. Install Python 3.12.
2. Install Git.
3. Install Tesseract.
4. Install Poppler.
5. Install Ollama if you want local enrichment.
6. Optional dev-only: set `CORPUSFORGE_INSTALL_DOCLING=1` before running the installer if you want the Docling test lane in this repo-local `.venv`.
7. Open the repo folder.
8. Double-click `INSTALL_WORKSTATION.bat`.
9. After install, double-click `start_corpusforge.bat`.

## Machine Configuration

After install, edit `config/config.yaml` directly on that machine:

```yaml
# Example config.yaml for Beast workstation
parse:
  docling_mode: "off"   # off | fallback | prefer

pipeline:
  workers: 16

hardware:
  gpu_index: 0
```

Safe Docling contract:

- `docling_mode: "off"` = current parser path only
- `docling_mode: "fallback"` = use built-in parsers first, then Docling if installed and useful
- `docling_mode: "prefer"` = try Docling first, but still fall back if it fails
- if Docling is not installed, CorpusForge still runs normally

## Workstation Env Vars

These are the parser-related environment variables to standardize across workstations when OCR or optional Docling testing matters:

- `TESSERACT_CMD`
  - path to `tesseract.exe` if it is not already on PATH
- `HYBRIDRAG_POPPLER_BIN`
  - directory containing `pdftoppm.exe` for scanned-PDF OCR
- `CORPUSFORGE_INSTALL_DOCLING`
  - set to `1` only when you want the optional Docling dev dependency installed into the repo-local `.venv`
- `HYBRIDRAG_DOCLING_MODE`
  - optional override for parser testing: `off`, `fallback`, or `prefer`
  - normal workstation preference is to set `parse.docling_mode` in `config/config.yaml` instead of relying on an environment variable

Recommended workstation rule:

- Tesseract and Poppler should be configured consistently everywhere if you expect OCR behavior
- Docling should remain optional and dev-only until waiver and real-corpus validation are complete

## OCR Pre-Check Before A Large Run

Tesseract and Poppler matter for **CorpusForge**, not for V2 directly.

Quick PowerShell pre-check:

```powershell
where.exe tesseract
where.exe pdftoppm
tesseract --version
pdftoppm -h
Write-Host "TESSERACT_CMD=$env:TESSERACT_CMD"
Write-Host "HYBRIDRAG_POPPLER_BIN=$env:HYBRIDRAG_POPPLER_BIN"
```

Fast repo-local precheck launcher:

```powershell
cd <CorpusForge repo root>
.\PRECHECK_WORKSTATION_700GB.bat
```

Interpretation:

- if `where.exe tesseract` fails and `TESSERACT_CMD` is blank, image OCR is not configured
- if `where.exe pdftoppm` fails and `HYBRIDRAG_POPPLER_BIN` is blank, scanned-PDF OCR fallback is not configured
- the pipeline still runs without them, but OCR-dependent content degrades

## Manual Fallback If The Installer Fails On A Proxy Or TLS-Inspection Network

If `INSTALL_WORKSTATION.bat` or `tools\setup_workstation_2026-04-06.ps1` fails, use this order:

1. confirm proxy env vars for the current shell if your environment requires them:

```powershell
Write-Host "HTTP_PROXY=$env:HTTP_PROXY"
Write-Host "HTTPS_PROXY=$env:HTTPS_PROXY"
Write-Host "NO_PROXY=$env:NO_PROXY"
```

2. if they are required and blank, set them for the current shell:

```powershell
$env:HTTP_PROXY="http://proxy-host:port"
$env:HTTPS_PROXY="http://proxy-host:port"
$env:NO_PROXY="localhost,127.0.0.1"
```

3. activate the repo-local venv and bootstrap pip trust handling:

```powershell
cd <CorpusForge repo root>
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install pip-system-certs --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

4. if your company uses TLS inspection and `pip-system-certs` is still not enough, point pip at the approved corporate CA bundle:

```powershell
$env:PIP_CERT="C:\path\to\corp-ca.pem"
```

Optional durable repo-local pip config:

```text
<repo>\.venv\pip.ini
```

Example contents:

```ini
[global]
trusted-host =
    pypi.org
    pypi.python.org
    files.pythonhosted.org
    download.pytorch.org
timeout = 120
retries = 3
proxy = http://proxy-host:port
cert = C:\path\to\corp-ca.pem
```

5. rerun the Python package installs in smaller manual steps if needed:

```powershell
python -m pip install -r requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

If CUDA torch is the part that failed, use the dedicated torch helper or the explicit manual command documented below in `Torch Failure Note`.

## Manual Tesseract / Poppler Fallback

If the batch installer completes but OCR tools are still missing, install them manually.

### Tesseract

Recommended expected binary path:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

After install, either:

- add that folder to `PATH`, or
- set:

```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```

If your proxy environment blocks direct download:

- use the approved internal software source, or
- copy the already-approved Tesseract install from another workstation, then set `TESSERACT_CMD`

### Poppler

Expected requirement:

- a folder containing `pdftoppm.exe`

After install or unzip, set:

```powershell
$env:HYBRIDRAG_POPPLER_BIN="C:\path\to\poppler\Library\bin"
```

If direct download is blocked:

- use the approved internal software source, or
- copy the Poppler `bin` folder from another workstation, then set `HYBRIDRAG_POPPLER_BIN`

### Re-check After Manual Install

```powershell
where.exe tesseract
where.exe pdftoppm
tesseract --version
pdftoppm -h
```

For text-only demo runs that defer images and archives, use the demo preset:
```powershell
python scripts/run_pipeline.py --config config/config.demo_text_only.yaml --input data/source
```

## Verification

Terminal dry run:

```powershell
cd <CorpusForge repo root>
start_corpusforge.bat --dry-run
```

Recovery GUI launch:

```powershell
cd <CorpusForge repo root>
start_corpusforge.bat --dedup
```

Laptop production-grade chunk vetting:

- [WORKSTATION_LAPTOP_PRODUCTION_CHUNK_VETTING_2026-04-06.md](/C:/CorpusForge/docs/WORKSTATION_LAPTOP_PRODUCTION_CHUNK_VETTING_2026-04-06.md)

## Why This Matters

The HybridRAG3 workstation postmortem showed that work-machine setup fails when:

- installers and docs drift apart
- cert/proxy handling is manual
- machine-specific paths leak through tracked config

CorpusForge now avoids that specific class of failure on fresh installs.

The main patterns carried forward are:

- repo-local proxy-aware pip configuration
- per-repo certificate bootstrap
- grouped install steps for fragile corporate-network paths
- explicit torch verification instead of trusting pip output
- optional parser lanes must never break the baseline parser path

## Torch Failure Note

If the installer fails at `torch==2.7.1` with proxy errors or says `from versions: none`, the usual cause on a Python 3.12 64-bit work venv is blocked access to `download.pytorch.org`, not a missing PyTorch release.

Official sources:

- https://pytorch.org/get-started/previous-versions/
- https://download.pytorch.org/whl/cu128/torch/

Dedicated repair helper:

- `INSTALL_CUDA_TORCH_WORKSTATION.bat`
- `INSTALL_CUDA_TORCH_CU124_THEN_FORCE_CU128.bat`

If this workstation already has a working HybridRAG torch install, the fastest offline recovery path is:

- `COPY_TORCH_FROM_EXISTING_HYBRIDRAG.bat`
- [TORCH_REUSE_FROM_EXISTING_HYBRIDRAG_2026-04-06.md](/C:/CorpusForge/docs/TORCH_REUSE_FROM_EXISTING_HYBRIDRAG_2026-04-06.md)

That script matches the proven HybridRAG3 Blackwell lane:

- uninstall any existing CPU-only torch
- install `torch==2.7.1` from the `cu128` index
- use `--force-reinstall --no-deps`
- verify `torch.cuda.is_available()`
