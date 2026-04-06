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
