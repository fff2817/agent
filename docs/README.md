# AI Agent 项目学习文档

面向 **AI Agent 实习面试** 的项目级学习手册。每份文档都结合本仓库真实代码，而不是只讲抽象理论。

## 文档索引

| 文档 | 对应代码目录 | 一句话说明 |
|------|-------------|-----------|
| [architecture.md](./architecture.md) | 全项目 | 整体架构、模块关系、主链路（以代码为准） |
| [backend.md](./backend.md) | `backend/` | FastAPI 路由、API 契约、启动方式 |
| [llm.md](./llm.md) | `backend/core/llm.py` | LLM 统一调用层 |
| [tool-calling.md](./tool-calling.md) | `backend/tools/` | 工具注册与 Function Calling |
| [react-agent.md](./react-agent.md) | `backend/agent/` | ReAct 循环：Thought → Action → Observation |
| [rag.md](./rag.md) | `backend/rag/` | 检索增强生成完整流水线 |
| [faiss.md](./faiss.md) | `backend/rag/vectorstore.py` | FAISS 向量索引与相似度搜索 |
| [memory.md](./memory.md) | `backend/memory/` + `backend/agent/memory.py` | Session / Agent / 长期记忆 |
| [frontend.md](./frontend.md) | `frontend/` | Vue 3 聊天 UI、会话侧栏与执行可视化 |
| [streaming.md](./streaming.md) | 流式全链路 | SSE 五层架构：LLM → Agent → API → 前端 |
| [stop-generation.md](./stop-generation.md) | 流式 + 前后端 | 「停止生成」全链路取消（AbortController） |
| **[interview-guide.md](./interview-guide.md)** | 全项目 | **按面试流程整理的问答指南（推荐面试前通读）** |

## 面试题怎么练

每份文档的 **# 面试题** 章节采用统一答法：

| 小节 | 用途 |
|------|------|
| **简短回答（30秒版）** | 面试官刚问完，先口头答 2～4 句，抓核心 |
| **深入回答（2分钟版）** | 对方说「展开讲讲 / 结合项目说说」时用，带代码路径和取舍 |

建议练习方式：遮住「深入回答」，只看标题自问自答 30 秒版；再对照 2 分钟版补缺口。

## 推荐阅读顺序

```
architecture → backend → llm → tool-calling → react-agent
                                    ↓
              rag → faiss → memory → frontend → streaming → stop-generation
```

1. 先读 **architecture**，建立全局地图
2. 再读 **backend + llm**，理解 HTTP 如何触达模型
3. 然后 **tool-calling + react-agent**，这是 Agent 核心
4. 接着 **rag + faiss**，理解知识库如何增强回答
5. 最后 **memory + frontend**，理解多轮对话与 UI
6. 读 **streaming**，理解 SSE 五层架构与打字机效果
7. 需要讲清 **stop-generation**，理解 AbortController 取消链路

## 本地运行（配合文档动手）

```bash
# 后端
cd backend
cp .env.example .env   # 填入 OPENAI_API_KEY 等
pip install -r requirements.txt
uvicorn main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

## 新增模块时如何补充文档

当项目新增核心模块（例如：长期记忆、MCP 工具、流式输出）时，请按以下步骤维护 docs：

### 1. 新建模块文档

复制 [`_template.md`](./_template.md)，命名为 `<模块名>.md`，填写全部章节。

### 2. 更新索引

在本 `README.md` 的「文档索引」表中增加一行。

### 3. 更新 architecture.md

在 architecture 中补充新模块在架构图中的位置和数据流。

### 4. 交叉引用

在相关模块文档中增加「参见 xxx.md」链接，避免重复大段内容。

### 5. 面试题维护

每个模块至少保留 **10 道** 面试题，每题包含：

- **简短回答（30秒版）** — 面试开场快速应答
- **深入回答（2分钟版）** — 面试官追问时结合项目展开

新增功能时追加 2～3 道实战题。

---

> **面试以代码为准，文档当复习提纲。** 同步基准：`backend/main.py` 路由 + `frontend/package.json`（Vue 3）+ `frontend/src/pages/ChatPage.vue`。
>
> 相对早期提纲，代码已补充：`auth/` 鉴权与多用户隔离、`conversation/` 会话持久化、长期记忆、`eval/` 评估、流式 `/chat/stream` 与停止生成——细节见 [architecture.md](./architecture.md)。
