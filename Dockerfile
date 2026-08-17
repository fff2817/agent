# 构建上下文：仓库根目录
# 多阶段：前端 Vite 构建 → 后端 FastAPI 托管静态资源（SERVE_FRONTEND=true）

# ---------- 前端 ----------
FROM node:22-alpine AS frontend

WORKDIR /fe

COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
# 同域部署：浏览器请求当前 origin，无需写死后端地址
ENV VITE_API_BASE_URL=
RUN npm run build

# ---------- 后端 + 静态资源 ----------
FROM python:3.11-slim-bookworm

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /workspace/backend/requirements.txt
RUN pip install --no-cache-dir -r /workspace/backend/requirements.txt

COPY backend/ /workspace/backend/
COPY --from=frontend /fe/dist /workspace/frontend/dist

RUN mkdir -p /data/data /data/rag/store /data/memory/store

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/backend \
    RAG_STORE_PATH=/data/rag/store \
    MEMORY_STORE_PATH=/data/memory/store \
    USERS_DB_PATH=/data/data/users.db \
    SESSIONS_DB_PATH=/data/data/sessions.db \
    CONVERSATIONS_DB_PATH=/data/data/conversations.db \
    EVAL_DB_PATH=/data/data/evaluations.db \
    SERVE_FRONTEND=true \
    AUTH_DISABLED=false \
    PORT=8000

WORKDIR /workspace/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=5 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["sh", "-c", "mkdir -p \"$RAG_STORE_PATH\" \"$MEMORY_STORE_PATH\" \"$(dirname \"$USERS_DB_PATH\")\" && (python scripts/seed_demo_user.py || true) && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
