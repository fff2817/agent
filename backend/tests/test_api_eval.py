"""RAG 评估 API 集成测试。"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from eval.types import AnswerEvaluation, CitationEvaluation, EvaluationRecord, RetrievalEvaluation


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("CONVERSATIONS_DB_PATH", str(tmp_path / "conversations.db"))
    monkeypatch.setenv("EVAL_DB_PATH", str(tmp_path / "evaluations.db"))
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag"))
    monkeypatch.setenv("MEMORY_STORE_PATH", str(tmp_path / "memory"))

    from core.config import get_settings

    get_settings.cache_clear()

    from conversation.store import reset_conversation_store

    reset_conversation_store()

    from main import app

    yield TestClient(app)

    reset_conversation_store()
    get_settings.cache_clear()

    get_settings.cache_clear()


def _mock_record(user_id: str) -> EvaluationRecord:
    return EvaluationRecord(
        id=str(uuid.uuid4()),
        created_at="2026-01-01T00:00:00+00:00",
        user_id=user_id,
        session_id="s1",
        pipeline="rag",
        question="测试问题",
        answer="测试回答",
        top_k=1,
        model="test-model",
        embedding_model="emb",
        sources=[],
        context="",
        retrieval=RetrievalEvaluation(top_k=1, hit_quality="good", context_precision=1.0),
        answer_eval=AnswerEvaluation(
            faithfulness=0.9,
            answer_relevance=0.9,
            completeness=0.8,
            overall_score=0.87,
            verdict="good",
        ),
        citation=CitationEvaluation(citation_coverage=0.5),
        latency_ms={"evaluate": 10},
    )


def test_list_evaluations_empty(client: TestClient):
    resp = client.get("/rag/evaluations")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("api.rag.evaluate_rag_result")
@patch("api.rag.rag_ask")
def test_rag_ask_returns_evaluation(mock_rag_ask, mock_eval, client: TestClient):
    from lc.rag.chain import RAGResult
    from lc.rag.types import SearchResult, TextChunk

    mock_rag_ask.return_value = RAGResult(
        question="Q",
        answer="A",
        sources=[
            SearchResult(
                rank=1,
                score=0.9,
                faiss_id=1,
                chunk=TextChunk(chunk_id=1, text="chunk", source="f.pdf", page=1),
            )
        ],
        context="ctx",
    )
    record = _mock_record("dev-default")

    def _eval_side_effect(result, **kwargs):
        user_id = kwargs.get("user_id", "dev-default")
        record.user_id = user_id
        from eval.store import get_eval_store

        get_eval_store().save(record)
        return record

    mock_eval.side_effect = _eval_side_effect

    resp = client.post("/rag/ask", json={"question": "Q", "evaluate": True})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["evaluation"]["evaluation_id"] == record.id

    detail_resp = client.get(f"/rag/evaluations/{record.id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["question"] == "测试问题"
