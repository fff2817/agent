# Backend 目录说明

```text
backend/
├── main.py              # FastAPI 入口
├── requirements.txt
├── api/                 # HTTP 路由（薄，只做编排）
├── auth/                # 登录 / JWT / 多用户
├── conversation/        # UI 会话列表（SQLite）
├── models/              # API Schema
├── core/                # 配置、SSE、可选 tracing
├── lc/                  # LangChain 领域层（业务核心）
│   ├── llm/             # ChatOpenAI、Embeddings
│   ├── prompts/         # ChatPromptTemplate
│   ├── tools/           # @tool 工具
│   ├── memory/          # 对话记忆 / 压缩 / 长期记忆编排
│   ├── rag/             # RAG 链、检索、入库
│   ├── agent/           # Tool-calling Agent 门面
│   └── graph/           # LangGraph 二期骨架
├── infra/               # 基础设施（存储 / 解析）
│   ├── session_store.py
│   ├── longterm_store.py
│   ├── *_vectorstore.py
│   ├── catalog.py
│   └── file_parser/
├── eval/                # RAG 评估
├── scripts/             # seed、demos
└── tests/
```

依赖方向：`api` → `lc` → `infra` → `core.config`
