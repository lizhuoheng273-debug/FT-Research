$ErrorActionPreference = "Stop"
$taskName = "FT-Research Backend"
$startScript = Join-Path $PSScriptRoot "start-backend.ps1"

if (-not (Test-Path -LiteralPath $startScript)) {
  throw "找不到启动脚本：$startScript"
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

Write-Host "已注册登录自启动任务：$taskName"
Write-Host "如需取消，请运行 scripts\unregister-backend-task.ps1"
