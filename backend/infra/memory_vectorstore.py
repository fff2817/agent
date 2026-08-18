"""
Long-term Memory 向量库 — 基于 LangChain Chroma，与 RAG 索引物理分离。

为什么单独建集合?
    · RAG 存文档 chunk，metadata 含 page/source
    · Long-term 存用户记忆，按 user_id 隔离目录，metadata 含 memory_type
    · 混用会导致检索污染、权限混乱

对外 API 与旧 Chroma MemoryVectorStore 对齐，上层 memory 链无需改接口。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import numpy as np
from langchain_chroma import Chroma

from core.config import get_settings
from lc.memory.types import MemoryRecord, MemoryType

logger = logging.getLogger(__name__)

COLLECTION_NAME = "memories"


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (vectors / norms).astype(np.float32)


def _chroma_meta(meta: dict) -> dict:
    out: dict = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


class MemorySearchResult:
    """单条记忆检索结果。"""

    __slots__ = ("rank", "score", "faiss_id", "record")

    def __init__(
        self,
        rank: int,
        score: float,
        faiss_id: int,
        record: MemoryRecord,
    ) -> None:
        self.rank = rank
        self.score = score
        self.faiss_id = faiss_id  # 字段名保持 API 兼容（内部为 seq_id）
        self.record = record


class MemoryVectorStore:
    """
    长期记忆专用 Chroma 封装（LangChain 集成）。

    每用户独立 persist_directory，metadata 含业务字段。
    """

    def __init__(self, store_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.store_dir = Path(store_dir or settings.memory_store_path)
        self.store_dir.mkdir(parents=True, exist_ok=True)

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
            "[ChromaMemory] 初始化, 目录=%s, 条数=%d",
            self.store_dir,
            self.count,
        )

    @property
    def _collection(self):
        return self._vs._collection

    @property
    def count(self) -> int:
        return int(self._collection.count())

    def count_for_user(self, user_id: str) -> int:
        """该用户在索引中的记忆条数（每用户独立索引时等于 count）。"""
        return self.count

    def list_for_user(self, user_id: str) -> list[MemoryRecord]:
        """列出该用户的全部长期记忆（按 created_at 降序）。"""
        if self.count == 0:
            return []
        data = self._vs.get(include=["metadatas"])
        records = [
            _meta_to_record(meta or {})
            for meta in (data.get("metadatas") or [])
        ]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def add_memory(
        self,
        record: MemoryRecord,
        embedding: list[float],
        *,
        model: str,
    ) -> int:
        """
        追加一条记忆向量（增量写入，自动持久化）。

        返回:
            内部 seq_id（兼容旧 Chroma ID 语义）
        """
        if not embedding:
            raise ValueError("embedding 不能为空")

        dim = len(embedding)
        if self._dimensions and self._dimensions != dim:
            raise ValueError(
                f"索引维度 {self._dimensions} 与向量维度 {dim} 不匹配"
            )

        vector = _l2_normalize(np.array([embedding], dtype=np.float32))[0].tolist()
        seq_id = self.count
        chroma_id = f"mem-{record.memory_id}-{uuid.uuid4().hex[:8]}"

        meta = _chroma_meta(
            {
                "seq_id": seq_id,
                "memory_id": record.memory_id,
                "user_id": record.user_id,
                "content": record.content,
                "memory_type": record.memory_type.value,
                "importance": float(record.importance),
                "source_session_id": record.source_session_id or "",
                "raw_user": record.raw_user or "",
                "created_at": record.created_at or "",
                "embedding_model": model,
                "dimensions": dim,
            }
        )

        self._collection.add(
            ids=[chroma_id],
            embeddings=[vector],
            documents=[record.content],
            metadatas=[meta],
        )
        self._dimensions = dim

        logger.info(
            "[ChromaMemory] 写入 memory_id=%s user=%s type=%s",
            record.memory_id,
            record.user_id,
            record.memory_type.value,
        )
        return seq_id

    def save(self) -> None:
        """Chroma 自动持久化；保留方法以兼容调用方。"""
        if self.count == 0:
            logger.warning("[ChromaMemory] save: 集合为空，跳过")
            return
        logger.info("[ChromaMemory] save 完成, 共 %d 条", self.count)

    def load(self) -> None:
        self._vs = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=str(self.store_dir),
            embedding_function=None,
            collection_metadata={"hnsw:space": "cosine"},
        )
        logger.info("[ChromaMemory] load 完成, 条数=%d", self.count)

    def search(
        self,
        query_embedding: list[float],
        *,
        user_id: str | None = None,
        top_k: int | None = None,
    ) -> list[MemorySearchResult]:
        """
        语义检索记忆。

        每用户独立目录，无需 post-filter。
        """
        if self.count == 0:
            return []

        settings = get_settings()
        k = top_k or settings.memory_top_k

        if self._dimensions and len(query_embedding) != self._dimensions:
            raise ValueError(
                f"query 维度 {len(query_embedding)} != 索引维度 {self._dimensions}"
            )

        fetch_k = min(self.count, k)
        query_vec = _l2_normalize(
            np.array([query_embedding], dtype=np.float32)
        )[0].tolist()

        raw = self._collection.query(
            query_embeddings=[query_vec],
            n_results=fetch_k,
            include=["distances", "metadatas"],
        )

        ids = (raw.get("ids") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]

        results: list[MemorySearchResult] = []
        for _cid, distance, meta in zip(ids, distances, metadatas):
            meta = meta or {}
            record = _meta_to_record(meta)
            cosine_sim = 1.0 - float(distance)
            weighted_score = cosine_sim * record.importance
            results.append(
                MemorySearchResult(
                    rank=0,
                    score=weighted_score,
                    faiss_id=int(meta.get("seq_id", 0)),
                    record=record,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        for rank, item in enumerate(results[:k], start=1):
            item.rank = rank

        return results[:k]


_stores: dict[str, MemoryVectorStore] = {}


def get_memory_vector_store(user_id: str) -> MemoryVectorStore:
    """按 user_id 获取长期记忆 Chroma 实例（每用户独立目录）。"""
    if user_id not in _stores:
        settings = get_settings()
        store_dir = Path(settings.memory_store_path) / user_id
        _stores[user_id] = MemoryVectorStore(store_dir=store_dir)
    return _stores[user_id]


def clear_memory_store_cache() -> None:
    """测试用：清空进程内 store 缓存。"""
    _stores.clear()


def _meta_to_record(meta: dict) -> MemoryRecord:
    return MemoryRecord(
        memory_id=meta["memory_id"],
        user_id=meta["user_id"],
        content=meta.get("content", ""),
        memory_type=MemoryType(meta["memory_type"]),
        importance=float(meta.get("importance", 0.7)),
        source_session_id=meta.get("source_session_id") or None,
        raw_user=meta.get("raw_user", ""),
        created_at=meta.get("created_at", ""),
    )
