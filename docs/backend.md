> **面试以代码为准，文档当复习提纲。** 若与仓库实现不一致，以 `backend/` 源码为准。

# 模块作用

**Backend（FastAPI 后端）** 是整个项目的 **HTTP 网关和业务编排层**。它负责：

- 接收前端请求（聊天、流式输出、对话管理、文档上传、RAG / Memory 问答、评估查询）
- **鉴权与用户隔离**（JWT / API Key / 开发模式）
- 调用 Agent、RAG、Memory、Conversation 等内部模块
- 统一错误处理和 API 契约（Pydantic Schema）
- 提供健康检查；可选托管 Vue 构建产物（`frontend/dist`）

没有这一层，前端无法安全、结构化地访问 LLM、向量库和持久化存储。

# 核心原理

## FastAPI 是什么

FastAPI 是基于 Python 类型注解的现代 Web 框架，特点：

- 自动生成 OpenAPI 文档（访问 `/docs`）
- Pydantic 做请求/响应校验
- 原生支持 async（路由为 async，核心 Agent / LLM 调用目前仍是同步阻塞）

## 本项目的 API 设计

| 端点 | 方法 | 职责 |
|------|------|------|
| `/health` | GET | 探活 |
| `/auth/register` | POST | 用户注册，返回 JWT + API Key |
| `/auth/login` | POST | 用户登录，返回 JWT + API Key |
| `/chat` | POST | ReAct Agent 聊天（含长期记忆检索与入库） |
| `/chat/stream` | POST | 流式聊天（SSE），支持停止生成 |
| `/conversations` | GET | 列出当前用户的对话 |
| `/conversations` | POST | 新建空对话 |
| `/conversations/{id}` | GET | 对话详情（含完整 messages，供前端恢复 UI） |
| `/conversations/{id}` | PATCH | 重命名对话 |
| `/conversations/{id}` | DELETE | 删除对话 |
| `/documents` | GET | 列出当前用户已上传文档 |
| `/documents/upload` | POST | 多格式文档上传并入库 FAISS |
| `/documents/delete` | POST | 删除文档及对应向量 |
| `/rag/ask` | POST | 独立 RAG 文档问答（可选评估） |
| `/rag/ask/stream` | POST | 流式 RAG 问答（SSE） |
| `/rag/ingest` | POST | 纯文本入库 |
| `/rag/evaluations` | GET | RAG 评估历史列表 |
| `/rag/evaluations/stats` | GET | 评估统计 |
| `/rag/evaluations/{id}` | GET | 单条评估详情 |
| `/memory` | GET | Memory 面板（短期 + 长期概览） |
| `/memory/ask` | POST | 长期记忆检索问答 |
| `/memory/ask/stream` | POST | 流式记忆问答（SSE） |

受保护路由均通过 `Depends(get_current_user)` 解析身份。每个端点尽量 **薄**：参数校验 → 调用 service / store → 返回 DTO。

# 项目中的实现方式

## 应用入口

`backend/main.py` 挂载全部路由，并按配置启用 CORS 与可选前端静态托管：

```python
from api.chat import router as chat_router
from api.conversations import router as conversations_router
from api.documents import router as documents_router
from api.eval import router as eval_router
from api.memory import router as memory_router
from api.rag import router as rag_router
from auth.router import router as auth_router

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = ["*"]

app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, ...)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(documents_router)
app.include_router(rag_router)
app.include_router(eval_router)
app.include_router(memory_router)

@app.get("/health")
async def health(): ...

# settings.serve_frontend=True 且 frontend/dist 存在时托管 SPA
```

要点：

- **CORS**：来自 `settings.cors_origins`（逗号分隔，默认 `*`）；前端为 **Vue 3 + Vite**，开发时常跑在 5173，API 在 8000
- **日志格式**：`时间 | 级别 | 模块 | 消息`
- **`serve_frontend`**：单端口 Demo 部署时由 FastAPI 返回 `index.html`，并排除 API 前缀避免路由冲突

## 鉴权（已实现）

`auth/dependencies.py` 的 `get_current_user` 解析当前用户并写入 `ContextVar`：

| 优先级 | 方式 | 说明 |
|--------|------|------|
| 1 | `Authorization: Bearer <jwt>` | 注册/登录签发的 JWT |
| 2 | `X-API-Key` | 用户专属 API Key |
| 3 | `auth_disabled=True` | 读 `X-User-Id` 或默认 `dev-default`，便于本地开发 |

