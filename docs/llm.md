# 模块作用

**LLM 调用层**（`backend/core/llm.py`）是整个项目的 **「和大脑说话的统一电话线」**。

它解决的问题：

- Agent、RAG、Embedding 都需要调外部模型 API，不能各写一套 HTTP 客户端
- 需要支持 **OpenAI 兼容 API**（OpenAI 官方、智谱 GLM、DeepSeek 等）
- ReAct Agent 需要 **Tool Calling**（传 `tools` 参数），RAG 只需要纯文本生成

如果把 LLM 调用散落在各处，换模型、改 temperature、加日志都会改十几个文件。

# 核心原理

## Chat Completion 是什么

大语言模型的核心接口是 **多轮对话补全**：

```
输入: messages = [
  { role: "system", content: "你是助手..." },
  { role: "user", content: "你好" },
  ...
]
输出: assistant 的一条 message（可能有 content 和/或 tool_calls）
```

## Tool Calling 原理

当请求携带 `tools`（函数说明书 JSON Schema）时，模型可以返回：

```json
{
  "role": "assistant",
  "content": "Thought: 需要计算...",
  "tool_calls": [{
    "id": "call_xxx",
    "function": { "name": "calculator", "arguments": "{\"expression\": \"1+2\"}" }
  }]
}
```

应用执行函数后，把结果以 `role: tool` 消息塞回对话，模型继续推理。

## OpenAI 兼容模式

许多国内厂商提供与 OpenAI SDK **相同 URL 结构和字段** 的 API。只需设置：

- `api_key`
- `base_url`（如智谱 `https://open.bigmodel.cn/api/paas/v4`）

SDK 的 `client.chat.completions.create()` 无需改代码。

# 项目中的实现方式

## 配置来源

`core/config.py`：

| 字段 | 环境变量 | 说明 |
|------|----------|------|
| `openai_api_key` | `OPENAI_API_KEY` | 必填 |
| `openai_model` | `OPENAI_MODEL` | 默认 `gpt-4o-mini`，.env.example 用 `glm-4.7` |
| `openai_base_url` | `OPENAI_BASE_URL` | 可选，智谱等兼容地址 |
| `embedding_model` | `EMBEDDING_MODEL` | 在 `rag/embedder.py` 使用 |

## 客户端创建

```21:32:backend/core/llm.py
def _build_client() -> OpenAI:
    settings = get_settings()
    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**client_kwargs)
```

每次 `chat_completion` 调用都会 `_build_client()`。MVP 简单；生产可单例 + 连接池。

## 统一入口 chat_completion

```35:96:backend/core/llm.py
def chat_completion(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
) -> ChatCompletionMessage:
    // ...
    request_kwargs = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.7,
    }
    if tools:
        request_kwargs["tools"] = tools
    response = client.chat.completions.create(**request_kwargs)
    return response.choices[0].message
```

**调用方：**

| 模块 | 文件 | tools |
|------|------|-------|
| ReAct Planner | `agent/planner.py:40` | `get_tool_schemas()` |
| RAG 问答 | `rag/chain.py:135` | `None` |

## Embedding 不在 llm.py

向量嵌入在 `rag/embedder.py` 单独调用 `client.embeddings.create()`，因为 API 路径和参数与 chat 不同。架构上仍共用 `_build_client()` 思路（embedder 内自建 client）。

## 日志

每次请求记录：model、messages 条数、tools 数量、finish_reason、tool_calls 详情。便于调试 Agent 是否「乱调工具」。

# 数据流

## Agent 路径

```
AgentMemory.messages
    ↓
planner.plan() → chat_completion(messages, tools=schemas)
    ↓
OpenAI SDK → 智谱/OpenAI API
    ↓
ChatCompletionMessage (content + tool_calls?)
    ↓
parser.parse_llm_response() → PlannerResult
```

## RAG 路径

```
build_rag_messages() → messages
    ↓
chat_completion(messages, tools=None)
    ↓
response.content → 最终 answer
```

## 失败路径

```
openai_api_key 为空 → ValueError("OPENAI_API_KEY is not configured")
    ↓
api/chat.py 捕获 → HTTP 503
```

# 面试题

> 每题提供两版回答：**30 秒版**适合开场快速应答，**2 分钟版**适合面试官追问「展开讲讲」。

## 你们的 LLM 层是怎么抽象的？

### 简短回答（30秒版）

全项目只有一个入口 `chat_completion(messages, tools=None)`，配置集中在 `Settings`，用 OpenAI SDK 兼容模式。Agent 带 tools，RAG 不带，换模型主要改 `.env` 就行。

### 深入回答（2分钟版）

