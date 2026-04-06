#Requires -Version 5.1
<#
.SYNOPSIS
    CorpusForge -- Non-interactive workstation setup.
.DESCRIPTION
    Installs venv, CUDA torch, requirements, and verifies the environment.
    Designed for workstation installs (Python 3.12, CUDA 12.8 lane when NVIDIA is present).
    NO interactive prompts. Auto-retry on failure. Colored diagnostics.
.NOTES
    Author: Jeremy Randall
    Date:   2026-04-06
#>

# ============================================================
# 1. Encoding + Helpers
# ============================================================
# PS 5.1 encoding fixes -- prevents garbled output and BOM injection
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:no_proxy = "localhost,127.0.0.1"

$global:PassCount = 0
$global:FailCount = 0
$global:WarnCount = 0
$global:StepNum   = 0
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$TrustedHosts = @(
    "--trusted-host", "pypi.org",
    "--trusted-host", "pypi.python.org",
    "--trusted-host", "files.pythonhosted.org",
    "--trusted-host", "download.pytorch.org",
    "--timeout", "120",
    "--retries", "3"
)

function Write-Step  { param([string]$msg) $global:StepNum++; Write-Host "`n[$global:StepNum] $msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$msg) $global:PassCount++; Write-Host "  [PASS] $msg" -ForegroundColor Green }
function Write-Fail  { param([string]$msg) $global:FailCount++; Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Warn  { param([string]$msg) $global:WarnCount++; Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Info  { param([string]$msg) Write-Host "  [INFO] $msg" -ForegroundColor Gray }
function Format-Elapsed { $ts = $Stopwatch.Elapsed; return ("{0:D2}m {1:D2}s" -f [int]$ts.TotalMinutes, $ts.Seconds) }
function Remove-TempFileQuietly {
    param([string]$Path)
    try {
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
    } catch {
    }
}

function Write-Utf8NoBomFile {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Initialize-PipConfig {
    param([string]$PipIniPath)
    $content = @"
[global]
trusted-host =
    pypi.org
    pypi.python.org
    files.pythonhosted.org
    download.pytorch.org
timeout = 120
retries = 3
disable-pip-version-check = true
"@
    Write-Utf8NoBomFile -Path $PipIniPath -Text $content
}

function Test-NvidiaGpuPresent {
    try {
        & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-PythonRuntimeInfo {
    param([string]$PythonExe)
    $probe = @'
import json
import platform
import struct
import sys

print(json.dumps({
    "python_version": ".".join(map(str, sys.version_info[:3])),
    "python_tag": f"cp{sys.version_info[0]}{sys.version_info[1]}",
    "is_64bit": struct.calcsize("P") * 8 == 64,
    "platform": platform.platform(),
}))
'@
    try {
        $raw = & $PythonExe -c $probe 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return $null }
        return ($raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Write-TorchInstallGuidance {
    param(
        [string]$RepoName,
        [object]$RuntimeInfo,
        [switch]$CudaExpected
    )

    Write-Host ""
    Write-Host "  Torch install guidance for ${RepoName}:" -ForegroundColor Yellow
    if ($RuntimeInfo) {
        Write-Host "    Python version: $($RuntimeInfo.python_version)" -ForegroundColor Gray
        Write-Host "    Python tag:     $($RuntimeInfo.python_tag)" -ForegroundColor Gray
        Write-Host "    64-bit:         $($RuntimeInfo.is_64bit)" -ForegroundColor Gray
    }
    Write-Host "    Official PyTorch 2.7.1 cu128 wheels exist for Windows cp310-cp313." -ForegroundColor Gray
    Write-Host "    Official index: https://download.pytorch.org/whl/cu128/torch/" -ForegroundColor Gray
    Write-Host "    Official versions page: https://pytorch.org/get-started/previous-versions/" -ForegroundColor Gray
    if ($RuntimeInfo -and (-not $RuntimeInfo.is_64bit)) {
        Write-Warn "This interpreter is not 64-bit. PyTorch Windows wheels require 64-bit Python."
    }
    if ($RuntimeInfo -and $RuntimeInfo.python_tag -notin @("cp310", "cp311", "cp312", "cp313")) {
        Write-Warn "This interpreter tag is not in the official 2.7.1 cu128 Windows wheel set."
        Write-Host "    Fix: use Python 3.12 64-bit in the repo .venv." -ForegroundColor Gray
    } else {
        Write-Warn "If pip says 'from versions: none' here, the usual cause is proxy/cert access to download.pytorch.org, not a missing torch release."
    }
    if ($CudaExpected) {
        Write-Host "    Dedicated helper:" -ForegroundColor Gray
        Write-Host "      INSTALL_CUDA_TORCH_WORKSTATION.bat" -ForegroundColor Gray
        if ($RepoName -eq "CorpusForge") {
            Write-Host "    Offline reuse from existing HybridRAG torch:" -ForegroundColor Gray
            Write-Host "      COPY_TORCH_FROM_EXISTING_HYBRIDRAG.bat" -ForegroundColor Gray
        }
        Write-Host "    Manual retry:" -ForegroundColor Gray
        Write-Host "      .venv\Scripts\pip.exe install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org" -ForegroundColor Gray
        Write-Host "    Direct wheel fallback example for Python 3.12 64-bit:" -ForegroundColor Gray
        Write-Host "      torch-2.7.1+cu128-cp312-cp312-win_amd64.whl" -ForegroundColor Gray
    } else {
        Write-Host "    CPU fallback:" -ForegroundColor Gray
        Write-Host "      .venv\Scripts\pip.exe install torch==2.7.1 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org" -ForegroundColor Gray
    }
}

function Resolve-NativeCommandPath {
    param(
        [string]$CommandName,
        [string[]]$CandidatePaths = @()
    )
    try {
        $cmd = Get-Command $CommandName -ErrorAction Stop | Select-Object -First 1
        if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
            return (Resolve-Path $cmd.Source).Path
        }
        if ($cmd -and $cmd.Path -and (Test-Path $cmd.Path)) {
            return (Resolve-Path $cmd.Path).Path
        }
    } catch {
    }

    foreach ($candidate in $CandidatePaths) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }
    return $null
}

function Invoke-WithRetry {
    param(
        [scriptblock]$Action,
        [string]$Label,
        [int]$MaxAttempts = 3
    )
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        Write-Info "Attempt $i/$MaxAttempts -- $Label"
        try {
            & $Action
            if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) { return $true }
        } catch { }
        if ($i -lt $MaxAttempts) { Start-Sleep -Seconds 5 }
    }
    return $false
}

# ============================================================
# 2. Detect project root
# ============================================================
Write-Step "Detecting project root"
$ToolsDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ToolsDir

if (-not (Test-Path (Join-Path $ProjectRoot "src\pipeline.py"))) {
    Write-Fail "Not a CorpusForge project root -- missing src\pipeline.py at $ProjectRoot"
    exit 1
}
Write-Ok "Project root: $ProjectRoot"
Set-Location $ProjectRoot

# ============================================================
# 3. Detect Python 3.12
# ============================================================
Write-Step "Detecting Python 3.12"
$pyVersion = $null
try { $pyVersion = & py -3.12 --version 2>&1 } catch { }

if ($pyVersion -match "Python 3\.12") {
    Write-Ok "Found: $pyVersion"
} else {
    Write-Fail "Python 3.12 not found via 'py -3.12'. Install Python 3.12 from python.org."
    exit 1
}

# ============================================================
# 4. Create .venv
# ============================================================
Write-Step "Creating virtual environment"
$VenvDir    = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"

if (Test-Path $VenvPython) {
    Write-Ok ".venv already exists"
} else {
    $ok = Invoke-WithRetry -Label "py -3.12 -m venv .venv" -Action {
        & py -3.12 -m venv "$VenvDir"
    }
    if ($ok) { Write-Ok ".venv created" } else { Write-Fail "Could not create .venv"; exit 1 }
}

# Activate (for this process only)
$env:VIRTUAL_ENV = $VenvDir
$env:PATH = (Join-Path $VenvDir "Scripts") + ";" + $env:PATH
$PipIni = Join-Path $VenvDir "pip.ini"
Initialize-PipConfig -PipIniPath $PipIni
Write-Ok "Created proxy-safe pip config: $PipIni"
$RequireCuda = Test-NvidiaGpuPresent
$RuntimeInfo = Get-PythonRuntimeInfo -PythonExe $VenvPython

# ============================================================
# 5. Upgrade pip + pip-system-certs
# ============================================================
Write-Step "Upgrading pip and installing pip-system-certs"
& $VenvPython -m pip install --upgrade pip @TrustedHosts --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Ok "pip upgraded" } else { Write-Warn "pip upgrade returned non-zero" }

& $VenvPip install pip-system-certs @TrustedHosts --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Ok "pip-system-certs installed" } else { Write-Warn "pip-system-certs failed (non-blocking)" }

# ============================================================
# 6. Install torch CUDA (BEFORE requirements.txt)
# ============================================================
Write-Step "Installing torch"
if ($RequireCuda) {
    $ok = Invoke-WithRetry -Label "pip install torch==2.7.1 (cu128)" -Action {
        & $VenvPip install "torch==2.7.1" --index-url https://download.pytorch.org/whl/cu128 --force-reinstall --no-deps @TrustedHosts --quiet 2>&1 | Out-Null
    }
    if ($ok) {
        Write-Ok "torch CUDA installed (2.7.1 cu128)"
    } else {
        Write-Fail "torch CUDA install failed after 3 attempts"
        Write-TorchInstallGuidance -RepoName "CorpusForge" -RuntimeInfo $RuntimeInfo -CudaExpected
        exit 1
    }
} else {
    Write-Warn "No NVIDIA GPU detected -- installing CPU torch fallback"
    $ok = Invoke-WithRetry -Label "pip install torch==2.7.1 (CPU)" -Action {
        & $VenvPip install "torch==2.7.1" @TrustedHosts --quiet 2>&1 | Out-Null
    }
    if ($ok) {
        Write-Ok "torch CPU fallback installed"
    } else {
        Write-Fail "torch CPU fallback install failed after 3 attempts"
        Write-TorchInstallGuidance -RepoName "CorpusForge" -RuntimeInfo $RuntimeInfo
        exit 1
    }
}

# ============================================================
# 7. Install requirements.txt (with retry + drill-down)
# ============================================================
Write-Step "Installing requirements.txt"
$reqFile = Join-Path $ProjectRoot "requirements.txt"
if (-not (Test-Path $reqFile)) {
    Write-Fail "requirements.txt not found at $reqFile"
    exit 1
}

$ok = Invoke-WithRetry -Label "pip install -r requirements.txt" -Action {
    & $VenvPip install -r $reqFile @TrustedHosts --quiet 2>&1 | Out-Null
}

if ($ok) {
    Write-Ok "All requirements installed"
} else {
    Write-Warn "Bulk install failed -- drilling down to per-package install"
    $lines = Get-Content $reqFile | Where-Object { $_ -match '^\s*[a-zA-Z]' -and $_ -notmatch '^\s*#' }
    $drillFails = @()
    foreach ($line in $lines) {
        $pkg = ($line -split '#')[0].Trim()
        if ([string]::IsNullOrWhiteSpace($pkg)) { continue }
        # Skip torch (already installed from CUDA index)
        if ($pkg -match '^torch(\s|$|=|>|<)') { continue }
        Write-Info "  Installing: $pkg"
        & $VenvPip install $pkg @TrustedHosts --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "  Failed: $pkg"
            $drillFails += $pkg
        }
    }
    if ($drillFails.Count -gt 0) {
        Write-Fail "Drill-down failures: $($drillFails -join ', ')"
    } else {
        Write-Ok "All packages installed via drill-down"
    }
}

# ============================================================
# 8. Verify CUDA torch
# ============================================================
Write-Step "Verifying CUDA torch"
$verifyPy = Join-Path $env:TEMP "cf_verify_cuda.py"
$verifyCode = @'
import torch
cuda = torch.cuda.is_available()
count = torch.cuda.device_count()
ver = torch.__version__
print(f"torch {ver}, CUDA={cuda}, devices={count}")
if not cuda:
    raise SystemExit(1)
'@
[System.IO.File]::WriteAllText($verifyPy, $verifyCode, [System.Text.UTF8Encoding]::new($false))
$cudaCheck = & $VenvPython $verifyPy 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok $cudaCheck
} elseif (-not $RequireCuda) {
    Write-Warn "torch CUDA not available: $cudaCheck"
    Write-Info "CPU-only fallback is acceptable on machines without NVIDIA GPUs"
} else {
    Write-Fail "torch CUDA not available: $cudaCheck"
    exit 1
}
Remove-TempFileQuietly -Path $verifyPy

