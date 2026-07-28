FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh \
    && mkdir -p /data/data /data/rag/store /data/memory/store

ENV PYTHONUNBUFFERED=1 \
    RAG_STORE_PATH=/data/rag/store \
    MEMORY_STORE_PATH=/data/memory/store \
    USERS_DB_PATH=/data/data/users.db \
    SESSIONS_DB_PATH=/data/data/sessions.db \
    EVAL_DB_PATH=/data/data/evaluations.db \
    SERVE_FRONTEND=false \
    AUTH_DISABLED=false

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["./entrypoint.sh"]
