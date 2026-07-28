"""RAG 评估流水线 — 编排检索/回答/引用评分并持久化。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from core.config import get_settings
from eval.answer_judge import run_llm_judge
from eval.citation import evaluate_citations
from eval.retrieval_judge import evaluate_retrieval
from eval.store import get_eval_store
from eval.types import EvaluationRecord
from rag.chain import RAGResult
from rag.types import SearchResult, TextChunk

logger = logging.getLogger(__name__)


def rag_result_from_source_dicts(
    question: str,
    answer: str,
    source_dicts: list[dict],
    *,
    context: str = "",
) -> RAGResult:
    """从 API/SSE 的 sources 字典重建 RAGResult（用于流式评估）。"""
    sources: list[SearchResult] = []
    for item in source_dicts:
        faiss_id = int(item.get("faiss_id", item.get("rank", 0)))
        chunk = TextChunk(
            chunk_id=faiss_id,
            text=str(item.get("text", "")),
            source=str(item.get("source", "")),
            page=int(item.get("page", 0)),
        )
        sources.append(
            SearchResult(
                rank=int(item["rank"]),
                score=float(item["score"]),
                faiss_id=faiss_id,
                chunk=chunk,
            )
        )
    return RAGResult(
        question=question.strip(),
        answer=answer.strip(),
        sources=sources,
        context=context,
    )


def _sources_to_dicts(sources: list[SearchResult]) -> list[dict]:
    return [
        {
            "rank": s.rank,
            "score": round(s.score, 4),
            "faiss_id": s.faiss_id,
            "source": s.chunk.source,
            "page": s.chunk.page,
            "text": s.chunk.text,
        }
        for s in sources
    ]


def evaluate_rag_result(
    result: RAGResult,
    *,
    user_id: str,
    session_id: str | None = None,
    pipeline: str = "rag",
    top_k: int | None = None,
    retrieve_ms: int = 0,
    generate_ms: int = 0,
    persist: bool = True,
) -> EvaluationRecord:
    """对一次 RAG 问答执行完整评估。"""
    settings = get_settings()
    eval_start = time.perf_counter()

    answer_eval, llm_retrieval_items = run_llm_judge(
        result.question,
        result.context,
        result.answer,
    )

    retrieval = evaluate_retrieval(result.sources, llm_items=llm_retrieval_items)
    citation = evaluate_citations(result.answer, result.sources)

    eval_ms = int((time.perf_counter() - eval_start) * 1000)
    effective_top_k = top_k if top_k is not None else len(result.sources)

    record = EvaluationRecord(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        user_id=user_id,
        session_id=session_id,
        pipeline=pipeline,
        question=result.question,
        answer=result.answer,
        top_k=effective_top_k,
        model=settings.openai_model,
        embedding_model=settings.embedding_model,
        sources=_sources_to_dicts(result.sources),
        context=result.context,
        retrieval=retrieval,
        answer_eval=answer_eval,
        citation=citation,
        latency_ms={
            "retrieve": retrieve_ms,
            "generate": generate_ms,
            "evaluate": eval_ms,
        },
    )

    if persist:
        get_eval_store().save(record)
        logger.info(
            "[Eval] 已保存评估 id=%s overall=%.2f retrieval=%s",
            record.id,
            record.answer_eval.overall_score,
            record.retrieval.hit_quality,
        )

    return record
