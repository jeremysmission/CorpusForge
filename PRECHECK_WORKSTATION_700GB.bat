@REM === NON-PROGRAMMER GUIDE ===
@REM What this does: Runs the preflight check that confirms the workstation is ready for a ~700GB Forge ingest.
@REM When to run: Before kicking off any large (hundreds-of-GB) ingest job. Skipping this risks a half-day wasted on a stuck run.
@REM Operator view: Prints PASS or FAIL per check. Success exits 0 with [OK]. Failure exits nonzero with [FAIL] -- do not start ingest.
@REM Prerequisites: .venv exists and tools\precheck_workstation_large_ingest.py is present in the repo.
@REM Skip pause: set CORPUSFORGE_NO_PAUSE=1 for unattended runs.
@REM Inputs:  Repo root with .venv and tools\precheck_workstation_large_ingest.py present.
@REM Outputs: PASS/FAIL console result and a dated report under logs\precheck_workstation_*.txt.
@REM ============================
@echo off
title CorpusForge 700GB Workstation Precheck
setlocal EnableExtensions EnableDelayedExpansion
for /f "tokens=2 delims=:." %%A in ('chcp') do set "_PREV_CP=%%A"
set "_PREV_CP=%_PREV_CP: =%"
chcp 65001 >nul 2>&1

REM Move into the repo so relative paths resolve, and lock onto the repo-local Python + precheck script.
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "SCRIPT=%PROJECT_ROOT%\tools\precheck_workstation_large_ingest.py"

REM UTF-8 safety, loopback-safe proxy settings, and PYTHONPATH so local imports resolve from the repo root.
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

REM Run the precheck. Pass through any extra args so operators can forward flags like --verbose.
"%PYTHON%" "%SCRIPT%" %*
set "_EXITCODE=%ERRORLEVEL%"

:cleanup
if not "%_EXITCODE%"=="0" (
  echo.
  echo [FAIL] Workstation precheck exited with code %_EXITCODE%.
  if /i not "%CORPUSFORGE_NO_PAUSE%"=="1" pause >nul
  goto :finish
)
echo.
echo [OK] Workstation precheck finished. Review RESULT and any warnings above.
if /i not "%CORPUSFORGE_NO_PAUSE%"=="1" pause >nul
:finish
if defined _PREV_CP chcp %_PREV_CP% >nul 2>&1
endlocal & exit /b %_EXITCODE%