- 用户数据：`auth/user_store.py` → SQLite `data/users.db`
- 注册/登录：`auth/router.py` → `/auth/register`、`/auth/login`
- **多用户隔离**：SessionStore、ConversationStore、RAG/Memory 向量库均按 `user_id` 分目录或校验归属；越权返回 **403**

**生产仍须注意**：默认 `auth_disabled=True`；`auth_secret` 需改；尚无 rate limit；JWT 无 refresh token。

## 聊天 API

`backend/api/chat.py` 是 Agent 主 HTTP 入口（同步与流式共用编排逻辑）：

1. `get_current_user` — 解析 `user_id`
2. `_resolve_chat_id` — `conversation_id` 与 `session_id` 共用同一 UUID
3. `SessionStore.get_or_create(session_id, user_id)` — 加载短期历史，校验归属
4. `ConversationStore.ensure_conversation` — 确保 UI 持久化记录存在
5. `_retrieve_longterm_memory` — `LongTermStore.retrieve` → FAISS Top-K hints
6. `run_react_agent(..., memory_hints=...)` 或 `run_react_agent_stream`
7. `SessionStore.add_turn` + `_save_longterm_memory` + `_persist_conversation_turn`
8. 返回 `ChatResponse` 或 SSE 事件流

错误映射：

- `SessionForbiddenError` / `ConversationForbiddenError` → **403**
- `ValueError`（API Key 未配置、超步数等）→ **503**
- 其他异常 → **502**

### 流式 `/chat/stream`

- 协议：**SSE**（`core/sse.py`）
- 事件类型：`context`（记忆上下文）→ `token` / `step` → `done` | `cancelled` | `error`
- 客户端断开或 AbortSignal → `should_cancel` → 保留已生成 partial 并写入 Session / Conversation / LongTerm
- 前端：`frontend/src/services/api.js` 的 `chatStreamAPI` + `AbortSignal`

## Conversation API

`backend/api/conversations.py` 提供对话 CRUD，数据在 SQLite `data/conversations.db`：

- `conversation_id === session_id`（同一 UUID）
- 每条 assistant 消息的 `meta` 可存 `steps`、`retrieved_memories` 等，供 Debug Inspector 恢复
- 前端 `ChatPage.vue` 在 `onMounted` 时 `fetchConversation(sessionId)` 恢复 UI 气泡

## 文档上传 API

`backend/api/documents.py`：

- 支持 **PDF、DOCX、TXT、Markdown、图片**（`file_parser/parser.py` 统一解析，非 PDF-only）
- 按用户隔离：`rag/store/{user_id}/uploads/`
- 流程：保存文件 → `ingest_file()` → chunk → embed → FAISS + catalog
- 列表 / 删除：同步清理磁盘文件、catalog 与向量

## RAG API

`backend/api/rag.py`：

- `/rag/ask`：Session 历史 → `rag_ask()` → `add_turn`；可选 `evaluate=True` 触发 `eval/pipeline.py`
- `/rag/ask/stream`：SSE 流式，结构类似 chat
- `/rag/ingest`：JSON 纯文本入库

## Memory API

`backend/api/memory.py`：

- `GET /memory`：短期 turns + 长期 FAISS metadata 概览
- `POST /memory/ask` / `/memory/ask/stream`：独立长期记忆问答链路（`memory/chain.py`）

## Eval API

`backend/api/eval.py`：

- 只读查询 `eval/store.py` 中持久化的 RAG 评估记录
- 写入发生在 `api/rag.py` 调用 `eval/pipeline.py` 时（检索/回答/引用评分）

## 数据模型

`backend/models/schemas.py` 定义全部 API 契约，例如：

- `ChatRequest`：`message` + 可选 `session_id` / `conversation_id`
- `ChatResponse`：`response` + `session_id` + `conversation_id` + `user_id` + `steps[]` + `retrieved_memories[]`
- `AuthResponse`：`access_token` + `api_key` + `user_id`
- `ConversationDetailSchema`：含完整 `messages[]` 与 `meta`

## 依赖与启动

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

关键环境变量见 `backend/.env.example` 与 `core/config.py`（LLM、CORS、`auth_disabled`、`memory_store_path`、`conversations_db_path` 等）。

# 数据流

## POST /chat 完整路径

```
JSON Body: { message, session_id?, conversation_id? }
    ↓
get_current_user → user_id
    ↓
ChatRequest 校验
    ↓
SessionStore.get_or_create(session_id, user_id) → get_history_messages
ConversationStore.ensure_conversation
    ↓
LongTermStore.retrieve(user_id, message) → memory_hints
    ↓
agent.loop.run_react_agent(message, history, memory_hints, user_id)
    ↓
SessionStore.add_turn
LongTermStore.save_turn（extractor 筛选后写 FAISS）
ConversationStore.append_turn（含 steps / retrieved_memories meta）
    ↓
ChatResponse JSON
```

