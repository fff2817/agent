"""
Long-term Memory 入库流水线。

    用户消息 + 助手回复
        ↓  extractor（筛选）
        ↓  embed_text（向量化，复用 rag/embedder）
        ↓  MemoryVectorStore（FAISS 持久化）

为什么放在独立 ingester 而不是 longterm_store?
    · extractor / embedder / vectorstore 各管一层，职责清晰
    · longterm_store 作为门面，对外只暴露 save_turn / search
"""

from __future__ import annotations

import logging

from core.config import get_settings
from memory.extractor import extract_memory
from memory.types import ExtractionResult, MemoryRecord
from memory.vectorstore import MemoryVectorStore, get_memory_vector_store
from rag.embedder import embed_text

logger = logging.getLogger(__name__)

_store: MemoryVectorStore | None = None  # deprecated: use get_memory_vector_store(user_id)


def get_memory_vector_store_for_user(user_id: str) -> MemoryVectorStore:
    """兼容别名 — 请直接使用 memory.vectorstore.get_memory_vector_store。"""
    return get_memory_vector_store(user_id)


def ingest_turn(
    user_message: str,
    assistant_message: str,
    *,
    user_id: str,
    session_id: str | None = None,
    store: MemoryVectorStore | None = None,
) -> ExtractionResult:
    """
    尝试从一轮对话中提取并持久化长期记忆。

    返回:
        ExtractionResult — 无论是否入库，都带 reason 便于日志
    """
    settings = get_settings()
    vector_store = store or get_memory_vector_store(user_id)

    result = extract_memory(
        user_message,
        assistant_message,
        user_id=user_id,
        session_id=session_id,
        min_score=settings.memory_min_score,
    )

    if not result.should_save or result.record is None:
        logger.info(
            "[Ingester] 跳过入库: reason=%s score=%.2f user=%r",
            result.reason,
            result.score,
            user_message[:60],
        )
        return result

    record = result.record

    if _is_duplicate(record, vector_store, settings.memory_dedup_threshold):
        logger.info("[Ingester] 语义去重跳过: content=%r", record.content)
        return ExtractionResult(
            False,
            reason="dedup:similar_exists",
            score=result.score,
        )

    logger.info("[Ingester] Step 1 — 筛选通过: %s", record.content)
    logger.info("[Ingester] Step 2 — 生成 Embedding")

    try:
        embedding = embed_text(record.content)
    except ValueError as exc:
        logger.warning("[Ingester] Embedding 失败，跳过入库: %s", exc)
        return ExtractionResult(False, reason=f"embed_failed:{exc}", score=result.score)

    logger.info("[Ingester] Step 3 — 写入 FAISS")
    vector_store.add_memory(
        record,
        embedding,
        model=settings.embedding_model,
    )
    vector_store.save()

    logger.info("[Ingester] 入库完成: memory_id=%s", record.memory_id)
    return result


def _is_duplicate(
    record: MemoryRecord,
    store: MemoryVectorStore,
    threshold: float,
) -> bool:
    """同用户下是否已有语义极相似的记忆。"""
    if store.count == 0:
        return False

    try:
        query_vec = embed_text(record.content)
    except ValueError:
        return False

    hits = store.search(query_vec, user_id=record.user_id, top_k=1)
    if not hits:
        return False

    # search 返回的是 importance 加权分；近似比较用原始相似度
    # 加权后 score = cosine * importance，反推 cosine 上界
    best = hits[0]
    raw_similarity = best.score / max(best.record.importance, 0.01)
    return raw_similarity >= threshold
