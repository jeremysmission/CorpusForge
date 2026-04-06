# CorpusForge Workstation Setup

Date: 2026-04-06

## Ready Status

CorpusForge is now ready for workstation install.

Before this update, the repo had the right intent documented in `Repo_Rules_2026-04-04.md`, but the actual installer did not yet enforce all of it. The installer now does.

## Installer Features

`INSTALL_WORKSTATION.bat` and `tools\setup_beast_2026-04-05.ps1` now provide:

- PowerShell process bypass
- UTF-8-safe setup handling
- `NO_PROXY=localhost,127.0.0.1`
- `pip-system-certs`
- trusted-host pip installs
- auto-generated `.venv\pip.ini` without BOM
- pinned `torch==2.7.1` on the CUDA 12.8 wheel index for NVIDIA workstations
- OCR tool warnings for Tesseract and Poppler

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
6. Open the repo folder.
7. Double-click `INSTALL_WORKSTATION.bat`.
8. After install, double-click `start_corpusforge.bat`.

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

## Why This Matters

The HybridRAG3 workstation postmortem showed that work-machine setup fails when:

- installers and docs drift apart
- cert/proxy handling is manual
- machine-specific paths leak through tracked config

CorpusForge now avoids that specific class of failure on fresh installs.

## Torch Failure Note

If the installer fails at `torch==2.7.1` with proxy errors or says `from versions: none`, the usual cause on a Python 3.12 64-bit work venv is blocked access to `download.pytorch.org`, not a missing PyTorch release.

Official sources:

- https://pytorch.org/get-started/previous-versions/
- https://download.pytorch.org/whl/cu128/torch/
