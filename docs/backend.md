# 模块作用

**Backend（FastAPI 后端）** 是整个项目的 **HTTP 网关和业务编排层**。它负责：

- 接收前端请求（聊天、上传 PDF、RAG 问答）
- 调用 Agent、RAG、Memory 等内部模块
- 统一错误处理和 API 契约（Pydantic Schema）
- 提供健康检查，便于部署探活

没有这一层，前端无法安全、结构化地访问 LLM 和向量库。

# 核心原理

## FastAPI 是什么

FastAPI 是基于 Python 类型注解的现代 Web 框架，特点：

- 自动生成 OpenAPI 文档（访问 `/docs`）
- Pydantic 做请求/响应校验
- 原生支持 async（本项目路由虽为 async，核心 Agent 逻辑仍是同步调用 LLM）

## 本项目的 API 设计

| 端点 | 方法 | 职责 |
|------|------|------|
| `/health` | GET | 探活 |
| `/chat` | POST | ReAct Agent 聊天 |
| `/documents/upload` | POST | PDF 上传并入库 |
| `/rag/ask` | POST | 独立 RAG 文档问答 |
| `/rag/ingest` | POST | 纯文本入库 |

每个端点尽量 **薄**：只做参数校验、调用 service、写 Session、返回 DTO。

# 项目中的实现方式

## 应用入口

```1:35:backend/main.py
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat import router as chat_router
from api.documents import router as documents_router
from api.rag import router as rag_router
from core.config import get_settings
// ...
app = FastAPI(title=settings.app_name, debug=settings.debug)
// ...
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(rag_router)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- CORS 配置为 `allow_origins=["*"]`，方便本地 React 开发
- 日志格式：`时间 | 级别 | 模块 | 消息`

## 聊天 API

`backend/api/chat.py` 是 Agent 的主 HTTP 入口：

1. `get_or_create(session_id)` — 无 ID 则 UUID 新建
2. `get_history_messages()` — 加载多轮历史
3. `run_react_agent(message, history=history)` — 执行 ReAct
4. `add_turn()` — 保存本轮 user + assistant **最终回复**
5. 把 `result.trace` 转成 `ReActStepSchema` 列表返回

错误映射：

- `ValueError`（如 API Key 未配置、超步数）→ **503**
- 其他异常 → **502**

## 文档上传 API

`backend/api/documents.py`（逻辑概要）：

- 接收 `UploadFile`（PDF）
- 保存到 `rag/store/uploads/`
- 调用 `ingest_pdf()` 切分、向量化、写入 FAISS
- 返回 `filename`、`chunks_added`、`total_chunks`

## RAG API

`backend/api/rag.py`：

- `/rag/ask`：与 `/chat` 类似，先 Session 再 `rag_ask()`，返回 `sources` 和 `context_preview`
- `/rag/ingest`：接收 JSON 文本，调用 `ingest_text()`

## 数据模型

`backend/models/schemas.py` 定义全部 API 契约，例如：

- `ChatRequest`：`message` + 可选 `session_id`
- `ChatResponse`：`response` + `session_id` + `steps[]`
- `RAGAskResponse`：`answer` + `sources[]` + `session_id`

使用 Pydantic 可自动校验字段类型、长度，并在 `/docs` 生成交互式文档。

## 依赖与启动

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

环境变量见 `backend/.env.example`（智谱 GLM 示例）。

# 数据流

## POST /chat 完整路径

```
JSON Body: { message, session_id? }
    ↓
ChatRequest 校验
    ↓
SessionStore.get_or_create → get_history_messages
    ↓
agent.loop.run_react_agent
    ↓
SessionStore.add_turn
    ↓
ChatResponse JSON: { response, session_id, steps }
```

## POST /documents/upload

```
multipart file (PDF)
    ↓
保存 uploads/
    ↓
rag.ingest.ingest_pdf
    ↓ load_pdf → chunk_document → embed_chunks → FaissVectorStore.save
    ↓
