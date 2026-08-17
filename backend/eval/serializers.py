"""评估结果序列化 — EvaluationRecord ↔ API Schema。"""

from __future__ import annotations

from eval.types import EvaluationRecord
from models.schemas import (
    AnswerEvalSchema,
    CitationEvalSchema,
    CitationItemSchema,
    RAGEvaluationDetailSchema,
    RAGEvaluationSummarySchema,
    RAGSourceSchema,
    RetrievalEvalSchema,
    RetrievalItemEvalSchema,
)
from lc.rag.chain import RAGResult


def _merge_sources_with_retrieval(record: EvaluationRecord) -> list[RAGSourceSchema]:
    retrieval_by_rank = {item.rank: item for item in record.retrieval.items}
    sources: list[RAGSourceSchema] = []
    for src in record.sources:
        rank = int(src["rank"])
        item = retrieval_by_rank.get(rank)
        sources.append(
            RAGSourceSchema(
                rank=rank,
                score=float(src["score"]),
                source=str(src["source"]),
                page=int(src["page"]),
                text=str(src["text"]),
                relevance_score=item.relevance_score if item else None,
                relevance_label=item.relevance_label if item else None,
            )
        )
    return sources


def record_to_summary(record: EvaluationRecord) -> RAGEvaluationSummarySchema:
    return RAGEvaluationSummarySchema(
        evaluation_id=record.id,
        retrieval=RetrievalEvalSchema(
            top_k=record.retrieval.top_k,
            items=[RetrievalItemEvalSchema(**item.__dict__) for item in record.retrieval.items],
            avg_vector_score=record.retrieval.avg_vector_score,
            avg_relevance_score=record.retrieval.avg_relevance_score,
            context_precision=record.retrieval.context_precision,
            hit_quality=record.retrieval.hit_quality,
        ),
        answer=AnswerEvalSchema(
            faithfulness=record.answer_eval.faithfulness,
            answer_relevance=record.answer_eval.answer_relevance,
            completeness=record.answer_eval.completeness,
            overall_score=record.answer_eval.overall_score,
            verdict=record.answer_eval.verdict,
            issues=record.answer_eval.issues,
            judge_model=record.answer_eval.judge_model,
        ),
        citation=CitationEvalSchema(
            cited_source_ranks=record.citation.cited_source_ranks,
            items=[CitationItemSchema(**item.__dict__) for item in record.citation.items],
            citation_coverage=record.citation.citation_coverage,
        ),
        latency_ms=record.latency_ms,
    )


def record_to_detail(record: EvaluationRecord) -> RAGEvaluationDetailSchema:
    return RAGEvaluationDetailSchema(
        id=record.id,
        created_at=record.created_at,
        user_id=record.user_id,
        session_id=record.session_id,
        pipeline=record.pipeline,
        question=record.question,
        answer=record.answer,
        top_k=record.top_k,
        model=record.model,
        embedding_model=record.embedding_model,
        sources=_merge_sources_with_retrieval(record),
        context_preview=record.context[:500] if record.context else "",
        retrieval=RetrievalEvalSchema(
            top_k=record.retrieval.top_k,
            items=[RetrievalItemEvalSchema(**item.__dict__) for item in record.retrieval.items],
            avg_vector_score=record.retrieval.avg_vector_score,
            avg_relevance_score=record.retrieval.avg_relevance_score,
            context_precision=record.retrieval.context_precision,
            hit_quality=record.retrieval.hit_quality,
        ),
        answer_eval=AnswerEvalSchema(
            faithfulness=record.answer_eval.faithfulness,
            answer_relevance=record.answer_eval.answer_relevance,
            completeness=record.answer_eval.completeness,
            overall_score=record.answer_eval.overall_score,
            verdict=record.answer_eval.verdict,
            issues=record.answer_eval.issues,
            judge_model=record.answer_eval.judge_model,
        ),
        citation=CitationEvalSchema(
            cited_source_ranks=record.citation.cited_source_ranks,
            items=[CitationItemSchema(**item.__dict__) for item in record.citation.items],
            citation_coverage=record.citation.citation_coverage,
        ),
        latency_ms=record.latency_ms,
        eval_version=record.eval_version,
    )


def sources_for_response(
    result: RAGResult,
    record: EvaluationRecord | None = None,
) -> list[RAGSourceSchema]:
    retrieval_by_rank = {}
    if record:
        retrieval_by_rank = {item.rank: item for item in record.retrieval.items}
    return [
        RAGSourceSchema(
            rank=s.rank,
            score=s.score,
            source=s.chunk.source,
            page=s.chunk.page,
            text=s.chunk.text,
            relevance_score=retrieval_by_rank[s.rank].relevance_score
            if s.rank in retrieval_by_rank
            else None,
            relevance_label=retrieval_by_rank[s.rank].relevance_label
            if s.rank in retrieval_by_rank
            else None,
        )
        for s in result.sources
    ]
