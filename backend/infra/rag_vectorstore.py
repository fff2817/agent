"""
RAG 向量索引 — 基于 LangChain Chroma，持久化 Embedding 并做 Similarity Search。

教学要点 — Chroma 是什么?

    Chroma 是开源的嵌入式向量数据库：向量与 metadata 同库存储，支持磁盘持久化、
    增量写入，以及按 metadata 过滤。

    本模块对外 API 与旧 Chroma 封装对齐（add_embeddings / search / save / load），
    上层 RAG / Agent / 文档 API 无需改接口。

    相似度:
        collection 使用 hnsw:space=cosine；入库与查询前做 L2 归一化。
        返回 score = 1 - distance（越高越相似，语义对齐原 Chroma 内积分数）。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

import numpy as np
from langchain_chroma import Chroma

from core.config import get_settings
from lc.rag.types import EmbeddedChunk, SearchResult, TextChunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "rag_chunks"


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """按行 L2 归一化，避免零向量除零。"""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (vectors / norms).astype(np.float32)


def _chroma_meta(meta: dict) -> dict:
    """Chroma metadata 仅允许 str/int/float/bool。"""
    out: dict = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


class RagVectorStore:
    """
    LangChain Chroma 向量库封装 — 负责向量的持久化与 Top-K 检索。

    目录结构（store_dir 下，由 Chroma 管理）:
        chroma.sqlite3  ← 元数据与索引
        <uuid>/         ← 分段向量数据
    """

    def __init__(self, store_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.store_dir = Path(store_dir or settings.rag_store_path)
        self.store_dir.mkdir(parents=True, exist_ok=True)

        # 兼容旧调用方仍读取这些路径属性（Chroma 不再使用）
        self.index_path = self.store_dir / "chroma.sqlite3"
        self.metadata_path = self.store_dir / "chroma.sqlite3"

        self._dimensions: int = 0
        self._vs = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=str(self.store_dir),
            embedding_function=None,
            collection_metadata={"hnsw:space": "cosine"},
        )

        if self.count > 0:
            sample = self._vs.get(limit=1, include=["embeddings", "metadatas"])
            embeddings = sample.get("embeddings")
            if embeddings is not None and len(embeddings) > 0 and embeddings[0] is not None:
                self._dimensions = len(embeddings[0])
            else:
                metas = sample.get("metadatas") or []
                if metas and metas[0] and "dimensions" in metas[0]:
                    self._dimensions = int(metas[0]["dimensions"])

        logger.info(
            "[ChromaRAG] 初始化向量库, 目录=%s, 条数=%d, 维度=%d",
            self.store_dir,
            self.count,
            self._dimensions,
        )

    @property
    def _collection(self):
        return self._vs._collection

    @property
    def count(self) -> int:
        """当前集合中的向量数量。"""
        return int(self._collection.count())

    def add_embeddings(self, embedded_chunks: list[EmbeddedChunk]) -> int:
        """
        把 EmbeddedChunk 列表写入 Chroma（追加 / 增量）。

        返回:
            本次新增的向量数量
        """
        if not embedded_chunks:
            logger.warning("[ChromaRAG] add_embeddings: 空列表，跳过")
            return 0

        dim = embedded_chunks[0].dimensions
        for item in embedded_chunks:
            if item.dimensions != dim:
                raise ValueError(
                    f"向量维度不一致: 期望 {dim}, 实际 {item.dimensions}"
                )

        if self._dimensions and self._dimensions != dim:
            raise ValueError(
                f"索引维度 {self._dimensions} 与新向量维度 {dim} 不匹配"
            )

        vectors = np.array(
            [item.embedding for item in embedded_chunks],
            dtype=np.float32,
        )
        vectors = _l2_normalize(vectors)

        start_seq = self.count
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []
        for offset, item in enumerate(embedded_chunks):
            c = item.chunk
            seq_id = start_seq + offset
            chroma_id = f"chunk-{c.chunk_id}-{uuid.uuid4().hex[:12]}"
            meta = {
                "seq_id": seq_id,
                "chunk_id": int(c.chunk_id) if str(c.chunk_id).isdigit() else str(c.chunk_id),
                "source": c.source,
                "page": int(c.page),
                "char_count": int(c.char_count or len(c.text)),
                "embedding_model": item.model,
                "dimensions": dim,
            }
            if c.doc_id:
                meta["doc_id"] = c.doc_id
            ids.append(chroma_id)
            texts.append(c.text)
            metadatas.append(_chroma_meta(meta))

        self._collection.add(
            ids=ids,
            embeddings=vectors.tolist(),
            documents=texts,
            metadatas=metadatas,
        )
        self._dimensions = dim
        logger.info(
            "[ChromaRAG] 已增量写入 %d 条, 总量=%d",
            len(embedded_chunks),
            self.count,
        )
        return len(embedded_chunks)

    def save(self) -> None:
        """
        持久化提示 — LangChain Chroma(persist_directory=...) 在写入时自动落盘。
        保留此方法以兼容现有调用方（ingest / API）。
        """
        if self.count == 0:
            logger.warning("[ChromaRAG] save: 集合为空，跳过")
            return
        logger.info("[ChromaRAG] save — 已持久化至 %s (count=%d)", self.store_dir, self.count)

    def load(self) -> None:
        """从 persist_directory 重新打开集合（通常 __init__ 已完成加载）。"""
        self._vs = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=str(self.store_dir),
            embedding_function=None,
            collection_metadata={"hnsw:space": "cosine"},
        )
        logger.info("[ChromaRAG] load — 完成, 条数=%d", self.count)

    def search(
        self,
        query_embedding: list[float],
        top_k: int | None = None,
        *,
        doc_ids: list[str] | None = None,
        expand_factor: int | None = None,
    ) -> list[SearchResult]:
        """
        Similarity Search — 找与 query 向量最相似的 Top-K 个 chunk。

        参数:
            query_embedding: 用户问题的 embedding 向量
            top_k:           返回几条；默认读 config.retrieval_top_k
            doc_ids:         可选，仅保留这些文档的 chunk
            expand_factor:   过滤时扩大候选池倍数
        """
        if self.count == 0:
            logger.warning("[ChromaRAG] search: 集合为空")
            return []

        settings = get_settings()
        k = top_k or settings.retrieval_top_k
        fetch_k = k
        doc_filter = set(doc_ids or [])
        if doc_filter:
            factor = expand_factor or settings.rag_route_expand_factor
            fetch_k = min(k * factor, self.count)
        fetch_k = min(fetch_k, self.count)

        if self._dimensions and len(query_embedding) != self._dimensions:
            raise ValueError(
                f"query 维度 {len(query_embedding)} != 索引维度 {self._dimensions}"
            )

        query_vec = _l2_normalize(
            np.array([query_embedding], dtype=np.float32)
        )[0].tolist()

        raw = self._collection.query(
            query_embeddings=[query_vec],
            n_results=fetch_k,
            include=["distances", "metadatas", "documents"],
        )

        ids = (raw.get("ids") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]

        results: list[SearchResult] = []
        for chroma_id, distance, meta, text in zip(ids, distances, metadatas, documents):
            meta = meta or {}
            if doc_filter:
                chunk_doc_id = str(meta.get("doc_id", ""))
                if chunk_doc_id not in doc_filter:
                    continue

            # cosine distance → 与旧 Chroma 内积分数同向（越高越相似）
            score = 1.0 - float(distance)
            chunk_id_raw = meta.get("chunk_id", 0)
            try:
                chunk_id = int(chunk_id_raw)
            except (TypeError, ValueError):
                chunk_id = chunk_id_raw

            chunk = TextChunk(
                chunk_id=chunk_id,
                text=text or "",
                source=str(meta.get("source", "")),
                page=int(meta.get("page", 1)),
                char_count=int(meta.get("char_count", len(text or ""))),
                doc_id=str(meta.get("doc_id", "")),
            )
            seq_id = int(meta.get("seq_id", len(results)))
            results.append(
                SearchResult(
                    rank=len(results) + 1,
                    score=score,
                    faiss_id=seq_id,  # 字段名保持 API 兼容
                    chunk=chunk,
                )
            )
            logger.info(
                "[ChromaRAG] #%d score=%.4f id=%s source=%s page=%d",
                len(results),
                score,
                chroma_id,
                chunk.source,
                chunk.page,
            )
            if len(results) >= k:
                break

        logger.info("[ChromaRAG] search 完成 — 返回 %d 条", len(results))
        return results

    def get_chunk_metadata(self) -> list[dict]:
        """返回按 seq_id 排序的 chunk metadata（供 catalog 同步等用途）。"""
        if self.count == 0:
            return []
        data = self._vs.get(include=["metadatas", "documents"])
        rows: list[dict] = []
        for chroma_id, meta, text in zip(
            data.get("ids") or [],
            data.get("metadatas") or [],
            data.get("documents") or [],
        ):
            item = dict(meta or {})
            item["text"] = text or ""
            item["_chroma_id"] = chroma_id
            rows.append(item)
        rows.sort(key=lambda m: int(m.get("seq_id", 0)))
        return rows

    def assign_doc_id_to_chunks(self, indices: list[int], doc_id: str) -> None:
        """按 get_chunk_metadata() 的下标批量为 chunk 写入 doc_id。"""
        rows = self.get_chunk_metadata()
        ids: list[str] = []
        metas: list[dict] = []
        for idx in indices:
            if idx < 0 or idx >= len(rows):
                continue
            row = dict(rows[idx])
            chroma_id = row.pop("_chroma_id", None)
            if not chroma_id:
                continue
            row["doc_id"] = doc_id
            row.pop("text", None)
            ids.append(chroma_id)
            metas.append(_chroma_meta(row))
        if ids:
            self._collection.update(ids=ids, metadatas=metas)

    def clear(self) -> None:
        """清空集合并删除持久化目录内容。"""
        try:
            self._vs.delete_collection()
        except Exception:
            pass
        if self.store_dir.exists():
            for child in self.store_dir.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._dimensions = 0
        self._vs = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=str(self.store_dir),
            embedding_function=None,
            collection_metadata={"hnsw:space": "cosine"},
        )
        logger.info("[ChromaRAG] 集合已清空")

    def remove_by_doc_id_or_source(
        self,
        *,
        doc_id: str | None = None,
        source: str | None = None,
    ) -> int:
        """按 doc_id 和/或 source 删除 chunk（Chroma 原生 delete，无需重建索引）。"""
        if self.count == 0:
            return 0

        rows = self.get_chunk_metadata()
        source_key = (source or "").strip().lower()
        to_delete: list[str] = []
        for row in rows:
            if doc_id and row.get("doc_id") == doc_id:
                to_delete.append(row["_chroma_id"])
                continue
            if source_key and str(row.get("source", "")).strip().lower() == source_key:
                to_delete.append(row["_chroma_id"])

        if not to_delete:
            return 0

        self._vs.delete(ids=to_delete)
        logger.info("[ChromaRAG] 已删除 %d 条 chunk, 剩余 %d", len(to_delete), self.count)
        return len(to_delete)


# 兼容旧类名（历史 import 仍可使用）
FaissVectorStore = RagVectorStore

_stores: dict[str, RagVectorStore] = {}


def get_rag_vector_store(user_id: str) -> RagVectorStore:
    """按 user_id 获取 RAG Chroma 实例（每用户独立目录）。"""
    if user_id not in _stores:
        settings = get_settings()
        store_dir = Path(settings.rag_store_path) / user_id
        _stores[user_id] = RagVectorStore(store_dir=store_dir)
    return _stores[user_id]


def clear_rag_store_cache() -> None:
    """测试用：清空进程内 store 缓存。"""
    _stores.clear()
