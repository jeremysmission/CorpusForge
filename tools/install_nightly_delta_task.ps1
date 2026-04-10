param(
    [string]$TaskName = "CorpusForge Nightly Delta Ingest",
    [string]$RepoRoot = "C:\CorpusForge",
    [string]$PythonExe = "C:\CorpusForge\.venv\Scripts\python.exe",
    [string]$ConfigPath = "config\config.yaml",
    [string]$StartTime = "01:00",
    [switch]$RequireCanary,
    [switch]$SkipPipeline
)

$repoPath = (Resolve-Path $RepoRoot).Path
$pythonPath = $PythonExe
if (-not (Test-Path $pythonPath)) {
    throw "Python executable not found: $pythonPath"
}

$scriptPath = Join-Path $repoPath "scripts\nightly_delta_ingest.py"
if (-not (Test-Path $scriptPath)) {
    throw "Nightly ingest script not found: $scriptPath"
}

$argumentParts = @(
    "`"$scriptPath`"",
    "--config",
    "`"$ConfigPath`""
)

if ($RequireCanary) {
    $argumentParts += "--require-canary"
}
if ($SkipPipeline) {
    $argumentParts += "--skip-pipeline"
}

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument ($argumentParts -join " ") `
    -WorkingDirectory $repoPath

$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($StartTime, "HH:mm", $null))
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

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
