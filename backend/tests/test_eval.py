"""RAG 评估单元测试 — 检索评分、引用、存储。"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.citation import evaluate_citations, extract_cited_ranks
from eval.retrieval_judge import evaluate_retrieval
from eval.store import EvalStore, reset_eval_store
from eval.types import AnswerEvaluation, CitationEvaluation, EvaluationRecord, RetrievalEvaluation
from lc.rag.types import SearchResult, TextChunk


def _chunk(text: str, *, rank: int = 1, score: float = 0.8) -> SearchResult:
    return SearchResult(
        rank=rank,
        score=score,
        faiss_id=rank,
        chunk=TextChunk(chunk_id=rank, text=text, source="doc.pdf", page=rank),
    )


def test_extract_cited_ranks():
    assert extract_cited_ranks("流程见手册 [1]，时限见 [2]。") == [1, 2]


def test_evaluate_retrieval_vector_only():
    sources = [
        _chunk("报销流程说明", rank=1, score=0.82),
        _chunk("无关内容", rank=2, score=0.35),
    ]
    result = evaluate_retrieval(sources)
    assert result.top_k == 2
    assert result.items[0].relevance_label == "high"
    assert result.items[1].relevance_label == "low"
    assert result.context_precision == 0.5


def test_evaluate_citations_explicit():
    sources = [_chunk("报销需填表", rank=1), _chunk("主管审批", rank=2)]
    citation = evaluate_citations("请先填表 [1]，再审批 [2]。", sources)
    assert citation.cited_source_ranks == [1, 2]
    assert citation.citation_coverage == 1.0


def test_eval_store_save_and_get(tmp_path: Path):
    store = EvalStore(db_path=tmp_path / "eval.db")
    reset_eval_store(store)

    record = EvaluationRecord(
        id="eval-1",
        created_at="2026-01-01T00:00:00+00:00",
        user_id="user-a",
        session_id="sess-1",
        pipeline="rag",
        question="q",
        answer="a",
        top_k=1,
        model="test",
        embedding_model="emb",
        sources=[],
        context="ctx",
        retrieval=RetrievalEvaluation(top_k=0),
        answer_eval=AnswerEvaluation(overall_score=0.9, verdict="good"),
        citation=CitationEvaluation(),
    )
    store.save(record)

    loaded = store.get("eval-1", user_id="user-a")
    assert loaded is not None
    assert loaded.answer_eval.overall_score == 0.9

    stats = store.stats(user_id="user-a")
    assert stats["total"] == 1

    reset_eval_store(None)
