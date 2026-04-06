@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Runs the CorpusForge workstation installer with PowerShell bypass enabled.
@REM How to follow: Double-click this file from Explorer, or run it from cmd.exe / PowerShell.
@REM Inputs: Repo folder with tools\setup_workstation_2026-04-06.bat present.
@REM Outputs: .venv, installed packages, and a verified local workstation setup.
@REM ============================
@echo off
title CorpusForge Workstation Install
setlocal EnableExtensions
cd /d "%~dp0"
set "SCRIPT=%~dp0tools\setup_workstation_2026-04-06.bat"

echo [INFO] CorpusForge workstation install
echo [INFO] Repo root: %CD%
if not exist "%SCRIPT%" (
  echo [FAIL] Installer batch not found:
  echo        %SCRIPT%
  pause
  exit /b 1
)

call "%SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
