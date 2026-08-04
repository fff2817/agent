FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/data /data/rag/store /data/memory/store

ENV PYTHONUNBUFFERED=1 \
    RAG_STORE_PATH=/data/rag/store \
    MEMORY_STORE_PATH=/data/memory/store \
    USERS_DB_PATH=/data/data/users.db \
    SESSIONS_DB_PATH=/data/data/sessions.db \
    CONVERSATIONS_DB_PATH=/data/data/conversations.db \
    EVAL_DB_PATH=/data/data/evaluations.db \
    SERVE_FRONTEND=false \
    AUTH_DISABLED=false \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# 使用 sh -c 避免 Windows CRLF 导致 entrypoint.sh 启动失败；PORT 由 Railway 注入
CMD ["sh", "-c", "mkdir -p \"$RAG_STORE_PATH\" \"$MEMORY_STORE_PATH\" \"$(dirname \"$USERS_DB_PATH\")\" && (python scripts/seed_demo_user.py || true) && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
