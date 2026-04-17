@REM === NON-PROGRAMMER GUIDE ===
@REM What this does: Fallback bootstrap. Installs a cu124 torch first, then force-reinstalls the cu128 (CUDA 12.8) wheel on top.
@REM When to run: Only when the normal INSTALL_CUDA_TORCH_WORKSTATION.bat cannot land the cu128 lane. Never the first attempt.
@REM Operator view: Step 1/5 through 5/5. Success ends with [DONE] and exit 0. Any failure ends with [FAIL] and exit 1.
@REM Prerequisites: .venv already exists, network reaches PyPI and download.pytorch.org.
@REM Inputs:  Repo-local .venv plus internet or proxy access to PyPI and download.pytorch.org.
@REM Outputs: Torch reinstalled in .venv with extra recovery steps aimed at stubborn workstation setups.
@REM ============================
@echo off
setlocal enabledelayedexpansion
title CorpusForge -- Torch Bootstrap (cu124 then force cu128)
for /f "tokens=2 delims=:." %%A in ('chcp') do set "_PREV_CP=%%A"
set "_PREV_CP=%_PREV_CP: =%"
chcp 65001 >nul 2>&1

REM UTF-8 safety + pip defaults so corporate proxies and certs behave.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "NO_PROXY=127.0.0.1,localhost"
REM TRUSTED = hosts pip can fetch from without cert-validation complaints.
set "TRUSTED=--trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org"

REM Bind to the repo-local .venv so we never touch system Python.
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "PIP=%PROJECT_ROOT%\.venv\Scripts\pip.exe"

echo.
echo  ============================================================
echo    CorpusForge -- Torch Bootstrap Fallback
echo.
echo    Sequence:
echo      1. install pip-system-certs
echo      2. install torch from cu124 index
echo      3. force-reinstall torch 2.7.1 from cu128 index
echo.
echo    Use this only if the normal cu128 install path keeps failing.
echo  ============================================================
echo.

if not exist "%PYTHON%" (
    echo  [FAIL] Python venv not found at:
    echo         %PYTHON%
    echo         Run INSTALL_WORKSTATION.bat first.
    goto :fail
)

echo  === Step 1/5: Python Runtime ===
"%PYTHON%" -c "import sys,struct; print(sys.version); print('64bit=', struct.calcsize('P')*8==64)"
if !errorlevel! neq 0 goto :fail
echo.

echo  === Step 2/5: pip Certificate Support ===
"%PIP%" install pip-system-certs %TRUSTED%
if !errorlevel! neq 0 (
    echo  [WARN] pip-system-certs install failed. Continuing anyway.
) else (
    echo  [OK] pip-system-certs installed.
)
echo.

REM Install a cu124 torch first; older wheel line is sometimes more forgiving when cu128 direct fails.
echo  === Step 3/5: Bootstrap Torch From cu124 ===
echo  Command:
echo    .venv\Scripts\pip.exe install torch --index-url https://download.pytorch.org/whl/cu124 %TRUSTED%
echo.
"%PIP%" install torch --index-url https://download.pytorch.org/whl/cu124 %TRUSTED%
if !errorlevel! neq 0 (
    echo  [FAIL] cu124 bootstrap install failed.
    goto :fail
)
echo  [OK] cu124 bootstrap install completed.
echo.

REM Now force-replace with the cu128 wheel so the workstation lands on the CUDA 12.8 lane.
echo  === Step 4/5: Force-Reinstall cu128 ===
echo  Command:
echo    .venv\Scripts\pip.exe install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall --no-deps %TRUSTED%
echo.
"%PIP%" install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall --no-deps %TRUSTED%
if !errorlevel! neq 0 (
    echo  [FAIL] cu128 force-reinstall failed.
    goto :fail
)
echo  [OK] cu128 force-reinstall completed.
echo.

REM Confirm torch imports, report CUDA version, then gate on torch.version.cuda starting with 12.8.
echo  === Step 5/5: Verify Torch ===
"%PYTHON%" -c "import torch; print('version=', torch.__version__); print('built_cuda=', torch.version.cuda); print('cuda_available=', torch.cuda.is_available()); print('gpu=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
if !errorlevel! neq 0 (
    echo  [FAIL] torch verification failed.
    goto :fail
)

"%PYTHON%" -c "import torch; raise SystemExit(0 if str(torch.version.cuda).startswith('12.8') else 1)"
if !errorlevel! neq 0 (
    echo  [FAIL] torch installed, but built CUDA is not 12.8.
    goto :fail
)

echo.
echo  [DONE] Torch is installed with cu128.
set "_EXITCODE=0"
goto :cleanup

:fail
set "_EXITCODE=1"

:cleanup
echo.
if /i not "%HYBRIDRAG_NO_PAUSE%"=="1" (
    if "!_EXITCODE!"=="0" (
        echo  Closing in 20 seconds. Set HYBRIDRAG_NO_PAUSE=1 to skip.
        timeout /t 20 >nul
    ) else (
        echo  Press any key to close.
        pause >nul
    )
)
if defined _PREV_CP chcp %_PREV_CP% >nul 2>&1
endlocal & exit /b %_EXITCODE%
