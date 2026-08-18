# AI Agent 实习面试指南

> 按真实面试流程组织，结合本仓库代码。建议先通读一遍，再对照各模块 [docs 索引](./README.md) 深挖。

---

## 使用说明

| 阶段 | 你要做什么 |
|------|-----------|
| **开场** | 用 1 分钟项目介绍建立印象 |
| **架构** | 画数据流、讲模块分工 |
| **深挖** | 按 Tool Calling → ReAct → RAG → Chroma → Memory 顺序答 |
| **追问** | 用「容易追问」预判，用「继续展开」展示深度 |
| **收尾** | 主动说 MVP 短板 + 改进方向，显得有工程思维 |

**答题节奏：** 先 30 秒结论 → 等追问 → 再 2 分钟结合项目展开。

---

# 1. 项目介绍

## 面试官会问什么

- 「介绍一下你的 Agent 项目。」
- 「这个项目解决了什么问题？」
- 「你负责哪一块？技术栈是什么？」
- 「和 ChatGPT 直接聊天有什么区别？」
- 「项目跑通了吗？能 demo 吗？」

## 如何回答

### 30 秒版（开场必背）

> 这是一个 **React + FastAPI** 的全栈 AI 助手。用户能聊天、上传 PDF 建知识库。后端核心是 **ReAct Agent**：大模型先思考，再调工具——**计算器**做精确运算，**search_docs** 检索文档——看到结果后继续推理，直到给出最终答案。文档侧走 **RAG**：PDF 切块、Embedding、存 **Chroma**，检索后拼进 Prompt 减少幻觉。多轮对话靠 **Session 记忆** 保留最近 10 轮。

### 2 分钟版（项目亮点）

**背景与目标：** 纯 LLM 会算错数、不知道私有 PDF 内容、容易编造。项目把 **Agent 推理** 和 **RAG 检索** 结合起来，让助手能「动手查资料、算数字」，而不只是空谈。

**技术栈：**
- 前端：React 19 + Vite + Axios
- 后端：FastAPI + Pydantic
- 模型：OpenAI 兼容 API（默认智谱 GLM，`core/llm.py`）
- 向量：Chroma + Embedding API
- Agent：自研 ReAct 循环（`backend/agent/`）

**两条主链路：**
1. **Agent 聊天**：`POST /chat` → Session 历史 → ReAct → 返回 `response` + `steps` trace
2. **RAG**：上传 PDF → ingest → Chroma；问答走 `/rag/ask` 或 Agent 的 `search_docs` 工具

**你的贡献（按实际改）：** 例如「我实现了 ReAct 循环和工具注册表」「我打通了 PDF 入库到 Agent 检索的全链路」。

## 容易追问什么

| 追问 | 方向 |
|------|------|
| 为什么不用 LangChain / LangGraph？ | 说清自研是为了理解原理、控制 trace、面试能讲清每一层 |
| 模型用的哪个？ | 智谱 GLM，`OPENAI_BASE_URL` 兼容模式 |
| 项目最难的点？ | ReAct 多轮消息格式、RAG 与 Agent 双入口、Memory 两套模型 |
| 有什么没做完？ | 前端 steps 可视化、Session Redis 持久化、长期记忆 |

## 如何继续展开

- **对比竞品：** 「ChatGPT 插件是工具调用；我这版是自研 ReAct + 可返回每步 trace，便于调试。」
- **举例子：** 「用户问『手册里报销流程？』→ Agent 调 search_docs → 拿到 PDF 片段 → 组织 Final Answer。」
- **主动收尾：** 「当前是 MVP，我知道 Session 内存存储、向量库规模、鉴权是生产短板，后续可以……」
- **深入阅读：** [architecture.md](./architecture.md)

---

# 2. 项目架构

## 面试官会问什么

- 「画一下整体架构 / 数据流。」
- 「用户发一条消息后发生了什么？」
- 「模块之间怎么解耦？」
- 「为什么 `/chat` 和 `/rag/ask` 两个入口？」
- 「如果换 LLM 提供商要改哪里？」

## 如何回答

### 30 秒版

