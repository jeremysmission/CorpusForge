@REM === NON-PROGRAMMER GUIDE ===
@REM What this does: Daily one-click launcher for the Forge desktop GUI using the repo's .venv Python.
@REM When to run: Every time the operator wants to open the Forge application. This is the normal "run Forge" entrypoint.
@REM Operator view: Console shows [INFO] lines and the GUI window opens. Any failure prints [FAIL] with next-step instructions.
@REM Prerequisites: INSTALL_WORKSTATION.bat has been run at least once and .venv\Scripts\python.exe exists.
@REM Flags: --detach launches GUI without holding the console; --dry-run prints resolved paths and exits.
@REM Inputs:  Repo root with .venv, config files, and the GUI launcher module in place.
@REM Outputs: The operator desktop application window and any startup logs shown in the console.
@REM ============================
@echo off
title CorpusForge Pipeline GUI
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM ================================================================
REM  CorpusForge -- One-Click GUI Launcher
REM ================================================================
REM  WHAT THIS DOES:
REM    1. Finds the .venv and verifies Python works.
REM    2. Sets project paths and UTF-8 encoding.
REM    3. Constrains to GPU 0 (compute, not display).
REM    4. Launches the GUI (terminal or detached mode).
REM
REM  FLAGS:
REM    --detach   Launch the GUI without keeping this console open.
REM    --dry-run  Print resolved paths and exit without starting.
REM ================================================================

REM Bind to the repo-local .venv Python (python.exe = console, pythonw.exe = detached/no-console) and the GUI entrypoint.
set "PROJECT_ROOT=%CD%"
set "VENV_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "VENV_PYTHONW=%PROJECT_ROOT%\.venv\Scripts\pythonw.exe"
set "VENV_ACTIVATE=%PROJECT_ROOT%\.venv\Scripts\activate.bat"
set "GUI_SCRIPT=%PROJECT_ROOT%\src\gui\launch_gui.py"
set "GUI_MODULE=src.gui.launch_gui"
set "GUI_MODE=terminal"
set "DRY_RUN=0"
set "PASSTHROUGH_ARGS="

REM Parse operator flags (--detach, --terminal, --dry-run). Anything else is forwarded to the GUI.
:parse_args
if "%~1"=="" goto after_parse_args
if /I "%~1"=="--detach" (
  set "GUI_MODE=detached"
  shift
  goto parse_args
)
if /I "%~1"=="--terminal" (
  set "GUI_MODE=terminal"
  shift
  goto parse_args
)
if /I "%~1"=="--dry-run" (
  set "DRY_RUN=1"
  shift
  goto parse_args
)
set "PASSTHROUGH_ARGS=!PASSTHROUGH_ARGS! "%~1""
shift
goto parse_args

:after_parse_args

REM Default launcher = console python; detached mode swaps to pythonw so Windows doesn't keep a black console window.
set "LAUNCH_EXE=%VENV_PYTHON%"
if /I "%GUI_MODE%"=="detached" set "LAUNCH_EXE=%VENV_PYTHONW%"

if "%DRY_RUN%"=="1" goto dry_run

REM --- Pre-flight checks ---
if not exist "%VENV_PYTHON%" goto missing_venv
if not exist "%GUI_SCRIPT%" goto missing_gui_script
for %%A in ("%VENV_PYTHON%") do if %%~zA EQU 0 goto broken_venv
"%VENV_PYTHON%" -c "import sys" >nul 2>nul
if errorlevel 1 goto broken_venv

REM --- Environment setup ---
set "PYTHONPATH=%PROJECT_ROOT%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NO_PROXY=localhost,127.0.0.1"
set "no_proxy=localhost,127.0.0.1"

REM GPU isolation: CorpusForge owns GPU 0 (batch indexing).
REM HybridRAG V2 uses GPU 1. No GPU sharing between repos.
if not defined CUDA_VISIBLE_DEVICES set "CUDA_VISIBLE_DEVICES=0"

REM Activate venv
if exist "%VENV_ACTIVATE%" call "%VENV_ACTIVATE%" >nul 2>nul

REM --- Launch ---
if /I "%GUI_MODE%"=="detached" if exist "%VENV_PYTHONW%" set "LAUNCH_EXE=%VENV_PYTHONW%"
if /I "%GUI_MODE%"=="detached" goto launch_detached

echo [INFO] Launching CorpusForge GUI from "%PROJECT_ROOT%"
echo [INFO] GPU: CUDA_VISIBLE_DEVICES=%CUDA_VISIBLE_DEVICES%
"%LAUNCH_EXE%" -m %GUI_MODULE% !PASSTHROUGH_ARGS!
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto launch_failed
goto end

:launch_detached
echo [INFO] Launching CorpusForge GUI (detached) from "%PROJECT_ROOT%"
start "" "%LAUNCH_EXE%" -m %GUI_MODULE% !PASSTHROUGH_ARGS!
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto launch_failed
goto end

:dry_run
echo CorpusForge GUI launcher -- dry run
echo.
echo Project root:    %PROJECT_ROOT%
echo Python exe:      %VENV_PYTHON%
echo Pythonw exe:     %VENV_PYTHONW%
echo Activate script: %VENV_ACTIVATE%
echo GUI script:      %GUI_SCRIPT%
echo GUI module:      %GUI_MODULE%
echo Launch exe:      %LAUNCH_EXE%
echo Launch mode:     %GUI_MODE%
echo CUDA devices:    %CUDA_VISIBLE_DEVICES%
echo Args:            !PASSTHROUGH_ARGS!
exit /b 0

:missing_venv
echo.
echo [FAIL] Virtual environment not found.
echo Expected Python here:
echo   "%VENV_PYTHON%"
echo.
echo Create the venv first:
echo   cd "%PROJECT_ROOT%"
echo   py -3.12 -m venv .venv
echo   .venv\Scripts\activate
echo   pip install torch --index-url https://download.pytorch.org/whl/cu128
echo   pip install -r requirements.txt
echo.
echo Then run start_corpusforge.bat again.
call :maybe_pause
exit /b 2

:broken_venv
echo.
echo [FAIL] Found .venv but Python cannot start.
echo   "%VENV_PYTHON%"
echo.
echo This usually means the venv was built with a different Python version
echo that was later removed or upgraded.
echo.
echo Rebuild:
echo   cd "%PROJECT_ROOT%"
echo   rmdir /s /q .venv
echo   py -3.12 -m venv .venv
echo   .venv\Scripts\activate
echo   pip install torch --index-url https://download.pytorch.org/whl/cu128
echo   pip install -r requirements.txt
echo.
echo Then run start_corpusforge.bat again.
call :maybe_pause
exit /b 4

:missing_gui_script
echo.
echo [FAIL] GUI entrypoint not found.
echo Expected file:
echo   "%GUI_SCRIPT%"
echo.
echo The repo may be incomplete. Re-clone or restore src\gui\launch_gui.py.
call :maybe_pause
exit /b 3

:launch_failed
echo.
echo [FAIL] GUI exited with code %EXIT_CODE%.
echo.
echo If you double-clicked this file, rerun from a terminal to see the full error.
echo.
echo Common checks:
echo   - Is Ollama running? (needed for enrichment)
echo   - Run: python scripts/run_pipeline.py --help
call :maybe_pause
exit /b %EXIT_CODE%

:maybe_pause
if /I "%CORPUSFORGE_NO_PAUSE%"=="1" exit /b 0
pause
exit /b 0

:end
endlocal
exit /b 0
