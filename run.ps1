$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "E:\anaconda3\envs\ai-job-agent\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到 ai-job-agent 环境中的 Python: $python"
}

Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "已根据 .env.example 创建 .env"
}

& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

