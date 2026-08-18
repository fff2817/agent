# FAISS → Chroma 迁移说明

将项目向量数据库从 **FAISS** 迁移到 **LangChain Chroma**，保持 RAG / 长期记忆功能与 HTTP API 契约不变。

## 目标达成情况

| 要求 | 实现 |
|------|------|
| RAG 功能不变 | 仍走 ingest → embed → store → retriever → chain / `search_docs` |
| API 接口不变 | `/documents/*`、`/rag/*`、`/memory/*`、`/chat*` 路径与响应字段未改 |
| 向量持久化 | `persist_directory` → `chroma.sqlite3` + 分段数据目录 |
| 增量添加文档 | `collection.add` 追加写入，无需全量重建 |
| LangChain Chroma | `from langchain_chroma import Chroma` |
| `faiss_id` 字段 | **保留**（值为内部 `seq_id`），兼容 Eval / schemas |

## 架构变化（摘要）

```
旧: Embedding → Faiss IndexFlatIP + metadata.json
新: Embedding → LangChain Chroma (hnsw:space=cosine) + 自动落盘
```

- **相似度**：入库/查询前 L2 归一化；Chroma 返回 cosine distance，对外 `score = 1 - distance`（越高越相似，对齐原 FAISS 内积语义）。
- **多用户隔离**：仍按 `rag_store_path/{user_id}`、`memory_store_path/{user_id}` 分目录。
- **类名兼容**：`FaissVectorStore = RagVectorStore`，现有 `from infra.rag_vectorstore import FaissVectorStore` 无需改 import。

## 需要修改的文件与原因

### 核心实现（必改）

| 文件 | 原因 |
|------|------|
| `backend/infra/rag_vectorstore.py` | RAG 向量库实现从 FAISS 换成 LangChain Chroma；保留 `add_embeddings` / `search` / `save` / `load` / `remove_by_doc_id_or_source` 等对外方法 |
| `backend/infra/memory_vectorstore.py` | 长期记忆向量库同样迁到 Chroma；保留 `add_memory` / `search` / `list_for_user` 等 API |
| `backend/requirements.txt` | 移除 `faiss-cpu`，增加 `chromadb`、`langchain-chroma` |

### 配置与注释（配套）

| 文件 | 原因 |
|------|------|
| `backend/core/config.py` | 注释改为 Chroma；路径环境变量 `RAG_STORE_PATH` / `MEMORY_STORE_PATH` 含义不变 |
| `backend/infra/catalog.py` | 文案去掉「FAISS」；仍调用 `get_chunk_metadata` / `assign_doc_id_to_chunks` |
| `backend/infra/__init__.py` | 包说明改为 Chroma |
| `backend/lc/rag/types.py` | `SearchResult` 文档说明：`faiss_id` 为兼容字段名 |

### 测试与 Demo

| 文件 | 原因 |
|------|------|
| `backend/tests/test_multi_user.py` | 持久化断言改为 `chroma.sqlite3`；增加 store 缓存清理，避免跨测污染 |
| `backend/scripts/demos/demo_chroma.py` | 演示 Chroma 增删查与持久化 |
| `backend/scripts/demos/demo_rag.py` | mock 向量改用 numpy L2 归一化 |

### 文档

| 文件 | 原因 |
|------|------|
| `docs/chroma-migration.md` | 本迁移说明（新建） |
| `docs/README.md` | 索引增加 Chroma 迁移文档入口 |

### 刻意未改（保持 API / 兼容）

| 范围 | 原因 |
|------|------|
| `backend/api/*.py` 路由与请求/响应模型 | 接口契约不变 |
| `backend/models/schemas.py` 中的 `faiss_id` | 对外 JSON 字段名保持稳定，避免前端 / Eval 破坏 |
| `backend/eval/*` | 继续读写 `faiss_id` |
| `FaissVectorStore` 别名 | `FaissVectorStore = RagVectorStore`，兼容旧 import |

上层业务（`lc/rag/*`、`lc/memory/*`、`lc/tools/search_docs.py`）**无需改调用签名**，因为仍依赖 `get_rag_vector_store` / `get_memory_vector_store` 与相同方法名。

## 磁盘格式变化

| 旧（FAISS） | 新（Chroma） |
|-------------|--------------|
| `{user}/faiss.index` | `{user}/chroma.sqlite3` |
| `{user}/metadata.json` | 元数据在 Chroma collection 内 |
| — | `{user}/<uuid>/` 分段向量文件 |

**不兼容**：旧 FAISS 索引无法自动导入。升级后需**重新上传/入库**文档与长期记忆。

建议升级步骤：

1. 备份旧目录：`rag/store/`、`memory/store/`
2. `pip install -r backend/requirements.txt`
3. 删除或移走旧 `faiss.index` / `metadata.json`（避免误以为仍在用）
4. 重启服务，重新 `POST /documents/upload`（及必要时重新产生长期记忆）

## 验证

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q
```

重点用例：

- `tests/test_multi_user.py` — 每用户 Chroma 目录隔离与持久化
- `tests/test_rag_router.py` — 路由 + 向量过滤检索
- 手工：`python -m scripts.demos.demo_chroma --mock`

## 使用注意

1. **换 Embedding 模型**：维度变化后仍须清空对应用户目录并重建索引。
2. **`save()`**：Chroma 写入即落盘；方法保留为空操作兼容，调用方无需删除。
3. **删除文档**：Chroma 支持按 id 删除，比旧 FAISS「重建索引」更直接（`remove_by_doc_id_or_source`）。
