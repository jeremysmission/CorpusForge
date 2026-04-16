#Requires -Version 5.1
<#
.SYNOPSIS
    Proxy-aware RAGAS installer for a repo-local .venv.

.DESCRIPTION
    Installs pinned RAGAS support into the current repository's .venv using
    UTF-8-safe console settings, loopback-safe NO_PROXY defaults, and either
    inherited proxy environment variables or the Windows Internet Settings
    proxy. Optionally runs the repo's RAGAS readiness probe when available.

.NOTES
    Date: 2026-04-15
    Pins:
      - ragas==0.4.3
      - rapidfuzz==3.14.5
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$VerifyRunner
)

$ErrorActionPreference = "Stop"
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

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runnerPath = Join-Path $repoRoot "scripts\run_ragas_eval.py"
$packages = @("ragas==0.4.3", "rapidfuzz==3.14.5")
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

& $pythonExe @pipArgs
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed."
}

& $pythonExe -c "import ragas, rapidfuzz, openai; print('ragas', ragas.__version__); print('rapidfuzz', rapidfuzz.__version__); print('openai', openai.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Import verification failed."
}

if ($VerifyRunner -and (Test-Path $runnerPath)) {
    Write-Info "Running repo RAGAS readiness probe..."
    & $pythonExe $runnerPath --analysis-only
    if ($LASTEXITCODE -ne 0) {
        throw "Runner verification failed: $runnerPath"
    }
}

Write-Ok "RAGAS install complete."
