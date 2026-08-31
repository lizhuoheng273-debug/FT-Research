$ErrorActionPreference = "Stop"
$taskName = "FT-Research Backend"
$startScript = Join-Path $PSScriptRoot "start-backend.ps1"

if (-not (Test-Path -LiteralPath $startScript)) {
  throw "Start script not found: $startScript"
}

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 3650) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Start the local FT-Research FastAPI backend for the hosted frontend." `
  -User $env:USERNAME `
  -RunLevel Limited `
  -Force | Out-Null

Write-Host "Registered logon startup task: $taskName"
Write-Host "To remove it, run scripts\\unregister-backend-task.ps1"