## POST /chat/stream

```
同上直到 retrieve
    ↓
run_react_agent_stream → SSE: context → token/step → done
    ↓
done / cancelled 时同样 persist Session + LongTerm + Conversation
```

## POST /documents/upload

```
multipart file（pdf/docx/txt/md/图片）
    ↓
保存 rag/store/{user_id}/uploads/
    ↓
file_parser → rag.ingest.ingest_file
    ↓ chunk → embed → FaissVectorStore.save + catalog
    ↓
DocumentUploadResponse
```

## 模块依赖关系

```
main.py
  ├── auth/router.py          → auth/user_store, auth/jwt_utils
  ├── api/chat.py             → agent.loop, memory.*, conversation.store, auth.dependencies
  ├── api/conversations.py    → conversation.store, auth.dependencies
  ├── api/documents.py        → file_parser, rag.ingest, rag.catalog, auth.dependencies
  ├── api/rag.py              → rag.chain, eval.pipeline, memory.session_store
  ├── api/memory.py           → memory.chain, memory.longterm_store
  ├── api/eval.py             → eval.store, eval.serializers
  └── core/config.py          ← 被所有模块读取

core/llm.py                   ← agent, rag, memory, eval 共用
```

# 面试题

> 每题提供两版回答：**30 秒版**适合开场快速应答，**2 分钟版**适合面试官追问「展开讲讲」。

## 为什么选 FastAPI 而不是 Flask/Django？

### 简短回答（30秒版）

FastAPI 有类型注解 + Pydantic 自动校验，还能自动生成 OpenAPI 文档。Agent 项目 API 字段多（steps、sources、retrieved_memories），用 FastAPI 少写很多校验代码。它比 Flask 更现代，比 Django 更轻，适合 AI 微服务。

### 深入回答（2分钟版）

本项目 `main.py` 挂载 auth/chat/conversations/documents/rag/memory/eval 多组路由，`models/schemas.py` 定义 ChatRequest、ChatResponse、ConversationDetailSchema 等契约，访问 `/docs` 可直接调试。相比 Flask 需手写校验和文档，FastAPI 的 Pydantic 对 `message` 做 `min_length=1` 等约束，422 自动返回。Django 过重；FastAPI + Uvicorn 启动快、async 友好（虽当前 Agent 仍同步），是 Agent/RAG 类项目的常见选型。

## `/chat` 路由里做了哪些事情？哪些不应该放在路由里？

### 简短回答（30秒版）

`/chat` 负责编排：鉴权 → 取 Session 历史 → 检索长期记忆 → 调 `run_react_agent` → 存 Session / LongTerm / Conversation → 把 trace 转成 steps 返回。ReAct 逻辑、LLM 调用、tool 解析属于 `agent/` 模块。

### 深入回答（2分钟版）

`api/chat.py` 是薄路由：`get_current_user` → `get_or_create(session_id, user_id)` → `retrieve` longterm → `run_react_agent(message, history, memory_hints)` → 三路持久化 → 组装 `ChatResponse`。流式路径复用相同编排，仅生成方式改为 SSE。ReAct 循环、Planner、Executor、parser 全在 `agent/`；LLM 在 `core/llm.py`；Session 在 `memory/session_store.py`；UI 历史在 `conversation/store.py`。路由只做 HTTP 边界：校验、编排、持久化、DTO 转换。

## 503 和 502 在本项目里分别代表什么？

### 简短回答（30秒版）

503 是可预期的业务/配置错误，比如 API Key 没配、向量库空、Agent 超步数，对应 `ValueError`。502 是未捕获的异常，比如 LLM 网络故障，表示上游失败、服务暂时不可用。

### 深入回答（2分钟版）

`api/chat.py`、`api/rag.py`、`api/memory.py` 都显式捕获 `ValueError` 转 HTTPException(503)，例如 `OPENAI_API_KEY is not configured`、向量库 count=0、`ReAct Agent exceeded maximum steps`。这类错误信息明确，前端可展示给用户。其他 Exception 记录日志后返回 502 和通用文案，避免泄露 stack trace。403 用于 Session/Conversation 越权。生产还可加 429（限流）、401（鉴权失败，已由 `get_current_user` 处理）。

## 鉴权是怎么实现的？生产还差什么？

### 简短回答（30秒版）

