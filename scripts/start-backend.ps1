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
    throw "Python not found. Install Python 3.11+ or create backend\\.venv."
  }
  $python = $pythonCommand.Source
}

if (-not (Test-Path -LiteralPath (Join-Path $backendRoot "app.py"))) {
  throw "FastAPI entrypoint not found: $backendRoot\\app.py"
}

Set-Location -LiteralPath $backendRoot
Write-Host "FT-Research backend starting on http://127.0.0.1:$Port"
& $python -m uvicorn app:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