> 前端 React 调 FastAPI。API 层很薄：`/chat` 编排 Session + ReAct，`/documents/upload` 入库，`/rag/ask` 固定 RAG 问答。ReAct 调 `core/llm.py` 和 `tools/registry.py`；RAG 调 embedder + `RagVectorStore`。LLM 层与 Agent 层分离，工具可插拔，RAG 与 Agent 共用同一向量库。

### 2 分钟版（建议边画边说）

```
用户 → React (ChatBox / UploadPanel)
         ↓ HTTP
       FastAPI (api/chat, api/documents, api/rag)
         ↓
    SessionStore ←→ run_react_agent / rag_ask
         ↓                    ↓
    agent/loop          rag/chain + retriever
         ↓                    ↓
    core/llm.py  ←——→  RagVectorStore
         ↓
    tools/registry (calculator, search_docs)
```

**`/chat` 路径：** `get_history_messages` → `run_react_agent` → `add_turn` → 返回 `ChatResponse(steps=...)`

**上传路径：** PDF → `ingest_pdf` → chunk → embed → Chroma save

**设计原则：**
1. LLM 只负责发请求，不负责 Agent 逻辑
2. 新工具只改 registry，不改 loop
3. Session 在 API 层读写，Agent 只收 `history` 列表

## 容易追问什么

| 追问 | 要点 |
|------|------|
| Session Memory 和 Agent Memory 区别？ | Session 跨请求、只存干净 QA；AgentMemory 单次请求、含 tool 消息和 trace |
| 503 和 502？ | 503=ValueError 可预期错误；502=未捕获异常 |
| 怎么加流式输出？ | 五层 SSE：`llm → planner/chain → loop → sse.py → fetch`；见 [streaming.md](./streaming.md) |
| 停止生成怎么实现？ | AbortController + `is_disconnected()` + stream break；见 [stop-generation.md](./stop-generation.md) |
| 生产短板？ | 单机 SQLite、CORS/`auth` 默认偏松、Chroma 本机文件难水平扩展 |

## 如何继续展开

- **双入口 RAG：** Agent 灵活多步；`/rag/ask` 固定 Prompt、返回 sources，适合合规文档 QA
- **换模型：** 只改 `.env` 和 `config.py`；Embedding 维度变了要重建向量索引
- **扩展性：** 「加 weather 工具 = schema + handler + registry 一行」
- **深入阅读：** [architecture.md](./architecture.md) · [backend.md](./backend.md)

---

# 3. Tool Calling

## 面试官会问什么

- 「什么是 Function Calling / Tool Calling？」
- 「你们有哪些工具？怎么注册的？」
- 「LLM 怎么知道何时调工具？」
- 「tool_call_id 干什么用？」
- 「怎么新增一个工具？」
- 「search_docs 和 rag_ask 有什么区别？」

## 如何回答

### 30 秒版

> Tool Calling 让 LLM 输出结构化「函数调用请求」，应用在本地执行后再把结果喂回去。我们用 `tools/registry.py` 注册工具：Planner 把 schema 发给 LLM，Executor 通过 `execute_tool` 执行。现有 **calculator**（安全算术）和 **search_docs**（Chroma 检索）。新增工具只需注册，不用改 Agent 循环。

### 2 分钟版

**流程：**
```
Planner: chat_completion(messages, tools=get_tool_schemas())
    → LLM 返回 tool_calls
    → parser 解析为 Action(name, arguments, tool_call_id)
    → executor → registry.execute_tool()
    → Observation 以 role=tool 写回 AgentMemory
    → 下一轮 Planner
```

**calculator：** AST 白名单解析，禁止 `eval`，防注入。

**search_docs：** 包装 RAG 检索，内部 `search_similar()` → 格式化片段返回 Agent。Agent 自己组织答案；`/rag/ask` 则是固定 RAG Prompt 一次生成。

**registry 模式：** 开闭原则，面试可举例「加 weather 工具三步：写 handler、写 schema、注册」。

## 容易追问什么

| 追问 | 要点 |
|------|------|
| 为什么 calculator 不用 eval？ | eval 可 RCE；AST 白名单只允许 `+ - * /` |
| 一次能调多个工具吗？ | OpenAI 支持；我们 Prompt 要求每次一个，简化循环 |
| Schema 的 description 重要吗？ | 非常重要，LLM 靠它决定何时调 search_docs |
| 工具返回 Error 呢？ | 作为 Observation 字符串回 LLM，不抛 500 |
| 怎么防危险工具？ | 白名单 registry、参数校验、绝不 LLM 输出当 shell |