已实现 `get_current_user`：Bearer JWT、Header `X-API-Key`，或 `auth_disabled` 模式下 `X-User-Id` / dev-default。Session 和 Conversation 都绑定 `user_id` 并校验归属。生产要关 `auth_disabled`、换强 `auth_secret`、加 HTTPS 和 rate limit。

### 深入回答（2分钟版）

`auth/router.py` 提供注册登录，JWT 由 `auth/jwt_utils.py` 签发，用户存 SQLite `users.db`。受保护路由 `Depends(get_current_user)`，优先级 JWT > API Key > 开发模式。`SessionStore.get_or_create` 和 `ConversationStore.get_owned` 校验 `user_id`，否则 403。RAG/Memory 向量库按用户分目录。已实现的是 **身份识别 + 资源归属**；生产短板：默认 `auth_disabled=True`、无 refresh token、无请求限流、本地 SQLite/FAISS 多副本不共享。

## CORS 是什么？本项目怎么配置的？

### 简短回答（30秒版）

CORS 是浏览器跨域安全策略。Vue 前端跑在 5173，API 在 8000，必须后端允许跨域。我们在 `main.py` 读 `settings.cors_origins`（逗号分隔，默认 `*`），生产应改成具体域名。

### 深入回答（2分钟版）

`main.py` 解析 `cors_origins` 为列表，空则 fallback `["*"]`，再挂 CORSMiddleware。本地 Vite + axios/fetch 请求 `http://localhost:8000` 不会被浏览器拦截。前端为 **Vue 3**（非 React）。生产 `*` 有风险，应改为 `["https://your-domain.com"]`；若带 Cookie 鉴权，`allow_origins` 不能为 `*` 且需精确匹配。CORS 是浏览器机制，curl/Postman 不受限。

## 为什么 `run_react_agent` 是同步函数，路由却是 async？

### 简短回答（30秒版）

FastAPI 路由声明 async，但内部调用的 `run_react_agent` 和 `chat_completion` 都是同步阻塞的。能跑，但高并发会阻塞事件循环。生产应放线程池或改真异步 LLM client。

### 深入回答（2分钟版）

`api/chat.py` 的 `async def chat` 直接调同步 `run_react_agent`，后者多轮调 LLM，单次可能数十秒。在 asyncio 事件循环里跑同步 I/O 会阻塞其他请求。改进：`await asyncio.to_thread(run_react_agent, ...)` 或 `run_in_executor`；长期可把 LLM 改成 async client。流式路径同样在内层同步迭代后通过 SSE 推送。面试要诚实：知道瓶颈在哪比假装全链路 async 更重要。

## Session、Conversation、LongTerm 在 API 层怎么分工？

### 简短回答（30秒版）

Session 供 Agent 注入最近 N 轮 history；LongTerm 跨会话向量检索 hints；Conversation 存完整 UI 消息和 meta（steps）。三者都在 `/chat` 结束后写入，但用途不同。

### 深入回答（2分钟版）

`session_id === conversation_id`。SessionStore（SQLite `sessions.db`）FIFO 保留 `max_session_turns` 轮，给 `run_react_agent` 拼 messages。LongTermStore 在请求前 `retrieve`、请求后 `save_turn`（extractor 筛选写 FAISS `memory/store`）。ConversationStore（SQLite `conversations.db`）append 每轮 user/assistant 及 assistant meta（steps、retrieved_memories），供侧边栏列表和刷新后 `GET /conversations/{id}` 恢复 Vue UI。Agent 工作记忆仍在单次请求内的 `AgentMemory`，不落 Session。

## 流式聊天和停止生成怎么实现的？

### 简短回答（30秒版）

`POST /chat/stream` 返回 SSE。`run_react_agent_stream` 逐 token/step 产出事件；客户端 AbortSignal 触发 `should_cancel`；取消时保留 partial 回复并写入 Session/Conversation。

### 深入回答（2分钟版）

`core/sse.py` 的 `create_sse_response` 包装 generator，监听 HTTP 断开设置 `cancelled`。事件顺序：先发 `context`（长期记忆检索结果），再 `token`/`step`，最后 `done` 含完整 response 和 session_id。`AgentCancelledError` 路径把 partial 写入三路存储并返回 `cancelled` 事件。前端 `chatStreamAPI` 传 `AbortSignal`，用户点「停止生成」即 abort fetch。RAG 和 Memory 的 `/ask/stream` 同理。

## 文档上传为什么支持多格式？和旧版 PDF-only 有何不同？

### 简短回答（30秒版）

