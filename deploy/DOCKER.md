# AI Agent — Docker 一键部署

## 项目结构（与镜像对应）

```text
agent/
├── Dockerfile              # 多阶段：Node 构建前端 + Python 后端
├── docker-compose.yml      # 默认服务 app（一键）
├── .dockerignore
├── .env.docker.example     # 环境变量模板 → 复制为 .env
├── backend/                # FastAPI + LangChain Agent / RAG / Memory
├── frontend/               # Vue 3（构建产物由 FastAPI 托管）
└── deploy/
    ├── Caddyfile           # 可选 profile=gateway
    └── DOCKER.md           # 本文
```

默认形态：**单容器**，端口 `8000`，`SERVE_FRONTEND=true`，前后端同域。

## 前置条件

- Docker Engine 24+ / Docker Compose v2
- 可用的 LLM API Key（如智谱 `OPENAI_API_KEY`）

## 一键启动

```bash
# 1. 进入仓库根目录
cd /path/to/agent

# 2. 配置环境变量
cp .env.docker.example .env
# 编辑 .env，至少填入：
#   OPENAI_API_KEY=...
#   AUTH_SECRET=...（公网务必修改）

# 3. 构建并启动
docker compose up --build -d

# 4. 查看状态
docker compose ps
docker compose logs -f app
```

浏览器打开：**http://localhost:8000**

健康检查：**http://localhost:8000/health** → `{"status":"ok"}`

### Demo 账号

首次启动会执行 `scripts/seed_demo_user.py`：

| 用户名 | 密码 |
|--------|------|
| `demo` | `Demo2026!` |

（`AUTH_DISABLED=true` 时可跳过登录，仅建议本地。）

## 常用命令

```bash
# 停止
docker compose down

# 停止并删除数据卷（清空用户/会话/向量库）
docker compose down -v

# 仅重建应用镜像
docker compose up --build -d app

# 改端口（例如 9000）
# 在 .env 中设置 APP_PORT=9000 后重新 up
```

## 环境变量说明

| 变量 | 说明 | 默认 |
|------|------|------|
| `OPENAI_API_KEY` | LLM API Key（必填） | — |
| `OPENAI_BASE_URL` | 兼容接口地址 | 智谱示例 |
| `OPENAI_MODEL` | 对话模型 | `glm-4.7` |
| `EMBEDDING_MODEL` | 向量模型 | `embedding-3` |
| `AUTH_DISABLED` | 关闭鉴权 | `false` |
| `AUTH_SECRET` | JWT 密钥 | 务必修改 |
| `CORS_ORIGINS` | 跨域白名单 | `*` |
| `APP_PORT` | 宿主机映射端口 | `8000` |
| `SERVE_FRONTEND` | 由 FastAPI 托管 `frontend/dist` | compose 内 `true` |

数据目录通过 Docker Volume 持久化：`agent-data` / `agent-rag` / `agent-memory`。

## 可选：Caddy 网关（80/443）

```bash
docker compose --profile gateway up --build -d
```

请先按域名修改 `deploy/Caddyfile`（将 `demo.example.com` 换成真实域名或 `:80`）。  
网关模式下建议在 `.env` 将 `CORS_ORIGINS` 设为你的前端域名。

## 仅构建后端镜像（云平台 / Railway）

仍可使用 `backend/Dockerfile`（不打包前端）：

```bash
docker build -t agent-backend ./backend
```

## 故障排查

1. **`env file .env not found`**  
   未复制模板：`cp .env.docker.example .env`

2. **页面空白 / API 502**  
   `docker compose logs app`；确认 `OPENAI_API_KEY` 有效；等待 healthcheck（首次 pip/构建较慢）。

3. **权限 / 数据库**  
   卷权限异常时可 `docker compose down -v` 后重建（会清空数据）。

4. **SSE 长时间无响应**  
   检查上游 LLM 网络；本机一键模式无额外反向代理超时限制。
