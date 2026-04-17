@REM === NON-PROGRAMMER GUIDE ===
@REM What this does: One-click entrypoint that runs the full CorpusForge (Forge) workstation installer.
@REM When to run: First thing on a fresh workstation, or after a venv rebuild. Not needed daily.
@REM Operator view: Watch for [OK] / [FAIL] lines. Success exits 0 and prints [OK]. Any failure exits nonzero.
@REM Prerequisites: Run from the CorpusForge repo root so tools\setup_workstation_2026-04-06.bat is found.
@REM Inputs:  Repo folder with tools\setup_workstation_2026-04-06.bat present.
@REM Outputs: .venv, installed packages, and a verified local workstation setup.
@REM ============================
@echo off
title CorpusForge Workstation Install
setlocal EnableExtensions
REM Move into the folder this .bat lives in so relative paths resolve correctly.
cd /d "%~dp0"
REM Point at the real installer batch under tools\.
set "SCRIPT=%~dp0tools\setup_workstation_2026-04-06.bat"

echo [INFO] CorpusForge workstation install
echo [INFO] Repo root: %CD%
if not exist "%SCRIPT%" (
  echo [FAIL] Installer batch not found:
  echo        %SCRIPT%
  pause
  exit /b 1
)

REM Hand off to the real installer. EXIT_CODE mirrors whatever it returned.
call "%SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [FAIL] CorpusForge workstation install exited with code %EXIT_CODE%.
) else (
  echo [OK] CorpusForge workstation install finished.
)
pause
endlocal & exit /b %EXIT_CODE%
