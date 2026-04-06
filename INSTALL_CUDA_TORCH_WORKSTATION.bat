@echo off
setlocal enabledelayedexpansion
title CorpusForge -- Install CUDA Torch (Workstation)
for /f "tokens=2 delims=:." %%A in ('chcp') do set "_PREV_CP=%%A"
set "_PREV_CP=%_PREV_CP: =%"
chcp 65001 >nul 2>&1

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "NO_PROXY=127.0.0.1,localhost"
set "TRUSTED=--trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org"

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "PIP=%PROJECT_ROOT%\.venv\Scripts\pip.exe"

echo.
echo  ============================================================
echo    CorpusForge -- Install CUDA Torch For Workstations
echo.
echo    Purpose:
echo      - replace CPU-only torch with the official cu128 build
echo      - match the working HybridRAG3 Blackwell workstation lane
echo.
echo    Uses:
echo      torch==2.7.1 from https://download.pytorch.org/whl/cu128
echo.
echo    Why:
echo      Blackwell-class GPUs need the CUDA 12.8 wheel line.
echo      If CPU-only torch is already installed, pip may need
echo      --force-reinstall to replace it cleanly.
echo  ============================================================
echo.

if not exist "%PYTHON%" (
    echo  [FAIL] Python venv not found at:
    echo         %PYTHON%
    echo         Run INSTALL_WORKSTATION.bat first.
    goto :fail
)

echo  === Step 1/6: Python Runtime ===
for /f "usebackq delims=" %%I in (`"%PYTHON%" -c "import sys,struct; print(sys.version.split()[0]); print('cp%d%d'%%sys.version_info[:2]); print('64bit=' + str(struct.calcsize('P')*8==64))" 2^>nul`) do (
    echo  %%I
)
echo.

echo  === Step 2/6: pip Certificate Support ===
"%PIP%" show pip-system-certs >nul 2>&1
if !errorlevel! neq 0 (
    echo  Installing pip-system-certs...
    "%PIP%" install pip-system-certs %TRUSTED% 2>&1
)
echo  [OK] pip-system-certs check complete.
echo.

echo  === Step 3/6: NVIDIA GPU Check ===
nvidia-smi --query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader 2>nul
if !errorlevel! neq 0 (
    echo  [FAIL] nvidia-smi not found or no NVIDIA GPU detected.
    goto :fail
)
echo  [OK] NVIDIA GPU detected.
echo.

echo  === Step 4/6: Remove Existing Torch Packages ===
"%PIP%" uninstall torch torchvision torchaudio -y 2>nul
echo  [OK] Existing torch packages removed if present.
echo.

echo  === Step 5/6: Install Official cu128 Torch ===
echo  Command:
echo    .venv\Scripts\pip.exe install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall --no-deps %TRUSTED%
echo.
"%PIP%" install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall --no-deps %TRUSTED%
if !errorlevel! neq 0 (
    echo.
    echo  [FAIL] CUDA torch install failed.
    echo.
    echo  This usually means one of these:
    echo    1. Corporate proxy is blocking download.pytorch.org
    echo    2. Python is not a supported Windows wheel tag
    echo    3. The wheel must be brought in manually
    echo.
    echo  Official sources:
    echo    https://pytorch.org/get-started/previous-versions/
    echo    https://download.pytorch.org/whl/cu128/torch/
    echo.
    echo  Manual fallback example for Python 3.12 x64:
    echo    torch-2.7.1+cu128-cp312-cp312-win_amd64.whl
    echo.
    echo  If this machine already has a working HybridRAG torch install:
    echo    COPY_TORCH_FROM_EXISTING_HYBRIDRAG.bat
    echo.
    goto :fail
)
echo  [OK] CUDA torch installed.
echo.

echo  === Step 6/6: Verify CUDA ===
"%PYTHON%" -c "import torch; print('Version:', torch.__version__); print('CUDA built-in:', torch.version.cuda); print('Available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A'); print('Compute capability:', torch.cuda.get_device_capability(0) if torch.cuda.is_available() else 'N/A')" 2>nul
if !errorlevel! neq 0 (
    echo  [FAIL] torch import or CUDA verification failed.
    goto :fail
)
"%PYTHON%" -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" 2>nul
if !errorlevel! neq 0 (
    echo.
    echo  [FAIL] torch installed but CUDA is not available.
    echo.
    echo  Check:
    echo    - NVIDIA driver version in nvidia-smi
    echo    - PyTorch cu128 wheel was installed, not CPU-only torch
    echo    - Blackwell systems should be on a CUDA 12.8-compatible driver
    goto :fail
)
echo.
echo  [DONE] CUDA torch is ready for CorpusForge.
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
