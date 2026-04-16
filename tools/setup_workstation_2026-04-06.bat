@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Thin launcher that starts the main PowerShell workstation setup script with policy bypass.
@REM How to follow: Run this file from the repo root when preparing a new CorpusForge machine.
@REM Inputs: This wrapper plus setup_workstation_2026-04-06.ps1 in the same tools folder.
@REM Outputs: Delegates to the full installer and returns its exit code.
@REM Suspect: This wrapper uses HYBRIDRAG_NO_PAUSE while several other wrappers use CORPUSFORGE_NO_PAUSE.
@REM ============================
@echo off
title CorpusForge Workstation Setup
setlocal EnableExtensions
cd /d "%~dp0"

set "SCRIPT=%~dp0setup_workstation_2026-04-06.ps1"

if not exist "%SCRIPT%" (
  echo [FAIL] Setup script not found:
  echo        %SCRIPT%
  pause
  exit /b 1
)

echo [INFO] CorpusForge workstation setup
echo [INFO] Script: %SCRIPT%
echo [INFO] Launching with session-only PowerShell execution-policy bypass.
echo [INFO] The installer will assess the workstation first, then pause before making changes.
if /i not "%HYBRIDRAG_NO_PAUSE%"=="1" (
  echo.
  echo Press any key to start the assessment.
  pause >nul
)
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" (
  "%ProgramFiles%\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
) else (
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
)
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [FAIL] Setup exited with code %EXIT_CODE%.
) else (
  echo [OK] Setup completed.
)
if /i not "%HYBRIDRAG_NO_PAUSE%"=="1" pause
endlocal & exit /b %EXIT_CODE%
