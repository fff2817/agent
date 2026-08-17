"""
Long-term Memory 检索器 — query → Embedding → FAISS Top-K。

与 rag/retriever.py 同构，但:
    · 索引路径不同（memory/store）
    · 检索结果按 user_id 过滤
"""

from __future__ import annotations

import logging

from core.config import get_settings
from infra.memory_vectorstore import MemorySearchResult, MemoryVectorStore, get_memory_vector_store
from lc.llm.embeddings import embed_text

logger = logging.getLogger(__name__)


def retrieve_memories(
    query: str,
    *,
    user_id: str,
    store: MemoryVectorStore | None = None,
    top_k: int | None = None,
) -> list[MemorySearchResult]:
    """
    按用户与问题检索相关长期记忆。

    返回:
        MemorySearchResult 列表，按加权相似度降序
    """
    query = query.strip()
    if not query:
        return []

    settings = get_settings()
    k = top_k or settings.memory_top_k
    vector_store = store or get_memory_vector_store(user_id)

    if vector_store.count == 0:
        logger.info("[MemoryRetriever] 索引为空")
        return []

    logger.info("[MemoryRetriever] query=%r user_id=%s", query[:80], user_id)
    query_vector = embed_text(query)
    results = vector_store.search(
        query_vector,
        user_id=user_id,
        top_k=k,
    )
    logger.info("[MemoryRetriever] 命中 %d 条", len(results))
    return results