## 如何继续展开

- **对比 Prompt JSON：** Tool Calling 有 schema、tool_call_id，比让模型打印 JSON 可靠
- **MCP：** 可提 Model Context Protocol 是工具生态标准化，未来可 adapter 进 registry
- **并行工具：** 无依赖的 search + calc 可并行，降低延迟
- **深入阅读：** [tool-calling.md](./tool-calling.md) · [llm.md](./llm.md)

---

# 4. ReAct

## 面试官会问什么

- 「什么是 ReAct？和 CoT 有什么区别？」
- 「描述一下 Agent 循环。」
- 「Thought / Action / Observation / Final Answer 是什么？」
- 「max_agent_steps 为什么需要？」
- 「Planner 和 Executor 为什么分开？」
- 「怎么评估 Agent 效果？」

## 如何回答

### 30 秒版

> ReAct = Reasoning + Acting。每轮：LLM **Thought** 思考 → **Action** 调工具 → **Observation** 看结果 → 循环直到 **Final Answer**。CoT 只想不动；ReAct 能查文档、算数。循环在 `agent/loop.py`，最多 10 步，trace 通过 API `steps` 返回。

### 2 分钟版

**伪代码（对应 `loop.py`）：**
```python
for step in 1..max_agent_steps:
    result = plan(memory)          # planner.py → llm + parser
    append assistant message
    if result.is_final:
        return ReActResult(response, trace)
    observation = execute(action)  # executor → registry
    append_tool_result(tool_call_id, observation)
    add_trace_step(...)
```

**模块分工：**
| 文件 | 职责 |
|------|------|
| `loop.py` | 主循环 |
| `planner.py` | 调 LLM + 解析 |
| `executor.py` | 执行工具 |
| `parser.py` | tool_calls 或文本 Action fallback |
| `memory.py` | messages + trace |
| `prompts.py` | REACT_SYSTEM_PROMPT |

**例子：**「12345×67890」→ Step1 calculator → Step2 Final Answer。

## 容易追问什么

| 追问 | 要点 |
|------|------|
| Thought 必须输出吗？ | 理想有；没有 parser 用默认文案，不影响执行 |
| 既不 tool 也不 final？ | 抛 ValueError → API 503 |
| trace 和 messages 区别？ | messages 喂 LLM；trace 给日志/前端展示 |
| ReAct 缺点？ | 多轮贵且慢、错误传播、占 context |
| 文本 Action fallback？ | 弱模型不支持 tool_calls 时 parser 正则解析 |

## 如何继续展开

- **和 Plan-and-Execute 比：** ReAct 每步可修正；Plan 适合长任务先规划
- **评估：** benchmark 任务集、tool 选择准确率、平均步数、人工抽检 trace
- **优化：** tool 结果缓存、ReWOO 减调用次数、LangGraph 状态机
- **前端：** 后端 steps 已 ready，aside 可渲染 Execution Viewer
- **深入阅读：** [react-agent.md](./react-agent.md)

---

# 5. RAG

## 面试官会问什么

- 「什么是 RAG？为什么需要？」
- 「你们的 RAG pipeline 几步？」
- 「chunk_size / overlap 怎么选？」
- 「怎么减少幻觉？」
- 「RAG 和 Fine-tuning 怎么选？」
- 「检索不到怎么办？」

## 如何回答

### 30 秒版

> RAG 是检索增强生成：先从知识库找相关片段，再让 LLM 带着片段回答，解决模型不知道私有数据、爱编造的问题。离线：PDF → 切块 → Embedding → Chroma；在线：问题 embed → Top-K 检索 → 拼 Prompt → LLM 生成。

### 2 分钟版

**入库（`ingest.py`）：**
```
PDF → loader.load_pdf → chunker.chunk_document
    → embedder.embed_chunks → RagVectorStore.add_embeddings → save
```

