
"""
FAISS 向量索引 — 保存 Embedding 并做 Similarity Search。

教学要点 — FAISS 是什么? 怎么工作?

    FAISS (Facebook AI Similarity Search) 是 Meta 开源的「向量搜索引擎」。

    你可以把它想象成:
        · 一个巨大的「坐标系」，每个 Embedding 是空间里的一个点
        · 用户提问 → 问题也变成点
        · FAISS 的工作: 在这个空间里快速找到离问题最近的 K 个点

    本模块只做两件事:
        1. 存 — 把 chunk 的向量写入 FAISS 索引（另用 JSON 存原文）
        2. 搜 — 给定 query 向量，返回 Top-K 最相似的 chunk

    为什么向量要单独存 JSON?
        FAISS 只存数字，不存文本。索引返回的是「第几个向量」，
        我们用这个编号去 metadata.json 里取回原文、页码、来源。

    相似度怎么算?
        使用 IndexFlatIP + L2 归一化 → 内积 = 余弦相似度
        分数越高，语义越相近。
"""

import json
import logging
from pathlib import Path

import faiss
import numpy as np

from core.config import get_settings
from rag.types import EmbeddedChunk, SearchResult, TextChunk

logger = logging.getLogger(__name__)

INDEX_FILENAME = "faiss.index"
METADATA_FILENAME = "metadata.json"


