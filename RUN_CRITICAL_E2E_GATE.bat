@REM === NON-PROGRAMMER GUIDE ===
@REM What this does: Runs the critical end-to-end operator gate -- the go/no-go check that covers Forge ingest into HybridRAG V2.
@REM When to run: Before declaring a release ready, before a demo, or any time you want a single-word PASS/FAIL read on the system.
@REM Operator view: Exit 0 = all gates PASS; 2 = at least one gate FAILED; 3 = gates PASS but live query blocked (missing LLM config).
@REM Prerequisites: Forge .venv exists, tools\run_critical_e2e_gate.py is present, and HybridRAG V2 is checked out at C:\HybridRAG_V2.
@REM Inputs:  Repo root with .venv and tools\run_critical_e2e_gate.py present. V2 repo at C:\HybridRAG_V2.
@REM Outputs: PASS/FAIL console result and report under data\critical_e2e_gate\<timestamp>\.
@REM Skip pause: set CORPUSFORGE_NO_PAUSE=1 for unattended runs.
@REM ============================
@echo off
title CorpusForge Critical E2E Gate
setlocal EnableExtensions EnableDelayedExpansion
for /f "tokens=2 delims=:." %%A in ('chcp') do set "_PREV_CP=%%A"
set "_PREV_CP=%_PREV_CP: =%"
chcp 65001 >nul 2>&1

REM Move into the repo folder and bind to the repo-local Python + gate script.
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "SCRIPT=%PROJECT_ROOT%\tools\run_critical_e2e_gate.py"

REM UTF-8 + loopback-safe proxy settings so local services (Ollama, V2) stay reachable.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NO_PROXY=localhost,127.0.0.1"
set "no_proxy=localhost,127.0.0.1"
set "PYTHONPATH=%PROJECT_ROOT%"

if not exist "%PYTHON%" (
  echo [FAIL] Missing repo-local Python:
  echo        %PYTHON%
  echo        Run INSTALL_WORKSTATION.bat first.
  set "_EXITCODE=2"
  goto :cleanup
)

if not exist "%SCRIPT%" (
  echo [FAIL] Critical E2E gate script not found:
  echo        %SCRIPT%
  set "_EXITCODE=2"
  goto :cleanup
)

REM Run the gate; forward any operator-supplied args (e.g. --fast, --skip-live) straight through.
"%PYTHON%" "%SCRIPT%" %*
set "_EXITCODE=%ERRORLEVEL%"

:cleanup
if not "%_EXITCODE%"=="0" (
  echo.
  echo [FAIL] Critical E2E gate exited with code %_EXITCODE%.
  echo        0 = all gates PASS
  echo        2 = at least one gate FAILED
  echo        3 = all gates PASS but V2 live query BLOCKED (missing LLM config)
  if /i not "%CORPUSFORGE_NO_PAUSE%"=="1" pause >nul
) else (
  echo.
  echo [PASS] Critical E2E gate completed successfully.
  if /i not "%CORPUSFORGE_NO_PAUSE%"=="1" pause >nul
)
if defined _PREV_CP chcp %_PREV_CP% >nul 2>&1
endlocal & exit /b %_EXITCODE%
