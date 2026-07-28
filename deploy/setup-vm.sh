#!/usr/bin/env bash
# Oracle / 任意 Linux VM 一键部署
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 检查 Docker"
command -v docker >/dev/null || { echo "请先安装 Docker"; exit 1; }
command -v docker compose >/dev/null || command -v docker-compose >/dev/null || {
  echo "请先安装 Docker Compose"
  exit 1
}

if [[ ! -f backend/.env.production ]]; then
  echo "请先复制 backend/.env.production.example 为 backend/.env.production 并填写密钥"
  exit 1
fi

echo "==> 构建前端"
cd frontend
npm ci
npm run build
cd "$ROOT"

echo "==> 启动服务"
docker compose up -d --build

#!/usr/bin/env bash
# Oracle / 任意 Linux VM 一键部署
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 检查 Docker"
command -v docker >/dev/null || { echo "请先安装 Docker"; exit 1; }

if [[ ! -f backend/.env.production ]]; then
  echo "请先复制 backend/.env.production.example 为 backend/.env.production 并填写密钥"
  exit 1
fi

echo "==> 构建前端"
cd frontend
npm ci
npm run build
cd "$ROOT"

echo "==> 启动服务"
docker compose up -d --build

echo "==> 初始化 Demo 用户"
docker compose exec -T backend python scripts/seed_demo_user.py

echo "==> 部署完成"
echo "    健康检查: curl http://127.0.0.1:8000/health"
echo "    Demo 账号: demo / Demo2026!"
echo "    请将 deploy/Caddyfile 中的 demo.example.com 改为你的域名"

echo "==> 部署完成"
echo "    健康检查: curl http://127.0.0.1:8000/health"
echo "    Demo 账号: demo / Demo2026!"
echo "    请将 deploy/Caddyfile 中的 demo.example.com 改为你的域名"
