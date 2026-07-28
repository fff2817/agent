# Windows 本地 Demo：构建前端 + 启动后端 + Cloudflare 快速隧道
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "==> 构建前端" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules")) { npm ci }
npm run build
Pop-Location

Write-Host "==> 检查后端依赖" -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend")
$venvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    python -m venv .venv
    & (Join-Path $Root "backend\.venv\Scripts\pip.exe") install -r requirements.txt
}

Write-Host "==> 初始化 Demo 用户" -ForegroundColor Cyan
$env:AUTH_DISABLED = "false"
$env:SERVE_FRONTEND = "true"
& $venvPython (Join-Path $Root "deploy\seed_demo_user.py")

Write-Host "==> 启动后端 (SERVE_FRONTEND=true, 端口 8000)" -ForegroundColor Cyan
Write-Host "    Demo 账号: demo / Demo2026!" -ForegroundColor Yellow
Write-Host "    本地访问: http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host ""
Write-Host "另开终端运行以下命令获取公网 URL:" -ForegroundColor Green
Write-Host "  winget install Cloudflare.cloudflared" -ForegroundColor White
Write-Host "  cloudflared tunnel --url http://127.0.0.1:8000" -ForegroundColor White
Write-Host ""

& $venvPython -m uvicorn main:app --host 0.0.0.0 --port 8000