DocumentUploadResponse
```

## 模块依赖关系

```
api/chat.py      → agent.loop, memory.session_store, models.schemas
api/rag.py       → rag.chain, rag.ingest, memory.session_store
api/documents.py → rag.ingest
core/config.py   ← 被所有模块读取
core/llm.py      ← agent, rag 共用
```

# 面试题

> 每题提供两版回答：**30 秒版**适合开场快速应答，**2 分钟版**适合面试官追问「展开讲讲」。

## 为什么选 FastAPI 而不是 Flask/Django？

### 简短回答（30秒版）

FastAPI 有类型注解 + Pydantic 自动校验，还能自动生成 OpenAPI 文档。Agent 项目 API 字段多（steps、sources），用 FastAPI 少写很多校验代码。它比 Flask 更现代，比 Django 更轻，适合 AI 微服务。

### 深入回答（2分钟版）

本项目 `backend/main.py` 用 FastAPI 挂载 chat/documents/rag 三组路由，`models/schemas.py` 定义 ChatRequest、ChatResponse、RAGAskResponse 等契约，访问 `/docs` 可直接调试。相比 Flask 需手写校验和文档，FastAPI 的 Pydantic 对 `message` 做 `min_length=1` 等约束，422 自动返回。Django 过重；FastAPI + Uvicorn 启动快、async 友好（虽当前 Agent 仍同步），是 Agent/RAG 类项目的常见选型。

## `/chat` 路由里做了哪些事情？哪些不应该放在路由里？

### 简短回答（30秒版）

`/chat` 负责编排：取 Session 历史 → 调 `run_react_agent` → 存本轮对话 → 把 trace 转成 steps 返回。不应该在路由里写 ReAct 逻辑、调 LLM、解析 tool_calls，这些属于 `agent/` 模块。

### 深入回答（2分钟版）

`api/chat.py` 是薄路由：`get_or_create(session_id)` → `get_history_messages()` → `run_react_agent(message, history)` → `add_turn()` → 组装 `ChatResponse`。错误映射：ValueError→503，其他→502。ReAct 循环、Planner、Executor、parser 全在 `agent/`；LLM 在 `core/llm.py`；Session 在 `memory/`。路由只做 HTTP 边界：校验、编排、持久化、DTO 转换，便于单测 Agent 时不启动 Web 服务。

## 503 和 502 在本项目里分别代表什么？

### 简短回答（30秒版）

503 是可预期的业务/配置错误，比如 API Key 没配、向量库空、Agent 超步数，对应 `ValueError`。502 是未捕获的异常，比如 LLM 网络故障，表示上游失败、服务暂时不可用。

### 深入回答（2分钟版）

`api/chat.py` 和 `api/rag.py` 都显式捕获 `ValueError` 转 HTTPException(503)，例如 `OPENAI_API_KEY is not configured`、向量库 count=0、`ReAct Agent exceeded maximum steps`。这类错误信息明确，前端可展示给用户。其他 Exception 记录日志后返回 502 和通用文案，避免泄露 stack trace。生产可进一步细分 429（限流）、401（鉴权），但 MVP 二分类已够用。

## Pydantic Schema 有什么好处？

### 简短回答（30秒版）

自动校验请求字段类型和长度，非法请求直接 422。还能自动生成 OpenAPI 文档，前后端对齐契约，IDE 也有类型提示。

### 深入回答（2分钟版）

`models/schemas.py` 定义 ChatRequest（message + session_id）、ChatResponse（response + session_id + steps[]）、ReActStepSchema、RAGSourceSchema 等。例如 `ChatRequest.message` 设 `min_length=1`，空消息不会进 Agent。`response_model=ChatResponse` 保证返回结构稳定。相比手写 dict 校验，Pydantic 减少 bug，Swagger UI 可直接试 API，QA 也可基于 OpenAPI 生成测试用例。

## CORS 是什么？本项目怎么配置的？

### 简短回答（30秒版）

CORS 是浏览器跨域安全策略。React 跑在 5173，API 在 8000，必须后端允许跨域。我们在 `main.py` 配了 `allow_origins=["*"]`，开发方便，生产要改成具体域名。

### 深入回答（2分钟版）

`main.py` 使用 CORSMiddleware：`allow_origins=["*"]`、`allow_methods=["*"]`、`allow_headers=["*"]`、`allow_credentials=True`。本地 Vite 开发时前端 axios 请求 `http://localhost:8000` 不会被浏览器拦截。生产环境 `*` 有风险，应改为 `["https://your-domain.com"]`；若带 Cookie 鉴权，`allow_origins` 不能为 `*` 且需精确匹配。CORS 是浏览器机制，curl/Postman 不受限。

## 为什么 `run_react_agent` 是同步函数，路由却是 async？

### 简短回答（30秒版）

FastAPI 路由声明 async，但内部调用的 `run_react_agent` 和 `chat_completion` 都是同步阻塞的。MVP 能跑，但高并发会阻塞事件循环。生产应放线程池或改真异步。

### 深入回答（2分钟版）

`api/chat.py` 的 `async def chat` 直接调同步 `run_react_agent`，后者多轮调 LLM，单次可能数十秒。在 asyncio 事件循环里跑同步 I/O 会阻塞其他请求。改进：`await asyncio.to_thread(run_react_agent, ...)` 或 `run_in_executor`；长期可把 LLM 改成 async client。面试要诚实：当前是 MVP 取舍，知道瓶颈在哪比假装 async 更重要。

## Session 为什么在 API 层读写，而不是 Agent 内部？

### 简短回答（30秒版）

Session 是跨功能的——`/chat` 和 `/rag/ask` 都要用。放 API 层统一 load/save，Agent 和 RAG 只接收 `history` 列表，模块更纯净、更好测。

### 深入回答（2分钟版）

