# 模块作用

**Chroma** 在本项目中是 **向量数据库**——负责持久化文档 / 长期记忆的 Embedding，并在提问时做 Top-K 相似度检索。

封装代码：

- RAG：`backend/infra/rag_vectorstore.py` 的 `RagVectorStore`（LangChain `Chroma`）
- Memory：`backend/infra/memory_vectorstore.py` 的 `MemoryVectorStore`

迁移说明见 [chroma-migration.md](./chroma-migration.md)。

# 核心原理

## 向量相似度

Embedding 把文本变成高维空间中的点。语义相近 → 距离更近。用户问题也 embed 后，找最近邻即最相关 chunk。

## 本项目的度量

- Collection：`hnsw:space=cosine`
- 入库 / 查询前做 **L2 归一化**
- 对外分数：`score = 1 - distance`（越高越相似）

## 持久化与增量

每用户独立目录（`rag_store_path/{user_id}`、`memory_store_path/{user_id}`）：

```text
{user_id}/
├── chroma.sqlite3
└── <uuid>/          # 分段向量数据
```

`add_embeddings` / `add_memory` 为 **追加写入**，写入即落盘；`save()` 保留为空操作以兼容旧调用方。

## 与原文如何关联

向量与 documents / metadatas 同库存储。检索直接带回文本、`source`、`page`、`doc_id` 等字段，无需再维护单独的 `metadata.json`。

# 关键代码路径

| 能力 | 入口 |
|------|------|
| 入库 | `lc/rag/ingest.py` → `RagVectorStore.add_embeddings` |
| 检索 | `lc/rag/retriever.py` → `search` |
| Agent 工具 | `lc/tools/search_docs.py` |
| 长期记忆 | `lc/memory/ingester.py` / `retriever.py` |

# 演示

```bash
cd backend
.venv\Scripts\python.exe -m scripts.demos.demo_chroma --mock
```

# 面试题（摘要）

**为什么用 Chroma？**  
嵌入式、可持久化、支持增量与 metadata 过滤，并用 LangChain 集成，接口对上层 RAG/Memory 友好。

**换 Embedding 模型要注意什么？**  
维度变化必须清空对应用户目录并重建索引，不能混用旧向量。

**`faiss_id` 是什么？**  
历史字段名，现为内部 `seq_id`，保留以兼容 API / Eval JSON，不代表仍使用 FAISS。

**相关文档**：[chroma-migration.md](./chroma-migration.md) · [rag.md](./rag.md) · [architecture.md](./architecture.md)
