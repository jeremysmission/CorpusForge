@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Reuse a working local torch install from another HybridRAG-style repo when internet installs fail.
@REM How to follow: Double-click this file, or pass an existing source .venv path as the first argument.
@REM Inputs: This repo plus tools\copy_torch_from_existing_hybridrag.ps1. Optional source venv path.
@REM Outputs: Torch packages copied into this repo's .venv so CorpusForge can use the same local build.
@REM ============================
@echo off
title CorpusForge -- Copy Torch From Existing HybridRAG
setlocal EnableExtensions
cd /d "%~dp0"

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
