#Requires -Version 5.1
<#
.SYNOPSIS
    Copy a working torch install from an existing HybridRAG workstation venv into CorpusForge (Forge).

.DESCRIPTION
    === NON-PROGRAMMER GUIDE ===
    What this does: Finds a local HybridRAG .venv that already has working CUDA torch, then copies
                    the torch package set into this Forge .venv so Forge can use the same local build.
    When to run:    Only when the normal internet install is blocked (corporate proxy, offline site).
                    Called by COPY_TORCH_FROM_EXISTING_HYBRIDRAG.bat at the repo root.
    Operator view:  PASS lines are green, WARN yellow, FAIL red. Success exits 0 after a verify import.
                    Any failure exits 1 with a red FAIL line and no partial state left behind.
    Prerequisites:  Forge .venv already exists (INSTALL_WORKSTATION.bat ran once). A source .venv on
                    the same machine with the SAME Python version (e.g., both 3.12 64-bit).
    Inputs:  Optional -SourceVenv path. If omitted, common HybridRAG paths are auto-scanned.
    Outputs: torch + dependencies copied into this repo's .venv\Lib\site-packages.
#>

param(
    [string]$SourceVenv = ""
)

# UTF-8 console output + loopback-safe proxy defaults so pip and local services behave.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:no_proxy = "localhost,127.0.0.1"
# Stop on first error so we never leave the .venv half-copied.
$ErrorActionPreference = "Stop"

function Write-Ok   { param([string]$Message) Write-Host "  [OK] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "  [WARN] $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "  [FAIL] $Message" -ForegroundColor Red }
function Write-Info { param([string]$Message) Write-Host "  [INFO] $Message" -ForegroundColor Gray }

# Read Python version + tag (cp312) + 64-bit status from a given python.exe; returns null on failure.
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
    $raw = & $PythonExe -c $probe 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return ($raw | ConvertFrom-Json)
}

