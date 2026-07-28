"""评估结果 SQLite 持久化。"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from core.config import get_settings
from eval.types import (
    AnswerEvaluation,
    CitationEvaluation,
    CitationItem,
    EvaluationRecord,
    RetrievalEvaluation,
    RetrievalItemEval,
)

logger = logging.getLogger(__name__)

_eval_store: "EvalStore | None" = None


class EvalStore:
    """RAG 评估记录存储。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.eval_db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_evaluations (
                    id              TEXT PRIMARY KEY,
                    user_id         TEXT NOT NULL,
                    session_id      TEXT,
                    pipeline        TEXT NOT NULL,
                    question        TEXT NOT NULL,
                    answer          TEXT NOT NULL,
                    overall_score   REAL NOT NULL,
                    hit_quality     TEXT NOT NULL,
                    record_json     TEXT NOT NULL,
                    created_at      TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eval_user ON rag_evaluations(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eval_created ON rag_evaluations(created_at)"
            )

    def save(self, record: EvaluationRecord) -> None:
        payload = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_evaluations (
                    id, user_id, session_id, pipeline, question, answer,
                    overall_score, hit_quality, record_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.session_id,
                    record.pipeline,
                    record.question,
                    record.answer,
                    record.answer_eval.overall_score,
                    record.retrieval.hit_quality,
                    payload,
                    record.created_at,
                ),
            )

    def get(self, eval_id: str, *, user_id: str | None = None) -> EvaluationRecord | None:
        with self._connect() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT record_json FROM rag_evaluations WHERE id = ? AND user_id = ?",
                    (eval_id, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT record_json FROM rag_evaluations WHERE id = ?",
                    (eval_id,),
                ).fetchone()
        if not row:
            return None
        return _record_from_dict(json.loads(row["record_json"]))

    def list_records(
        self,
        *,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, question, answer, overall_score, hit_quality,
                       pipeline, session_id, created_at
                FROM rag_evaluations
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self, *, user_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    AVG(overall_score) AS avg_overall,
                    SUM(CASE WHEN overall_score < 0.5 THEN 1 ELSE 0 END) AS low_score_count,
                    SUM(CASE WHEN hit_quality = 'poor' THEN 1 ELSE 0 END) AS poor_retrieval_count
                FROM rag_evaluations
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        total = int(row["total"] or 0)
        return {
            "total": total,
            "avg_overall_score": round(float(row["avg_overall"] or 0), 4),
            "low_score_rate": round((row["low_score_count"] or 0) / total, 4) if total else 0.0,
            "poor_retrieval_rate": round((row["poor_retrieval_count"] or 0) / total, 4) if total else 0.0,
        }


def _record_from_dict(data: dict) -> EvaluationRecord:
    retrieval_data = data["retrieval"]
    answer_data = data["answer_eval"]
    citation_data = data["citation"]

    return EvaluationRecord(
        id=data["id"],
        created_at=data["created_at"],
        user_id=data["user_id"],
        session_id=data.get("session_id"),
        pipeline=data["pipeline"],
        question=data["question"],
        answer=data["answer"],
        top_k=data["top_k"],
        model=data["model"],
        embedding_model=data.get("embedding_model", ""),
        sources=data.get("sources", []),
        context=data.get("context", ""),
        retrieval=RetrievalEvaluation(
            top_k=retrieval_data["top_k"],
            items=[RetrievalItemEval(**item) for item in retrieval_data.get("items", [])],
            avg_vector_score=retrieval_data.get("avg_vector_score", 0),
            avg_relevance_score=retrieval_data.get("avg_relevance_score", 0),
            context_precision=retrieval_data.get("context_precision", 0),
            hit_quality=retrieval_data.get("hit_quality", "poor"),
        ),
        answer_eval=AnswerEvaluation(**answer_data),
        citation=CitationEvaluation(
            cited_source_ranks=citation_data.get("cited_source_ranks", []),
            items=[CitationItem(**item) for item in citation_data.get("items", [])],
            citation_coverage=citation_data.get("citation_coverage", 0),
        ),
        latency_ms=data.get("latency_ms", {}),
        eval_version=data.get("eval_version", "1.0"),
    )


def get_eval_store() -> EvalStore:
    global _eval_store
    if _eval_store is None:
        _eval_store = EvalStore()
    return _eval_store


def reset_eval_store(store: EvalStore | None = None) -> None:
    global _eval_store
    _eval_store = store
