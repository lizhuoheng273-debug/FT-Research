param(
  [string]$BaseUrl = "http://127.0.0.1:8900"
)

$ErrorActionPreference = "Stop"
$status = Invoke-RestMethod -Uri "$BaseUrl/api/ai/status" -Method Get
if (-not $status.configured) {
  throw "GLM 未配置。请先在 backend/.env 设置 GLM_API_KEY。"
}

Write-Host "GLM 已配置：$($status.model) @ $($status.base_url)"
$body = @{ messages = @(@{ role = "user"; content = "请只回复：FT-Research smoke ok" }); context = "健康检查" } | ConvertTo-Json -Depth 5
$response = Invoke-WebRequest -Uri "$BaseUrl/api/chat" -Method Post -ContentType "application/json" -Body $body
if ($response.Content -notmatch '"type"\s*:\s*"done"') {
  throw "未收到完成事件，原始响应：$($response.Content.Substring(0, [Math]::Min(300, $response.Content.Length)))"
}
Write-Host "GLM 普通/流式链路检查通过。"