# ============================================================
# 9. Verify key imports
# ============================================================
Write-Step "Verifying key imports"
$importPy = Join-Path $env:TEMP "cf_verify_imports.py"
$importCode = @'
import sys, importlib
packages = [
    "numpy", "pydantic", "yaml", "sentence_transformers",
    "pdfplumber", "structlog", "rich", "tqdm", "tiktoken",
    "onnxruntime", "PIL", "lxml", "openpyxl", "psutil",
    "cryptography", "ezdxf",
]
fails = []
for pkg in packages:
    try:
        importlib.import_module(pkg)
        ver = getattr(sys.modules[pkg], "__version__", "OK")
        print(f"  OK: {pkg} {ver}")
    except ImportError as e:
        print(f"  FAIL: {pkg} -- {e}")
        fails.append(pkg)
if fails:
    print("FAILED_IMPORTS=" + ",".join(fails))
    raise SystemExit(1)
print("ALL_IMPORTS_OK")
'@
[System.IO.File]::WriteAllText($importPy, $importCode, [System.Text.UTF8Encoding]::new($false))
$importResult = & $VenvPython $importPy 2>&1
$importOutput = ($importResult | Out-String).Trim()
if ($LASTEXITCODE -eq 0) {
    foreach ($line in ($importOutput -split "`n")) {
        if ($line -match "OK:") { Write-Ok $line.Trim() }
    }
} else {
    foreach ($line in ($importOutput -split "`n")) {
        $trimmed = $line.Trim()
        if ($trimmed -match "OK:") { Write-Ok $trimmed }
        elseif ($trimmed -match "FAIL:") { Write-Fail $trimmed }
    }
}
Remove-TempFileQuietly -Path $importPy