**问答（`chain.py` 六步）：**
1. 接收问题
2. embed 问题
3. Chroma search Top-K
4. 得到 SearchResult
5. `build_rag_messages` 拼 Prompt（system 要求「仅据资料，禁止编造」）
6. `chat_completion(tools=None)` 生成答案

**双路径：**
- `/rag/ask`：固定 RAG，返回 `sources` + `answer`
- Agent `search_docs`：只检索，Agent 多轮组织答案

**参数：** 默认 chunk 500 字、overlap 50；Top-K=3（`retrieval_top_k`）

## 容易追问什么

| 追问 | 要点 |
|------|------|
| 字符切分 vs token？ | MVP 用字符简单；生产用 tiktoken |
| Top-K 太大太小？ | 太小漏信息；太大噪音多、费 token |
| 多轮 RAG？ | 每轮应重新检索；history 注入注意 token |
| 怎么评估 RAG？ | Recall@K、faithfulness、RAGAS、人工标注 |
| config 和 ingest 不一致？ | `rag_chunk_size` 在 config 有但 ingest 未 wired，是已知坑 |

## 如何继续展开

- **减幻觉：** 强 system prompt、低 temperature、返回 sources、空检索拒绝回答
- **进阶：** Hybrid Search（BM25+向量）、Reranker、HyDE  query 改写
- **和 Fine-tune：** RAG 知识可热更新；Fine-tune 改行为/风格；常组合使用
- **深入阅读：** [rag.md](./rag.md)

---

# 6. Chroma

## 面试官会问什么

- 「Chroma 是什么？为什么用？」
- 「向量存哪？原文存哪？」
- 「为什么要 L2 归一化？score 怎么算？」
- 「和 Milvus / Qdrant 怎么选？」
- 「换 Embedding 模型要注意什么？」
- 「`faiss_id` 字段还在，是不是还用 FAISS？」

## 如何回答

### 30 秒版

> 我们用 **LangChain Chroma** 做嵌入式向量库：向量和 metadata 同库持久化到 `chroma.sqlite3`。入库/查询前做 **L2 归一化**，空间用 cosine，对外 `score = 1 - distance`。RAG 与长期记忆按用户分目录隔离；API 里的 `faiss_id` 只是历史字段名，实际是内部序号。

### 2 分钟版

**磁盘结构（每用户一份）：**
```
rag/store/{user_id}/
├── chroma.sqlite3
└── <uuid>/          ← 分段向量数据
uploads/             ← 原文件
```

**写入：** embed → L2 归一化 → `collection.add`（增量）→ 自动落盘

**检索：** query 归一化 → cosine Top-K → 直接带回 documents / metadatas → `SearchResult`

**选型：** 本机嵌入式、支持持久化与增量，适合 Demo/中小规模；百万级、多副本再迁 Milvus/Qdrant

**换模型：** 维度可能变，必须清空对应用户目录并重建，不能混用旧向量

## 容易追问什么

| 追问 | 要点 |
|------|------|
| 为什么归一化？ | 只比方向（语义），避免模长干扰；与 cosine 一致 |
| 增量追加 PDF？ | `add_embeddings` 追加；按 `doc_id`/`source` 可 delete |
| 为何保留 `faiss_id`？ | 兼容前端 / Eval JSON，值为 `seq_id`，不代表仍用 FAISS |
| 多用户怎么隔离？ | `rag_store_path/{user_id}` 与 memory 目录物理分离 |
| score 当置信度？ | 别当概率，看相对排序 + 人工定标 |

## 如何继续展开

- **生产迁移：** Milvus/Qdrant 支持分布式、更强 filter、高可用
- **删除文档：** Chroma 按 id 删除，比旧 Flat 索引重建更直接
- **优化：** 文档路由（catalog）缩小检索范围；必要时加 Reranker
- **深入阅读：** [chroma.md](./chroma.md) · [chroma-migration.md](./chroma-migration.md)

---

# 7. Memory

## 面试官会问什么

- 「LLM 有记忆吗？你们怎么实现多轮对话？」
- 「Session Memory 和 Agent Memory 区别？」
- 「为什么不存 ReAct 中间步骤？」
- 「服务重启后对话还在吗？」
- 「长期记忆怎么做？」
- 「context 太长怎么办？」

## 如何回答

### 30 秒版