class FaissVectorStore:
    """
    FAISS 向量库封装 — 负责向量的持久化与 Top-K 检索。

    文件结构（store_dir 下）:
        faiss.index    ← FAISS 二进制索引（只有向量）
        metadata.json  ← chunk 原文 + 来源 + 页码（与向量下标一一对应）
    """

    def __init__(self, store_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.store_dir = Path(store_dir or settings.rag_store_path)
        self.store_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.store_dir / INDEX_FILENAME
        self.metadata_path = self.store_dir / METADATA_FILENAME

        # FAISS 索引对象；None 表示尚未创建
        self._index: faiss.Index | None = None
        # 与 FAISS 内部 ID（0,1,2,...）对齐的 chunk 元数据列表
        self._metadata: list[dict] = []
        self._dimensions: int = 0

        logger.info("[FAISS] 初始化向量库, 目录=%s", self.store_dir)

        if self.index_path.exists() and self.metadata_path.exists():
            self.load()

    @property
    def count(self) -> int:
        """当前索引中的向量数量。"""
        if self._index is None:
            return 0
        return self._index.ntotal

    def add_embeddings(self, embedded_chunks: list[EmbeddedChunk]) -> int:
        """
        把 EmbeddedChunk 列表写入 FAISS 索引（追加模式）。

        步骤:
            1. 校验向量维度一致
            2. 转成 numpy float32 矩阵
            3. L2 归一化（使内积 = 余弦相似度）
            4. index.add() 追加向量
            5. 同步追加 metadata

        返回:
            本次新增的向量数量
        """
        if not embedded_chunks:
            logger.warning("[FAISS] add_embeddings: 空列表，跳过")
            return 0

        logger.info("[FAISS] Step 1 — 准备写入 %d 条向量", len(embedded_chunks))

        dim = embedded_chunks[0].dimensions
        for item in embedded_chunks:
            if item.dimensions != dim:
                raise ValueError(
                    f"向量维度不一致: 期望 {dim}, 实际 {item.dimensions}"
                )

        # Step 2: 构建 numpy 矩阵 (n, dim)
        vectors = np.array(
            [item.embedding for item in embedded_chunks],
            dtype=np.float32,
        )
        logger.info("[FAISS] Step 2 — 构建矩阵 shape=%s", vectors.shape)

        # Step 3: L2 归一化 — 归一化后两个向量的内积 = 余弦相似度
        faiss.normalize_L2(vectors)
        logger.info("[FAISS] Step 3 — L2 归一化完成（内积即余弦相似度）")

        # Step 4: 创建或追加到索引
        if self._index is None:
            # IndexFlatIP = 暴力精确搜索 + 内积（适合中小规模、学习/demo）
            self._index = faiss.IndexFlatIP(dim)
            self._dimensions = dim
            logger.info("[FAISS] Step 4 — 创建新索引 IndexFlatIP, 维度=%d", dim)
        elif self._dimensions != dim:
            raise ValueError(
                f"索引维度 {self._dimensions} 与新向量维度 {dim} 不匹配"
            )
        else:
            logger.info("[FAISS] Step 4 — 追加到已有索引, 当前共 %d 条", self.count)

        self._index.add(vectors)
        logger.info("[FAISS] Step 5 — 向量已 add, 索引总量=%d", self.count)

        # Step 6: 追加 metadata（FAISS ID = metadata 列表下标）
        for item in embedded_chunks:
            c = item.chunk
            meta = {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "source": c.source,
                "page": c.page,
                "char_count": c.char_count,
                "embedding_model": item.model,
            }
            if c.doc_id:
                meta["doc_id"] = c.doc_id
            self._metadata.append(meta)

        logger.info("[FAISS] Step 6 — metadata 已更新, 共 %d 条记录", len(self._metadata))
        return len(embedded_chunks)

    def save(self) -> None:
        """
        持久化到磁盘: faiss.index + metadata.json
        """
        if self._index is None or self.count == 0:
            logger.warning("[FAISS] save: 索引为空，跳过")
            return

        logger.info("[FAISS] save — 写入 %s", self.index_path)
        faiss.write_index(self._index, str(self.index_path))

        payload = {
            "version": 1,
            "dimensions": self._dimensions,
            "total": self.count,
            "chunks": self._metadata,
        }
        logger.info("[FAISS] save — 写入 %s (%d 条 metadata)", self.metadata_path, self.count)
        self.metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[FAISS] save — 完成")

    def load(self) -> None:
        """
        从磁盘加载 faiss.index 和 metadata.json
        """
        if not self.index_path.exists():
            raise FileNotFoundError(f"索引文件不存在: {self.index_path}")
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"metadata 不存在: {self.metadata_path}")

        logger.info("[FAISS] load — 读取 %s", self.index_path)
        self._index = faiss.read_index(str(self.index_path))
        self._dimensions = self._index.d

        raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self._metadata = raw.get("chunks", [])

        if self._index.ntotal != len(self._metadata):
            raise ValueError(
                f"索引向量数 ({self._index.ntotal}) 与 metadata 条数 ({len(self._metadata)}) 不一致"
            )

        logger.info(
            "[FAISS] load — 完成, 维度=%d, 向量数=%d",
            self._dimensions,
            self.count,
        )

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

        步骤:
            1. 检查索引非空
            2. query 转 numpy 并 L2 归一化
            3. index.search(query, k) → 分数 + 内部 ID
            4. 用 ID 查 metadata，组装 SearchResult

        参数:
            query_embedding: 用户问题的 embedding 向量
            top_k:           返回几条；默认读 config.retrieval_top_k

        返回:
            SearchResult 列表，按相似度从高到低
        """
        if self._index is None or self.count == 0:
            logger.warning("[FAISS] search: 索引为空")
            return []

        settings = get_settings()
        k = top_k or settings.retrieval_top_k
        fetch_k = k
        doc_filter = set(doc_ids or [])
        if doc_filter:
            factor = expand_factor or settings.rag_route_expand_factor
            fetch_k = min(k * factor, self.count)

        fetch_k = min(fetch_k, self.count)

        if len(query_embedding) != self._dimensions:
            raise ValueError(
                f"query 维度 {len(query_embedding)} != 索引维度 {self._dimensions}"
            )

        logger.info("[FAISS] search Step 1 — 查询向量维度=%d, 请求 Top-%d", len(query_embedding), fetch_k)

        # Step 2: 归一化 query
        query_vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query_vec)
        logger.info("[FAISS] search Step 2 — query 向量已 L2 归一化")

        # Step 3: FAISS 搜索 — scores[i][j] 是第 j 近邻的内积（≈余弦相似度）
        scores, indices = self._index.search(query_vec, fetch_k)
        logger.info("[FAISS] search Step 3 — FAISS 返回 scores=%s, indices=%s", scores[0].tolist(), indices[0].tolist())

        # Step 4: 组装结果（可选 doc_id 过滤）
        results: list[SearchResult] = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue

            meta = self._metadata[int(idx)]
            if doc_filter:
                chunk_doc_id = meta.get("doc_id", "")
                if chunk_doc_id not in doc_filter:
                    continue

            chunk = TextChunk(
                chunk_id=meta["chunk_id"],
                text=meta["text"],
                source=meta["source"],
                page=meta["page"],
                char_count=meta.get("char_count", len(meta["text"])),
                doc_id=meta.get("doc_id", ""),
            )
            results.append(
                SearchResult(
                    rank=len(results) + 1,
                    score=float(score),
                    faiss_id=int(idx),
                    chunk=chunk,
                )
            )
            logger.info(
                "[FAISS] search Step 4 — #%d score=%.4f id=%d source=%s page=%d doc_id=%s text=%r",
                len(results),
                score,
                idx,
                chunk.source,
                chunk.page,
                chunk.doc_id or "-",
                chunk.text[:50],
            )
            if len(results) >= k:
                break

        logger.info("[FAISS] search 完成 — 返回 %d 条结果", len(results))
        return results

    def get_chunk_metadata(self) -> list[dict]:
        """返回 chunk metadata 副本（供 catalog 同步等用途）。"""
        return list(self._metadata)

    def assign_doc_id_to_chunks(self, indices: list[int], doc_id: str) -> None:
        for idx in indices:
            self._metadata[idx]["doc_id"] = doc_id


_stores: dict[str, FaissVectorStore] = {}


def get_rag_vector_store(user_id: str) -> FaissVectorStore:
    """按 user_id 获取 RAG FAISS 实例（每用户独立目录）。"""
    if user_id not in _stores:
        settings = get_settings()
        store_dir = Path(settings.rag_store_path) / user_id
        _stores[user_id] = FaissVectorStore(store_dir=store_dir)
    return _stores[user_id]