# ============================================================
# 10. Check Ollama
# ============================================================
Write-Step "Checking Ollama service"
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:11434/api/version" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    Write-Ok "Ollama running: $($resp.Content)"
} catch {
    Write-Warn "Ollama not reachable at localhost:11434 -- start with 'ollama serve' if needed"
}

# ============================================================
# 11. Check OCR toolchain
# ============================================================
Write-Step "Checking OCR toolchain"
$tesseractPath = Resolve-NativeCommandPath -CommandName "tesseract.exe" -CandidatePaths @(
    "C:\Program Files\Tesseract-OCR\tesseract.exe",
    "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
)
$popplerPath = Resolve-NativeCommandPath -CommandName "pdftoppm.exe" -CandidatePaths @(
    "C:\tools\poppler\Library\bin\pdftoppm.exe",
    "C:\Program Files\poppler\Library\bin\pdftoppm.exe",
    "C:\Program Files\poppler\bin\pdftoppm.exe"
)
if ($tesseractPath) {
    Write-Ok "Tesseract found: $tesseractPath"
} else {
    Write-Warn "Tesseract not found -- scanned PDF OCR will be degraded"
}
if ($popplerPath) {
    Write-Ok "Poppler pdftoppm found: $popplerPath"
} else {
    Write-Warn "Poppler not found -- pdf2image OCR fallback will fail"
}

