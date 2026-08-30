param(
  [int]$Port = 8900
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$venvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $venvPython) {
  $python = $venvPython
} else {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if (-not $pythonCommand) {
    throw "未找到 Python。请先安装 Python 3.11+，或在 backend\.venv 中创建虚拟环境。"
  }
  $python = $pythonCommand.Source
}

if (-not (Test-Path -LiteralPath (Join-Path $backendRoot "app.py"))) {
  throw "找不到 FastAPI 入口：$backendRoot\app.py"
}

Set-Location -LiteralPath $backendRoot
Write-Host "FT-Research backend starting on http://127.0.0.1:$Port"
& $python -m uvicorn app:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
