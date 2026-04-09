@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Run the workstation large-ingest precheck before a 700GB-scale CorpusForge job.
@REM How to follow: Double-click this file from Explorer, or run it from cmd.exe / PowerShell.
@REM Inputs: Repo root with .venv and tools\precheck_workstation_large_ingest.py present.
@REM Outputs: PASS/FAIL console result and a dated report under logs\precheck_workstation_*.txt.
@REM ============================
@echo off
title CorpusForge 700GB Workstation Precheck
setlocal EnableExtensions EnableDelayedExpansion
for /f "tokens=2 delims=:." %%A in ('chcp') do set "_PREV_CP=%%A"
set "_PREV_CP=%_PREV_CP: =%"
chcp 65001 >nul 2>&1

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "SCRIPT=%PROJECT_ROOT%\tools\precheck_workstation_large_ingest.py"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NO_PROXY=localhost,127.0.0.1"
set "no_proxy=localhost,127.0.0.1"
set "PYTHONPATH=%PROJECT_ROOT%"

if not exist "%PYTHON%" (
  echo [FAIL] Missing repo-local Python:
  echo        %PYTHON%
  set "_EXITCODE=1"
  goto :cleanup
)

if not exist "%SCRIPT%" (
  echo [FAIL] Precheck script not found:
  echo        %SCRIPT%
  set "_EXITCODE=1"
  goto :cleanup
)

"%PYTHON%" "%SCRIPT%" %*
set "_EXITCODE=%ERRORLEVEL%"

:cleanup
if not "%_EXITCODE%"=="0" (
  echo.
  echo [FAIL] Workstation precheck exited with code %_EXITCODE%.
  if /i not "%CORPUSFORGE_NO_PAUSE%"=="1" pause >nul
)
if defined _PREV_CP chcp %_PREV_CP% >nul 2>&1
endlocal & exit /b %_EXITCODE%