`file_parser` 统一解析 PDF/DOCX/TXT/MD/图片，再走同一套 chunk → embed → FAISS。图片走视觉模型 OCR/描述。按 `user_id` 隔离 uploads 和向量库。

### 深入回答（2分钟版）

`api/documents.py` 用 `get_supported_extensions()` 校验后缀，拒绝路径穿越。`ingest_file` 根据类型选 parser（`pdf_parser`、`docx_parser`、`image_parser` 等），输出统一文本块后入库。图片可能需要 `openai_vision_model`。列表和删除 API 同步清理 catalog 与 FAISS chunks。前端 upload 用 XHR multipart，timeout 180s。这比早期只接 PDF 更贴近真实知识库场景。

## RAG 评估链路怎么接入的？

### 简短回答（30秒版）

`/rag/ask` 传 `evaluate=True` 时，`eval/pipeline.py` 对检索、回答、引用做评分并写入 `evaluations.db`。`GET /rag/evaluations*` 只读查询，按 user_id 隔离。

### 深入回答（2分钟版）

`api/rag.py` 在 `rag_ask` 返回后可选调用 `evaluate_rag_result`：retrieval_judge、answer_judge、citation 模块打分，结果存 SQLite。流式路径在 `done` 事件后用 sources 重建 `RAGResult` 再评估。`api/eval.py` 提供 list/stats/detail 三个 GET，均需鉴权。这样评估与问答解耦：写发生在 RAG 链路，读走独立 API，便于 Dashboard 展示。

## OpenAPI `/docs` 对团队有什么价值？

### 简短回答（30秒版）

自动生成可交互 API 文档，前后端对齐字段含义，QA 能直接试接口，还能导出 OpenAPI spec 做 Mock 和自动化测试。

### 深入回答（2分钟版）

FastAPI 根据 Pydantic Schema 和路由装饰器生成 Swagger UI，访问 `http://localhost:8000/docs` 可试 POST /chat、/auth/login 等。ChatResponse 的 `retrieved_memories`、Conversation 的 `meta` 字段都有类型约束。Vue 前端对照 schema 写 `api.js` 不会漏字段。CI 可用 schemathesis 等工具做契约测试。

## 健康检查 `/health` 够不够用？生产环境还要查什么？

### 简短回答（30秒版）

当前 `/health` 只返回 `{"status":"ok"}`，只能证明进程活着。生产还应检查 LLM 连通、FAISS 可读、磁盘空间，返回细粒度状态给 K8s 探针。

### 深入回答（2分钟版）

`main.py` 的 `/health` 是 liveness 最低配。生产建议：`/health/live` 仅进程存活；`/health/ready` 检查 OPENAI_API_KEY 已配、各用户 FaissVectorStore 能 load、SQLite 目录可写。返回 `{ status, llm, vector_store, disk }` 供 Kubernetes readinessProbe。LLM 检查可用轻量 ping 或缓存结果避免每次打 API。多实例部署时 SQLite/FAISS 本地文件需迁移到共享存储或对象存储。

# 容易踩坑的问题

1. **忘记配 `.env`**：启动成功但 `/chat` 返回 503「API Key 未配置」。
2. **`auth_disabled=False` 但未带 Token**：除 `/auth/*` 和 `/health` 外全部 401。
3. **async 阻塞**：高并发下同步 LLM 调用拖垮整个服务。
4. **CORS 与 credentials**：生产域名未写入 `cors_origins` 会导致 Vue 前端跨域失败。
5. **大文件上传 timeout**：前端 upload 180s，超大 PDF/图片仍可能超时，需异步任务或分片。
6. **Session 与 Conversation 混淆**：Session 只保留最近 N 轮给 Agent；完整 UI 历史看 Conversation API。
7. **错误 detail 泄露**：生产环境不应把完整 stack trace 返回给前端。
8. **多副本部署**：本地 SQLite + 每实例 FAISS 文件不自动同步，需架构升级。

# 进阶知识

- **依赖注入**：FastAPI `Depends(get_current_user)` 统一鉴权，测试可 override
- **SSE vs WebSocket**：本项目聊天/RAG/Memory 流式均用 SSE + POST，实现简单、穿透代理友好
- **BackgroundTasks**：大文档入库可异步化，上传立即返回 task_id
- **gunicorn + uvicorn workers**：多进程部署时注意 SQLite 写锁与 FAISS 文件锁
- **API Gateway**：Kong/Nginx 统一鉴权、限流、TLS 终止

**相关文档**：[architecture.md](./architecture.md) · [memory.md](./memory.md) · [react-agent.md](./react-agent.md) · [rag.md](./rag.md) · [frontend.md](./frontend.md)