`SessionStore` 在 `api/chat.py` 和 `api/rag.py` 中：`get_history_messages()` 注入 Agent/RAG，`add_turn()` 保存最终 user+assistant。Agent 的 `run_react_agent(user_message, history=history)` 不感知 session_id，只处理 messages。这样 Agent 可 CLI 测试、RAG 可独立调用，Session 持久化策略（内存→Redis）只改 `session_store.py` 一处，符合单一职责。

## 如何给 API 加鉴权（API Key / JWT）？

### 简短回答（30秒版）

用 FastAPI 的 `Depends` 做中间件：HTTP Bearer JWT 或 Header 里的 API Key，校验失败返回 401。Session 还要和用户 ID 绑定，防止猜 session_id 读别人数据。

### 深入回答（2分钟版）

实现 `get_current_user` 依赖：解析 Authorization Header，验 JWT 或查 API Key 表。路由 `@router.post("/chat", dependencies=[Depends(verify_api_key)])`。SessionStore 的 key 从纯 session_id 改为 `(user_id, session_id)`，get_or_create 时校验归属。生产还需 HTTPS、rate limit、审计日志。当前 MVP 无鉴权，面试可说「我知道怎么加，只是 demo 未实现」。

## 上传 PDF 时为什么要单独设 120s timeout（前端）？

### 简短回答（30秒版）

PDF 解析 + 批量 Embedding 比聊天慢很多。前端 chat 设 60s，upload 设 120s，避免 axios 默认超时把还在处理的上传误杀。

### 深入回答（2分钟版）

`frontend/src/services/api.js` 里 axios client 默认 timeout 60000（chat），uploadDocument 单独设 120000。后端 ingest 要走 load_pdf → chunk → embed_chunks → FAISS save，大 PDF 可能接近一分钟。若 timeout 太短，前端报失败但后端可能已入库一半。生产还可改异步：上传立即返回 task_id，轮询或 WebSocket 通知完成。

## OpenAPI `/docs` 对团队有什么价值？

### 简短回答（30秒版）

自动生成可交互 API 文档，前后端对齐字段含义，QA 能直接试接口，还能导出 OpenAPI spec 做 Mock 和自动化测试。

### 深入回答（2分钟版）

FastAPI 根据 Pydantic Schema 和路由装饰器生成 Swagger UI，访问 `http://localhost:8000/docs` 可试 POST /chat、/rag/ask 等。ChatResponse 的 steps 字段、RAGSourceSchema 的 score/page 都有 description。新人 onboarding 快；前端对照 schema 写 api.js 不会漏字段。CI 可用 schemathesis 等工具做契约测试。

## 如果要做接口版本 v2，你会怎么设计？

### 简短回答（30秒版）

URL 前缀 `/v2/chat` 或 Header 带 `API-Version: 2`。v1 并行保留一段时间，v2 可改 response 结构，避免 breaking change 影响老客户端。

### 深入回答（2分钟版）

FastAPI 可用多个 APIRouter：`router_v1` 挂 `/v1`，`router_v2` 挂 `/v2`，或同一 router 用 Depends 读版本号分发。例如 v2 ChatResponse 增加 `token_usage` 字段。Pydantic 模型分 ChatResponseV1/V2。文档 `/docs` 可分组展示。迁移期 v1 deprecated header 提醒，监控 v1 流量归零后下线。

## 健康检查 `/health` 够不够用？生产环境还要查什么？

### 简短回答（30秒版）

当前 `/health` 只返回 `{"status":"ok"}`，只能证明进程活着。生产还应检查 LLM 连通、FAISS 可读、磁盘空间，返回细粒度状态给 K8s 探针。

### 深入回答（2分钟版）

`main.py` 的 `/health` 是 liveness 最低配。生产建议：`/health/live` 仅进程存活；`/health/ready` 检查 OPENAI_API_KEY 已配、FaissVectorStore 能 load、uploads 目录可写。返回 `{ status, llm, vector_store, disk }` 供 Kubernetes readinessProbe。LLM 检查可用轻量 ping 或缓存结果避免每次打 API。FAISS 损坏时 ready 失败，流量不切入该实例。

# 容易踩坑的问题

1. **忘记配 `.env`**：启动成功但 `/chat` 返回 503「API Key 未配置」。
2. **async 阻塞**：高并发下同步 LLM 调用拖垮整个服务。
3. **大 PDF 上传内存**：未流式处理时可能 OOM（当前 MVP 一次性读文件）。
4. **错误 detail 泄露**：生产环境不应把完整 stack trace 返回给前端。
5. **Session 与 Agent 混淆**：API 只存最终 assistant 回复，不存 tool 中间消息。

# 进阶知识

- **依赖注入**：FastAPI `Depends(get_session_store)` 便于测试 mock
- **后台任务**：`BackgroundTasks` 异步入库大 PDF
- **WebSocket/SSE**：流式聊天与逐步 trace 推送
- **gunicorn + uvicorn workers**：多进程部署
- **API Gateway**：Kong/Nginx 统一鉴权与限流

**相关文档**：[architecture.md](./architecture.md) · [react-agent.md](./react-agent.md) · [rag.md](./rag.md)