# Build the list of likely HybridRAG .venv locations on this machine, skipping the target itself.
function Get-SourceCandidates {
    param([string]$TargetVenv)
    $userProfile = [Environment]::GetFolderPath("UserProfile")
    $candidates = @(
        (Join-Path $userProfile "Desktop1\HybridRAG3\.venv"),
        (Join-Path $userProfile "Desktop1\HybridRAG3_Educational\.venv"),
        (Join-Path $userProfile "Desktop1\HybridRAG_V2\.venv"),
        (Join-Path $userProfile "Documents\HybridRAG3\.venv"),
        (Join-Path $userProfile "Documents\HybridRAG3_Educational\.venv"),
        (Join-Path $userProfile "Documents\HybridRAG_V2\.venv"),
        "C:\HybridRAG3_DesktopProd\.venv",
        "C:\HybridRAG3_Educational\.venv",
        "C:\HybridRAG_V2\.venv"
    )
    return $candidates |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        ForEach-Object { $_.TrimEnd('\') } |
        Select-Object -Unique |
        Where-Object { $_ -ne $TargetVenv -and (Test-Path (Join-Path $_ "Scripts\python.exe")) }
}

# Collect torch + all directly related package folders/dist-info entries in a source site-packages.
function Get-MatchingEntries {
    param([string]$SitePackages)
    $patterns = @(
        "torch",
        "torch-*.dist-info",
        "torchgen",
        "torchgen-*.dist-info",
        "functorch",
        "functorch-*.dist-info",
        "torchvision",
        "torchvision-*.dist-info",
        "torchaudio",
        "torchaudio-*.dist-info",
        "filelock",
        "filelock-*.dist-info",
        "typing_extensions.py",
        "typing_extensions-*.dist-info",
        "sympy",
        "sympy-*.dist-info",
        "networkx",
        "networkx-*.dist-info",
        "jinja2",
        "jinja2-*.dist-info",
        "fsspec",
        "fsspec-*.dist-info",
        "mpmath",
        "mpmath-*.dist-info",
        "markupsafe",
        "MarkupSafe-*.dist-info"
    )

    $items = @()
    foreach ($pattern in $patterns) {
        $items += Get-ChildItem -Path $SitePackages -Filter $pattern -Force -ErrorAction SilentlyContinue
    }
    return $items | Sort-Object FullName -Unique
}

# Resolve repo root from this script's location (tools\ sits one level below repo root).
$projectRoot = Split-Path -Parent $PSScriptRoot
$targetVenv = Join-Path $projectRoot ".venv"
$targetPython = Join-Path $targetVenv "Scripts\python.exe"
$targetSitePackages = Join-Path $targetVenv "Lib\site-packages"

Write-Host ""
Write-Host "CorpusForge -- Offline Torch Reuse" -ForegroundColor Cyan
Write-Host ""
Write-Info "Project root: $projectRoot"
Write-Info "Target venv:  $targetVenv"

if (-not (Test-Path $targetPython)) {
    Write-Fail "Target .venv is missing. Run INSTALL_WORKSTATION.bat once first so .venv exists."
    exit 1
}
if (-not (Test-Path $targetSitePackages)) {
    Write-Fail "Target site-packages folder is missing: $targetSitePackages"
    exit 1
}

$targetInfo = Get-PythonRuntimeInfo -PythonExe $targetPython
if (-not $targetInfo) {
    Write-Fail "Could not read target Python runtime info."
    exit 1
}
Write-Info ("Target Python: {0} ({1}, 64-bit={2})" -f $targetInfo.python_version, $targetInfo.python_tag, $targetInfo.is_64bit)

$candidateVenvs = @()
if (-not [string]::IsNullOrWhiteSpace($SourceVenv)) {
    $explicit = $SourceVenv.Trim('"').Trim()
    if (-not (Test-Path (Join-Path $explicit "Scripts\python.exe"))) {
        Write-Fail "Explicit source venv not found or invalid: $explicit"
        exit 1
    }
    $candidateVenvs = @($explicit)
} else {
    $candidateVenvs = Get-SourceCandidates -TargetVenv $targetVenv
}

if (-not $candidateVenvs -or $candidateVenvs.Count -eq 0) {
    Write-Fail "No valid HybridRAG source venvs were found."
    Write-Info "Common paths checked:"
    Write-Info "  %USERPROFILE%\Desktop1\HybridRAG3\.venv"
    Write-Info "  %USERPROFILE%\Desktop1\HybridRAG3_Educational\.venv"
    Write-Info "  %USERPROFILE%\Desktop1\HybridRAG_V2\.venv"
    Write-Info "  %USERPROFILE%\Documents\HybridRAG3\.venv"
    Write-Info "  %USERPROFILE%\Documents\HybridRAG3_Educational\.venv"
    Write-Info "  %USERPROFILE%\Documents\HybridRAG_V2\.venv"
    Write-Info "  C:\HybridRAG3_DesktopProd\.venv"
    Write-Info "  C:\HybridRAG3_Educational\.venv"
    Write-Info "  C:\HybridRAG_V2\.venv"
    exit 1
}

# Walk the candidate list and pick the first source whose Python tag + 64-bit match the target.
$selectedSource = $null
$selectedSourceInfo = $null
foreach ($candidate in $candidateVenvs) {
    $candidatePython = Join-Path $candidate "Scripts\python.exe"
    $candidateInfo = Get-PythonRuntimeInfo -PythonExe $candidatePython
    if (-not $candidateInfo) {
        Write-Warn "Skipping unreadable source venv: $candidate"
        continue
    }
    if ($candidateInfo.python_tag -ne $targetInfo.python_tag) {
        Write-Warn ("Skipping {0} because Python tag {1} does not match target {2}" -f $candidate, $candidateInfo.python_tag, $targetInfo.python_tag)
        continue
    }
    if ($candidateInfo.is_64bit -ne $targetInfo.is_64bit) {
        Write-Warn ("Skipping {0} because 64-bit status does not match target." -f $candidate)
        continue
    }
    $selectedSource = $candidate
    $selectedSourceInfo = $candidateInfo
    break
}

if (-not $selectedSource) {
    Write-Fail "No source venv matched the target Python runtime."
    exit 1
}

$sourceSitePackages = Join-Path $selectedSource "Lib\site-packages"
if (-not (Test-Path $sourceSitePackages)) {
    Write-Fail "Source site-packages folder is missing: $sourceSitePackages"
    exit 1
}

Write-Ok ("Using source venv: {0}" -f $selectedSource)
Write-Info ("Source Python: {0} ({1}, 64-bit={2})" -f $selectedSourceInfo.python_version, $selectedSourceInfo.python_tag, $selectedSourceInfo.is_64bit)

$entries = Get-MatchingEntries -SitePackages $sourceSitePackages
if (-not $entries -or $entries.Count -eq 0) {
    Write-Fail "No torch package set was found in the source venv."
    exit 1
}

# Wipe any existing torch set in the target so the copy lands cleanly.
$targetEntries = Get-MatchingEntries -SitePackages $targetSitePackages
foreach ($entry in $targetEntries) {
    Remove-Item -LiteralPath $entry.FullName -Force -Recurse -ErrorAction SilentlyContinue
}

# Copy each source entry (folder or file) into the target site-packages.
foreach ($entry in $entries) {
    $destination = Join-Path $targetSitePackages $entry.Name
    if ($entry.PSIsContainer) {
        Copy-Item -LiteralPath $entry.FullName -Destination $destination -Recurse -Force
    } else {
        Copy-Item -LiteralPath $entry.FullName -Destination $destination -Force
    }
}

Write-Ok "Copied torch package set into CorpusForge .venv"

# Verify the copy worked by importing torch in the target Python and printing version / CUDA status.
$verify = & $targetPython -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Torch import verification failed after copy:"
    Write-Host $verify -ForegroundColor Red
    exit 1
}

$verifyLines = $verify -split "`r?`n"
Write-Ok ("Torch version: {0}" -f $verifyLines[0])
if ($verifyLines.Count -gt 1) {
    Write-Info ("Built CUDA: {0}" -f $verifyLines[1])
}
if ($verifyLines.Count -gt 2) {
    Write-Info ("CUDA available: {0}" -f $verifyLines[2])
}

Write-Host ""
Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "  .venv\Scripts\pip.exe install -r requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org" -ForegroundColor Gray
Write-Host ""
exit 0