`core/llm.py` 封装 `_build_client()` 和 `chat_completion()`：读 `openai_api_key`、`openai_model`、`openai_base_url`，构造 OpenAI 客户端发 chat completion。ReAct 的 `planner.py` 传入 `get_tool_schemas()`；RAG 的 `chain.py` 传 `tools=None`。返回 `ChatCompletionMessage` 而非字符串，保留 content 和 tool_calls。Embedding 在 `rag/embedder.py` 单独调 embeddings API，职责分离。

## temperature 设 0.7 有什么影响？Agent 和 RAG 要不要不同？

### 简短回答（30秒版）

temperature 越高越发散，越低越稳定。0.7 是常见默认，Agent 推理需要一点灵活性。RAG  factual 问答 ideally 降到 0.2～0.3 减少编造，我们目前共用 0.7 是可改进点。

### 深入回答（2分钟版）

`llm.py` 里写死 `temperature=0.7`。Agent 多步推理时适度随机有助于探索不同 tool 策略；RAG 在 `prompt_builder.py` 已约束「仅据资料」，但低 temperature 能进一步减少幻觉。生产可按场景拆分：`chat_completion(..., temperature=0.7)` 与 RAG 专用 `temperature=0.2`，或暴露到 config。面试可说：知道 trade-off，MVP 先统一便于调试。

## 什么是 OpenAI 兼容 API？怎么切换智谱？

### 简短回答（30秒版）

很多厂商提供和 OpenAI 相同 URL 结构和 JSON 字段的 API。设 `base_url` 和 `api_key` 即可，不用改业务代码。我们 `.env.example` 指向智谱 GLM。

### 深入回答（2分钟版）

OpenAI Python SDK 支持自定义 `base_url`。本项目 `config.py` 的 `openai_base_url` 默认示例为 `https://open.bigmodel.cn/api/paas/v4`，模型 `glm-4.7`，Embedding `embedding-3`。切换时改 `.env` 四项即可，Agent/RAG/ingest 无感。注意：Embedding 维度变化需重建向量索引；智谱 tool calling 若格式有差异，改动收敛在 `llm.py` 和 `parser.py`。

## Tool Calling 和传统 Prompt 里写 JSON 有什么区别？

### 简短回答（30秒版）

Tool Calling 是模型原生结构化输出，带 schema 和 tool_call_id，可靠得多。让模型在文本里「打印 JSON」容易格式错、难和 Observation 对齐。

### 深入回答（2分钟版）

Function Calling 时 LLM 返回标准 `tool_calls` 数组，含 name、arguments JSON、id；应用执行后以 `role=tool` + `tool_call_id` 回传。比 Prompt 里写「请输出 {"tool":...}」更稳。我们 `parser.py` 优先解析 tool_calls，仍保留 `Action: calculator(...)` 文本 fallback 兼容弱模型。Tool Calling 还支持 tools 参数里的 description 指导何时调用。

## `chat_completion` 返回什么类型？为什么不让它直接返回字符串？

### 简短回答（30秒版）

返回 `ChatCompletionMessage`，因为同时要读 `content`（Thought/Final Answer）和 `tool_calls`（Action）。只返回字符串会丢结构，parser 无法工作。

### 深入回答（2分钟版）

OpenAI SDK 的 Message 对象含 `content`、`tool_calls`、`role` 等。`parser.py` 的 `parse_llm_response()` 需要：从 content 抽 Thought/Final Answer，从 tool_calls 建 Action 对象（含 tool_call_id）。若 llm 层只返回 str，Assistant 的 tool 信息就丢了。这也是分层设计：llm 层原样返回 API 结果，agent 层负责语义解析。

## 一次 Agent 请求会调用 LLM 几次？

### 简短回答（30秒版）

ReAct 每轮至少 1 次。简单问题可能 1 次就 Final Answer；复杂问题多轮调工具。最多 `max_agent_steps=10` 次。RAG 的 `/rag/ask` 固定 1 次 LLM 调用。

### 深入回答（2分钟版）

`agent/loop.py` 每步 `plan()` → `chat_completion()`。例：「123*456」可能 2 次（calculator + Final Answer）；文档问题可能 2 次（search_docs + 总结）。超 10 步无 Final Answer 抛错。成本与延迟随步数线性增。优化：缓存 tool 结果、合并步骤、小模型规划大模型生成。RAG chain 检索用 Embedding API，生成答案只 1 次 chat completion。

## 如何控制 LLM 成本？

### 简短回答（30秒版）

限制 max_agent_steps、精简 system prompt、缓存 Embedding、用小模型做规划、记录 token 用量。避免 LLM 无限调工具是控成本第一关。

### 深入回答（2分钟版）

