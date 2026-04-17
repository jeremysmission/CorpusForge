@REM === NON-PROGRAMMER GUIDE ===
@REM What this does: Copies a known-good torch install from another local HybridRAG-style .venv into CorpusForge's .venv.
@REM When to run: Only when download.pytorch.org is blocked (proxy, offline site) and another repo on this machine already has working CUDA torch.
@REM Operator view: Delegates to a PowerShell helper. Success exits 0 with [OK]. Failure exits nonzero with [FAIL].
@REM Prerequisites: Forge .venv already created (INSTALL_WORKSTATION.bat ran once). Source .venv on same machine with matching Python version.
@REM Usage: Double-click, OR pass a source .venv path as the first argument, e.g. COPY_TORCH_FROM_EXISTING_HYBRIDRAG.bat C:\HybridRAG_V2\.venv
@REM Inputs:  This repo plus tools\copy_torch_from_existing_hybridrag.ps1. Optional source venv path.
@REM Outputs: Torch packages copied into this repo's .venv so CorpusForge can use the same local build.
@REM ============================
@echo off
title CorpusForge -- Copy Torch From Existing HybridRAG
setlocal EnableExtensions
cd /d "%~dp0"

REM Locate the PowerShell helper; first arg, if provided, is an explicit source .venv path.
set "SCRIPT=%~dp0tools\copy_torch_from_existing_hybridrag.ps1"
set "SOURCE_VENV=%~1"

if not exist "%SCRIPT%" (
  echo [FAIL] Copy script not found:
  echo        %SCRIPT%
  pause
  exit /b 1
)

echo [INFO] CorpusForge offline torch recovery
echo [INFO] Repo root: %CD%
if defined SOURCE_VENV (
  echo [INFO] Using explicit source venv:
  echo        %SOURCE_VENV%
) else (
  echo [INFO] Auto-detecting source venv from common HybridRAG workstation paths.
)

REM Prefer PowerShell 7 (pwsh) if installed; fall back to Windows PowerShell otherwise. ExecutionPolicy Bypass is session-only.
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" (
  if defined SOURCE_VENV (
    "%ProgramFiles%\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -SourceVenv "%SOURCE_VENV%"
  ) else (
    "%ProgramFiles%\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
  )
) else (
  if defined SOURCE_VENV (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -SourceVenv "%SOURCE_VENV%"
  ) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
  )
)

set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [FAIL] Torch copy exited with code %EXIT_CODE%.
) else (
  echo [OK] Torch copy completed.
)
if /i not "%HYBRIDRAG_NO_PAUSE%"=="1" pause
endlocal & exit /b %EXIT_CODE%
