#!/bin/sh
set -e

# Railway Volume 通常挂在 /data；本地无挂载时回退到相对路径
mkdir -p "${RAG_STORE_PATH:-rag/store}" \
         "${MEMORY_STORE_PATH:-memory/store}" \
         "$(dirname "${USERS_DB_PATH:-data/users.db}")" \
         "$(dirname "${CONVERSATIONS_DB_PATH:-data/conversations.db}")"

# 幂等创建 Demo 账号（失败不阻断启动，避免首次无 DB 权限时卡死）
python scripts/seed_demo_user.py || true

PORT="${PORT:-8000}"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT" --workers 1