> LLM API 无状态，每次都要传完整 messages。我们用 **SessionStore** 存跨请求的 user/assistant 对话，默认 10 轮 FIFO。**AgentMemory** 只在单次 `/chat` 内存在，存含 tool 的 messages 和 ReAct trace。Session 给续聊；AgentMemory 给当前推理；trace 经 API steps 返回，不进 Session。

### 2 分钟版

**Session（`memory/session_store.py`）：**
- `get_or_create(session_id)` — 无 ID 则 UUID
- `get_history_messages()` — 转 OpenAI messages
- `add_turn(user, assistant)` — 只存最终回复
- MVP：进程内 dict，**重启丢失**；前端 localStorage 存 session_id

**Agent Memory（`agent/memory.py`）：**
- `messages`：system + history + user + assistant + tool
- `trace`：ReActStep 列表
- 请求结束销毁

**Long-term（占位）：** `longterm_store.py` 接口已有，未实现

**前端：** 刷新页面 messages UI 清空，session_id 可能还在 → 前后端不同步

## 容易追问什么

| 追问 | 要点 |
|------|------|
| FIFO 丢什么？ | 最早几轮；可改摘要压缩 |
| 防串 session？ | 生产绑 user_id + 鉴权 |
| trace 要持久化吗？ | 审计有价值，存 DB；不进 Session history |
| `/chat` 和 `/rag/ask` 共用 Session？ | 好处连续上下文；风险行为不一致 |
| 超 context？ | 减 max_turns、摘要、检索式 memory、长窗口模型 |

## 如何继续展开

- **生产：** Redis Session + TTL
- **长期记忆：** 对话摘要 embed 存向量库，retrieve 注入 Prompt
- **改进 FIFO：** ConversationSummaryBuffer、MemGPT 分页换入
- **深入阅读：** [memory.md](./memory.md) · [frontend.md](./frontend.md)

---

# 附录

## A. 1 分钟项目介绍（背诵版）

> 我做了一个 AI Agent 助手，React 前端 + FastAPI 后端。核心是 ReAct Agent：模型思考后调 calculator 算数、调 search_docs 查上传的 PDF，看到结果再回答。文档走 RAG  pipeline，PDF 切块 Embedding 存 Chroma。多轮对话用 Session 记最近 10 轮。后端已经返回 ReAct 的 steps trace，前端侧边栏预留了可视化。模型用智谱 GLM，OpenAI 兼容 API。

## B. 高频追问速查

| 话题 | 一句话 |
|------|--------|
| ReAct vs CoT | CoT 只想；ReAct 想+做+观察 |
| RAG vs Fine-tune | RAG 热更新知识；Fine-tune 改行为 |
| search_docs vs rag_ask | 前者只检索给 Agent；后者固定 RAG 一次生成 |
| 两种 Memory | Session 跨请求；AgentMemory 单次请求 |
| 生产短板 | Session 内存、无鉴权、向量库规模、steps 未展示 |
| 加工具 | schema + handler + registry |
| 换模型 | 改 .env；Embedding 变则重建向量索引 |

## C. 演示建议（若要求 live demo）

1. 启动后端 `uvicorn main:app --reload`，前端 `npm run dev`
2. 上传 PDF → 看 chunks_added
3. 问文档问题 → 观察日志里 search_docs
4. 问算术 → 观察 calculator
5. 打开 `/docs` 展示 API 结构
6. 主动提：「steps 在 response 里，前端 aside 待渲染」

## D. 相关文档

| 模块 | 详细文档 |
|------|----------|
| 架构 | [architecture.md](./architecture.md) |
| 后端 | [backend.md](./backend.md) |
| LLM | [llm.md](./llm.md) |
| Tool Calling | [tool-calling.md](./tool-calling.md) |
| ReAct | [react-agent.md](./react-agent.md) |
| RAG | [rag.md](./rag.md) |
| Chroma | [chroma.md](./chroma.md) |
| Memory | [memory.md](./memory.md) |
| 前端 | [frontend.md](./frontend.md) |

---

> **练习建议：** 按 1→7 顺序模拟面试，每模块先自答 30 秒版，再让朋友追问「容易追问」里的问题，用「继续展开」加深。祝面试顺利。
