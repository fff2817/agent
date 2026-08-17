"""
Long-term Memory FAISS 向量库 — 与 RAG 索引物理分离。

为什么单独建索引?
    · RAG 存 PDF chunk，全局共享，metadata 含 page/source
    · Long-term 存用户记忆，按 user_id 隔离，metadata 含 memory_type
    · 混用一个 index 会导致检索污染、权限混乱

复用 rag/vectorstore.py 的设计:
    faiss.index 存向量，metadata.json 存原文与业务字段。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import faiss
import numpy as np

from core.config import get_settings
from lc.memory.types import MemoryRecord, MemoryType

logger = logging.getLogger(__name__)

INDEX_FILENAME = "faiss.index"
METADATA_FILENAME = "metadata.json"


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
        self.faiss_id = faiss_id
        self.record = record


class MemoryVectorStore:
    """
    长期记忆专用 FAISS 封装。

    metadata 与 FAISS 内部 ID（0, 1, 2, ...）一一对应。
    """

    def __init__(self, store_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.store_dir = Path(store_dir or settings.memory_store_path)
        self.store_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.store_dir / INDEX_FILENAME
        self.metadata_path = self.store_dir / METADATA_FILENAME

        self._index: faiss.Index | None = None
        self._metadata: list[dict] = []
        self._dimensions: int = 0

        logger.info("[MemoryFAISS] 初始化, 目录=%s", self.store_dir)

        if self.index_path.exists() and self.metadata_path.exists():
            self.load()

    @property
    def count(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal

    def count_for_user(self, user_id: str) -> int:
        """该用户在索引中的记忆条数（每用户独立索引时等于 count）。"""
        return self.count

    def list_for_user(self, user_id: str) -> list[MemoryRecord]:
        """列出该用户的全部长期记忆（按 created_at 降序）。"""
        records = [_meta_to_record(meta) for meta in self._metadata]
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
        追加一条记忆向量。

        返回:
            FAISS 内部 ID
        """
        if not embedding:
            raise ValueError("embedding 不能为空")

        dim = len(embedding)
        vector = np.array([embedding], dtype=np.float32)
        faiss.normalize_L2(vector)

        if self._index is None:
            self._index = faiss.IndexFlatIP(dim)
            self._dimensions = dim
            logger.info("[MemoryFAISS] 创建新索引, 维度=%d", dim)
        elif self._dimensions != dim:
            raise ValueError(
                f"索引维度 {self._dimensions} 与向量维度 {dim} 不匹配"
            )

        faiss_id = self.count
        self._index.add(vector)
        self._metadata.append(
            {
                "memory_id": record.memory_id,
                "user_id": record.user_id,
                "content": record.content,
                "memory_type": record.memory_type.value,
                "importance": record.importance,
                "source_session_id": record.source_session_id,
                "raw_user": record.raw_user,
                "created_at": record.created_at,
                "embedding_model": model,
            }
        )

        logger.info(
            "[MemoryFAISS] 写入 memory_id=%s user=%s type=%s",
            record.memory_id,
            record.user_id,
            record.memory_type.value,
        )
        return faiss_id

    def save(self) -> None:
        if self._index is None or self.count == 0:
            logger.warning("[MemoryFAISS] save: 索引为空，跳过")
            return

        faiss.write_index(self._index, str(self.index_path))
        payload = {
            "version": 1,
            "dimensions": self._dimensions,
            "total": self.count,
            "memories": self._metadata,
        }
        self.metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[MemoryFAISS] save 完成, 共 %d 条", self.count)

    def load(self) -> None:
        if not self.index_path.exists():
            raise FileNotFoundError(f"索引文件不存在: {self.index_path}")
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"metadata 不存在: {self.metadata_path}")

        self._index = faiss.read_index(str(self.index_path))
        self._dimensions = self._index.d

        raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self._metadata = raw.get("memories", [])

        if self._index.ntotal != len(self._metadata):
            raise ValueError(
                f"向量数 ({self._index.ntotal}) 与 metadata ({len(self._metadata)}) 不一致"
            )

        logger.info(
            "[MemoryFAISS] load 完成, 维度=%d, 条数=%d",
            self._dimensions,
            self.count,
        )

    def search(
        self,
        query_embedding: list[float],
        *,
        user_id: str | None = None,
        top_k: int | None = None,
    ) -> list[MemorySearchResult]:
        """
        语义检索记忆。

        每用户独立索引，无需 post-filter。
        """
        if self._index is None or self.count == 0:
            return []

        settings = get_settings()
        k = top_k or settings.memory_top_k

        if len(query_embedding) != self._dimensions:
            raise ValueError(
                f"query 维度 {len(query_embedding)} != 索引维度 {self._dimensions}"
            )

        fetch_k = min(self.count, k)

        query_vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query_vec)

        scores, indices = self._index.search(query_vec, fetch_k)

        results: list[MemorySearchResult] = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue

            meta = self._metadata[int(idx)]
            record = _meta_to_record(meta)
            weighted_score = float(score) * record.importance
            results.append(
                MemorySearchResult(
                    rank=0,
                    score=weighted_score,
                    faiss_id=int(idx),
                    record=record,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        for rank, item in enumerate(results[:k], start=1):
            item.rank = rank

        return results[:k]


_stores: dict[str, MemoryVectorStore] = {}


def get_memory_vector_store(user_id: str) -> MemoryVectorStore:
    """按 user_id 获取长期记忆 FAISS 实例（每用户独立目录）。"""
    if user_id not in _stores:
        settings = get_settings()
        store_dir = Path(settings.memory_store_path) / user_id
        _stores[user_id] = MemoryVectorStore(store_dir=store_dir)
    return _stores[user_id]


def _meta_to_record(meta: dict) -> MemoryRecord:
    return MemoryRecord(
        memory_id=meta["memory_id"],
        user_id=meta["user_id"],
        content=meta["content"],
        memory_type=MemoryType(meta["memory_type"]),
        importance=float(meta.get("importance", 0.7)),
        source_session_id=meta.get("source_session_id"),
        raw_user=meta.get("raw_user", ""),
        created_at=meta.get("created_at", ""),
    )