本项目已有 `max_agent_steps=10`、`max_session_turns=10` 限制上下文长度。可扩展：在 `llm.py` 读 `response.usage` 打日志；Embedding 对相同 chunk 不重复算；RAG Top-K 不宜过大；Planner 换便宜模型。Agent 路径比 RAG 贵在 multi-turn。生产加 per-user rate limit 和预算告警。

## 模型不支持 tool_calls 怎么办？

### 简短回答（30秒版）

用 `parser.py` 解析文本里的 `Action: calculator(...)`；或换支持 Function Calling 的模型；或降级为纯 CoT 无工具。

### 深入回答（2分钟版）

`parser.py` 双路径：优先 `message.tool_calls`，fallback 正则匹配 `Action:` 行。fallback 时无 tool_call_id，loop 用 user 消息模拟 Observation。生产应选 glm-4/gpt-4o 等支持 tools 的模型。若完全无 tools，Agent 退化为纯文本 ReAct，search_docs 和 calculator 不可用，RAG 仍可通过 `/rag/ask` 独立使用。

## system prompt 放在 messages 哪里？谁负责拼？

### 简短回答（30秒版）

LLM 层不负责拼 prompt，只负责发送 messages。Agent 在 `loop.py` 放 `REACT_SYSTEM_PROMPT`；RAG 在 `prompt_builder.py` 放 `RAG_SYSTEM_PROMPT`。

### 深入回答（2分钟版）

`run_react_agent` 构造 `initial_messages = [system, *history, user]`，system 来自 `prompts.py`。RAG 的 `build_rag_messages()` 拼 system + history + user（含资料块）。`chat_completion` 原样转发 messages 列表。这样换 Agent 行为改 prompts.py，换 RAG 约束改 prompt_builder，llm 层稳定。

## Embedding 和 Chat 为什么分开两个 API？

### 简短回答（30秒版）

端点不同：chat 是 `/chat/completions`，embedding 是 `/embeddings`。输入输出结构也不一样，分开更清晰。

### 深入回答（2分钟版）

Chat 输入 messages 数组，输出 assistant message。Embedding 输入 text/string[]，输出 float 向量。本项目 `core/llm.py` 只管 chat；`rag/embedder.py` 的 `embed_text/embed_chunks` 调 embeddings API。入库和检索都依赖 embedder，与 Agent 的 chat 路径解耦。换 Embedding 模型只动 embedder 和 Chroma 重建，不动 ReAct loop。

## 如何做 LLM 调用的重试和超时？

### 简短回答（30秒版）

OpenAI SDK 支持 `timeout` 和 `max_retries`。对 429 做指数退避。Agent 层可对单步 plan 的 transient error 重试，避免整轮失败。

### 深入回答（2分钟版）

可在 `_build_client()` 或 `create()` 传 `timeout=60.0, max_retries=3`。429/503 可 sleep 后重试。注意 ReAct 重试语义：重试单步 plan 而非整 Agent，避免重复执行副作用工具（如写库）。Idempotent 工具（calculator、search_docs）较安全。记录每次调用 latency 和 error rate 调参数。

## 流式输出在 SDK 层怎么改？

### 简短回答（30秒版）

`client.chat.completions.create(..., stream=True)` 返回迭代器，逐 chunk 读 delta.content。FastAPI 用 StreamingResponse 推 SSE 给前端。

### 深入回答（2分钟版）

新增 `chat_completion_stream(messages)` generator，yield 每个 token chunk。API 层从 JSON 改 SSE：`StreamingResponse(event_stream(), media_type="text/event-stream")`。Agent 复杂：可只流最后一轮 Final Answer，或每步 Observation 后推 trace 事件。RAG `/rag/ask` 流式改动最小。Session `add_turn` 需等流结束再写，避免半截入库。

# 容易踩坑的问题

1. **API Key 未配置**：空字符串会在第一次调用时才报错，不是启动时。
2. **base_url 末尾斜杠**：部分厂商对 `/v4` vs `/v4/` 敏感，404 难排查。
3. **模型名写错**：智谱用 `glm-4.7` 不是 `gpt-4`。
4. **messages 格式错误**：tool 消息必须带 `tool_call_id`，否则 API 400。
5. **每次 new Client**：高 QPS 下可优化为单例。

# 进阶知识

- **结构化输出 JSON mode / response_format**
- **多模型路由**：小模型分类意图，大模型生成
- **Prompt Caching**（Anthropic/OpenAI 缓存 system prompt）
- **本地模型**：vLLM + OpenAI 兼容 server
- **Token 计费中间件**：统一在 llm.py 记录 usage

**相关文档**：[tool-calling.md](./tool-calling.md) · [react-agent.md](./react-agent.md) · [rag.md](./rag.md) · [stop-generation.md](./stop-generation.md)
