$ErrorActionPreference = "Stop"
$taskName = "FT-Research Backend"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  Write-Host "已移除登录自启动任务：$taskName"
} else {
  Write-Host "未找到登录自启动任务：$taskName"
}
