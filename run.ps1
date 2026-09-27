$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "未找到 Python。请安装 Python 3.11，并创建 .venv 或激活 Conda/venv 环境。"
    }
    $python = $pythonCommand.Source
}

Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "已根据 .env.example 创建 .env"
}

& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