# ============================================================
# 12. Check phi4 model
# ============================================================
Write-Step "Checking phi4 model"
try {
    $models = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($models.Content -match "phi4") {
        Write-Ok "phi4 model found"
    } else {
        Write-Warn "phi4 not found -- pull with: ollama pull phi4:14b-q4_K_M"
    }
} catch {
    Write-Warn "Could not query Ollama models (service may be down)"
}

# ============================================================
# 13. Environment summary
# ============================================================
Write-Step "Setting environment variables"
$env:CUDA_VISIBLE_DEVICES = "0"
$env:PYTHONUTF8 = "1"
Write-Ok "CUDA_VISIBLE_DEVICES=0, PYTHONUTF8=1, NO_PROXY=localhost,127.0.0.1"
Write-Info "Project root: $ProjectRoot"
Write-Info "pip.ini: $PipIni"
Write-Info "Python: $VenvPython"

# ============================================================
# 13. Smoke test -- Embedder with CUDA
# ============================================================
Write-Step "Running embedding smoke test"
$smokePy = Join-Path $env:TEMP "corpusforge_smoke_test.py"
$smokeCode = @'
import torch
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True, device="cuda")
emb = model.encode(["search_document: CorpusForge smoke test"])
assert emb.shape[1] == 768, f"Expected dim 768, got {emb.shape[1]}"
print(f"Embedding OK: device=cuda, dim={emb.shape[1]}, dtype={emb.dtype}")
'@
[System.IO.File]::WriteAllText($smokePy, $smokeCode, [System.Text.UTF8Encoding]::new($false))
$smokeResult = & $VenvPython $smokePy 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok $smokeResult
} else {
    Write-Fail "Embedding smoke test failed: $smokeResult"
}
Remove-TempFileQuietly -Path $smokePy

# ============================================================
# 14. Final summary
# ============================================================
$Stopwatch.Stop()
Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "  CorpusForge Workstation Setup Complete -- $(Format-Elapsed)" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "  PASS: $global:PassCount" -ForegroundColor Green
if ($global:WarnCount -gt 0) { Write-Host "  WARN: $global:WarnCount" -ForegroundColor Yellow }
if ($global:FailCount -gt 0) { Write-Host "  FAIL: $global:FailCount" -ForegroundColor Red }
Write-Host ("=" * 60) -ForegroundColor Cyan

if ($global:FailCount -gt 0) {
    Write-Host "`n  Setup completed with failures. Review output above." -ForegroundColor Red
    exit 1
} else {
    Write-Host "`n  Environment ready. Activate with:" -ForegroundColor Green
    Write-Host "    .venv\Scripts\activate" -ForegroundColor White
    exit 0
}
