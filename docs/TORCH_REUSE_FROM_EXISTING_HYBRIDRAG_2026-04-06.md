# CorpusForge Torch Reuse From Existing HybridRAG

Date: 2026-04-06

## Purpose

Use this when `CorpusForge` cannot download `torch==2.7.1` from `download.pytorch.org`, but the same workstation already has a working HybridRAG installation with torch inside its `.venv`.

This recovery path copies the working torch package set from the existing HybridRAG venv into the `CorpusForge` venv, then lets `CorpusForge` finish installing the rest of its requirements normally.

## Fastest Path

From the `CorpusForge` repo root:

```text
Double-click COPY_TORCH_FROM_EXISTING_HYBRIDRAG.bat
```

If the source HybridRAG venv is not in a common location, run it with the exact source venv path:

```text
COPY_TORCH_FROM_EXISTING_HYBRIDRAG.bat "C:\Users\yourname\Desktop1\HybridRAG3\.venv"
```

## Exact PowerShell Steps

These commands are for a workstation where `CorpusForge` already exists but torch download is failing.

### Step 1: Open PowerShell

Open PowerShell in the `CorpusForge` repo root.

### Step 2: Go to the repo

Laptop example:

```powershell
cd "$env:USERPROFILE\Desktop1\CorpusForge"
```

Desktop example:

```powershell
cd "$env:USERPROFILE\Documents\CorpusForge"
```

### Step 3: Make sure the `.venv` exists

```powershell
py -3.12 -m venv .venv
```

If `.venv` already exists, this step can be skipped.

### Step 4: Install certificate support for pip

```powershell
.\.venv\Scripts\pip.exe install pip-system-certs --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org
```

### Step 5: Copy torch from an existing HybridRAG venv

Laptop source example:

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\tools\copy_torch_from_existing_hybridrag.ps1 -SourceVenv "$env:USERPROFILE\Desktop1\HybridRAG3\.venv"
```

Desktop source example:

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\tools\copy_torch_from_existing_hybridrag.ps1 -SourceVenv "$env:USERPROFILE\Documents\HybridRAG3\.venv"
```

If you want the script to auto-detect a common HybridRAG location:

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\tools\copy_torch_from_existing_hybridrag.ps1
```

### Step 6: Verify torch

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print('cuda=', torch.cuda.is_available()); print('built_cuda=', torch.version.cuda)"
```

### Step 7: Install the rest of CorpusForge

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org
```

### Step 8: Verify CorpusForge imports

```powershell
.\.venv\Scripts\python.exe -c "import torch, sentence_transformers, pdfplumber, yaml; print('CorpusForge core imports OK')"
```

## Common Source Venv Locations Checked By The Batch

The batch and helper script automatically check these paths:

```text
%USERPROFILE%\Desktop1\HybridRAG3\.venv
%USERPROFILE%\Desktop1\HybridRAG3_Educational\.venv
%USERPROFILE%\Desktop1\HybridRAG_V2\.venv
%USERPROFILE%\Documents\HybridRAG3\.venv
%USERPROFILE%\Documents\HybridRAG3_Educational\.venv
%USERPROFILE%\Documents\HybridRAG_V2\.venv
C:\HybridRAG3_DesktopProd\.venv
C:\HybridRAG3_Educational\.venv
C:\HybridRAG_V2\.venv
```

## Why This Works

`torch` is installed inside the source repo’s `.venv\Lib\site-packages`.

When the source and target use the same Python version and architecture, the working torch package set can be copied from one repo venv into the other, then verified locally.

This recovery path is meant for workstations where:

- the source HybridRAG repo already has working CUDA torch
- the target `CorpusForge` repo is on the same machine
- `download.pytorch.org` is blocked or unreliable
