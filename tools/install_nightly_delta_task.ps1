<#
.SYNOPSIS
    Install the Windows Scheduled Task that runs CorpusForge (Forge) nightly delta ingest.

.DESCRIPTION
    === NON-PROGRAMMER GUIDE ===
    What this does: Registers a once-per-day Windows Scheduled Task that wakes up at the chosen time
                    and runs scripts\nightly_delta_ingest.py against the chosen config, so Forge picks
                    up new/changed source files without operator action.
    When to run:    Once, on the workstation that should own the nightly ingest. Re-run only if you
                    want to change the task name, schedule time, Python path, or flags.
    Operator view:  Prints the task name, repo root, Python, config, and start time on success.
                    Throws and exits nonzero if Python or the nightly script cannot be found.
    Prerequisites:  Must run in an elevated PowerShell (admin) because Register-ScheduledTask writes
                    to the system task store. Forge .venv exists and nightly_delta_ingest.py is present.
    Parameters:
      -TaskName        Scheduled task display name (default: "CorpusForge Nightly Delta Ingest").
      -RepoRoot        Repo folder (default: C:\CorpusForge).
      -PythonExe       Python to invoke (default: the repo's .venv Python).
      -ConfigPath      Config file passed to --config (default: config\config.yaml).
      -StartTime       HH:mm 24h start time (default: 01:00).
      -RequireCanary   Add --require-canary flag (task fails if canary sources are missing).
      -SkipPipeline    Add --skip-pipeline flag (scan + delta copy only, no ingest step).
#>

param(
    [string]$TaskName = "CorpusForge Nightly Delta Ingest",
    [string]$RepoRoot = "C:\CorpusForge",
    [string]$PythonExe = "C:\CorpusForge\.venv\Scripts\python.exe",
    [string]$ConfigPath = "config\config.yaml",
    [string]$StartTime = "01:00",
    [switch]$RequireCanary,
    [switch]$SkipPipeline
)

# Resolve paths and fail fast if Python or the nightly ingest script is missing.
$repoPath = (Resolve-Path $RepoRoot).Path
$pythonPath = $PythonExe
if (-not (Test-Path $pythonPath)) {
    throw "Python executable not found: $pythonPath"
}

$scriptPath = Join-Path $repoPath "scripts\nightly_delta_ingest.py"
if (-not (Test-Path $scriptPath)) {
    throw "Nightly ingest script not found: $scriptPath"
}

# Build the command-line args the scheduled task will pass to Python. Quote paths in case of spaces.
$argumentParts = @(
    "`"$scriptPath`"",
    "--config",
    "`"$ConfigPath`""
)

# Optional gating flags requested by operator switches.
if ($RequireCanary) {
    $argumentParts += "--require-canary"
}
if ($SkipPipeline) {
    $argumentParts += "--skip-pipeline"
}

# Scheduled-task action: run python.exe with the assembled args, working dir = repo root.
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument ($argumentParts -join " ") `
    -WorkingDirectory $repoPath

# Daily trigger at the operator-specified HH:mm time.
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($StartTime, "HH:mm", $null))
# Task settings: run on battery if needed, catch up on missed runs, never stack duplicate instances.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# Register (or overwrite via -Force) the task in Windows Task Scheduler.
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "CorpusForge nightly delta ingest: source scan, local delta copy, and pipeline handoff." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Repo root: $repoPath"
Write-Host "Python: $pythonPath"
Write-Host "Config: $ConfigPath"
Write-Host "Start time: $StartTime"
