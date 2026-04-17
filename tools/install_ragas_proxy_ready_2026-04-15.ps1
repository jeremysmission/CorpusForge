#Requires -Version 5.1
<#
.SYNOPSIS
    Proxy-aware RAGAS installer for a repo-local .venv.

.DESCRIPTION
    === NON-PROGRAMMER GUIDE ===
    What this does: Installs pinned RAGAS (answer-quality evaluation) packages into the Forge .venv
                    using UTF-8-safe console output and a proxy picked up from env vars or the
                    Windows Internet Settings. Can also run the repo's RAGAS readiness probe.
    When to run:    Once, when the operator wants to enable RAGAS-based answer scoring. Re-run after
                    wiping .venv. Not part of the normal daily run.
    Operator view:  [INFO] lines for context, [PASS] green on success. Any step that fails throws
                    and exits nonzero. Pass -DryRun to preview without touching packages.
    Prerequisites:  Forge .venv already exists at .\.venv\Scripts\python.exe. Internet or corporate
                    proxy access to PyPI.
    Pins:
      - ragas==0.4.3
      - rapidfuzz==3.14.5

.NOTES
    Date: 2026-04-15
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$VerifyRunner
)

# Stop on first error so a partial install cannot leave the .venv in a mixed state.
$ErrorActionPreference = "Stop"
# UTF-8 console output + loopback-safe proxy defaults (localhost / ::1 always bypass any proxy).
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = $env:NO_PROXY

function Write-Info([string]$Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

# Pick a proxy URL: env vars win; otherwise read the Windows Internet Settings. Empty string if none.
function Get-ProxyUrl {
    $explicit = $env:HTTPS_PROXY
    if ([string]::IsNullOrWhiteSpace($explicit)) {
        $explicit = $env:HTTP_PROXY
    }
    if (-not [string]::IsNullOrWhiteSpace($explicit)) {
        if ($explicit -notmatch "^https?://") {
            $explicit = "http://$explicit"
        }
        return $explicit
    }

    try {
        $inetSettings = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        $proxyEnabled = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).ProxyEnable
        $proxyServer = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).ProxyServer
        if ($proxyEnabled -eq 1 -and $proxyServer) {
            $resolved = $proxyServer
            if ($proxyServer -match "https=([^;]+)") {
                $resolved = $Matches[1]
            } elseif ($proxyServer -match "http=([^;]+)") {
                $resolved = $Matches[1]
            }
            if ($resolved -notmatch "^https?://") {
                $resolved = "http://$resolved"
            }
            return $resolved
        }
    } catch {
    }

    return ""
}

# Resolve repo root (tools\ sits one level below) and bind to the repo-local Python.
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runnerPath = Join-Path $repoRoot "scripts\run_ragas_eval.py"
# Pinned RAGAS + rapidfuzz; any drift here should be reviewed intentionally.
$packages = @("ragas==0.4.3", "rapidfuzz==3.14.5")
# Standard pip args: trusted hosts for corporate proxies, 120s timeout, auto-retry 3x.
$pipArgs = @(
    "-m", "pip", "install",
    "--trusted-host", "pypi.org",
    "--trusted-host", "pypi.python.org",
    "--trusted-host", "files.pythonhosted.org",
    "--timeout", "120",
    "--retries", "3"
) + $packages

if (-not (Test-Path $pythonExe)) {
    throw "Repo-local venv not found: $pythonExe"
}

# Export the resolved proxy URL into the current session so pip picks it up.
$proxyUrl = Get-ProxyUrl
if (-not [string]::IsNullOrWhiteSpace($proxyUrl)) {
    $env:HTTP_PROXY = $proxyUrl
    $env:HTTPS_PROXY = $proxyUrl
}

Write-Info "Repo root: $repoRoot"
Write-Info "Python: $pythonExe"
Write-Info ("Proxy: " + ($(if ($proxyUrl) { $proxyUrl } else { "<none-detected>" })))
Write-Info "Packages: $($packages -join ', ')"

if ($DryRun) {
    Write-Ok "Dry run only. No changes made."
    exit 0
}

# Install the pinned packages into the repo-local .venv.
& $pythonExe @pipArgs
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed."
}

# Confirm the packages actually import and print their versions.
& $pythonExe -c "import ragas, rapidfuzz, openai; print('ragas', ragas.__version__); print('rapidfuzz', rapidfuzz.__version__); print('openai', openai.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Import verification failed."
}

# Optional: run the repo's readiness probe in analysis-only mode when -VerifyRunner is passed.
if ($VerifyRunner -and (Test-Path $runnerPath)) {
    Write-Info "Running repo RAGAS readiness probe..."
    & $pythonExe $runnerPath --analysis-only
    if ($LASTEXITCODE -ne 0) {
        throw "Runner verification failed: $runnerPath"
    }
}

Write-Ok "RAGAS install complete."
