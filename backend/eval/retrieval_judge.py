"""检索相关性评估 — 基于向量分 + 可选 LLM 增强。"""

from __future__ import annotations

from lc.rag.types import SearchResult

from eval.types import (
    RetrievalEvaluation,
    RetrievalItemEval,
    hit_quality_from_precision,
    relevance_label_from_score,
)

RELEVANT_LABELS = frozenset({"high", "medium"})


def evaluate_retrieval(
    sources: list[SearchResult],
    *,
    llm_items: list[dict] | None = None,
) -> RetrievalEvaluation:
    """
    对 Top-K 检索结果评分。

    llm_items: Judge 返回的 per-source 结果，格式:
      [{"rank": 1, "relevant": true, "score": 0.85, "reason": "..."}]
    """
    llm_by_rank = {item["rank"]: item for item in (llm_items or [])}
    items: list[RetrievalItemEval] = []

    for source in sources:
        vector_score = round(source.score, 4)
        llm_item = llm_by_rank.get(source.rank)

        if llm_item:
            relevance_score = float(llm_item.get("score", vector_score))
            if llm_item.get("relevant") is False:
                relevance_label = "irrelevant"
            else:
                relevance_label = relevance_label_from_score(relevance_score)
            reason = str(llm_item.get("reason", ""))
        else:
            relevance_score = vector_score
            relevance_label = relevance_label_from_score(vector_score)
            reason = "基于向量相似度评分"

        items.append(
            RetrievalItemEval(
                rank=source.rank,
                faiss_id=source.faiss_id,
                vector_score=vector_score,
                relevance_score=round(relevance_score, 4),
                relevance_label=relevance_label,
                source=source.chunk.source,
                page=source.chunk.page,
                text_preview=source.chunk.text[:200],
                reason=reason,
            )
        )

    if not items:
        return RetrievalEvaluation(top_k=0, hit_quality="poor")

    avg_vector = sum(i.vector_score for i in items) / len(items)
    avg_relevance = sum(i.relevance_score for i in items) / len(items)
    relevant_count = sum(1 for i in items if i.relevance_label in RELEVANT_LABELS)
    precision = relevant_count / len(items)

    return RetrievalEvaluation(
        top_k=len(items),
        items=items,
        avg_vector_score=round(avg_vector, 4),
        avg_relevance_score=round(avg_relevance, 4),
        context_precision=round(precision, 4),
        hit_quality=hit_quality_from_precision(precision),
    )
