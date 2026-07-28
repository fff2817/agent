"""RAG 评估数据类型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RetrievalItemEval:
    rank: int
    faiss_id: int
    vector_score: float
    relevance_score: float
    relevance_label: str
    source: str = ""
    page: int = 0
    text_preview: str = ""
    reason: str = ""


@dataclass
class RetrievalEvaluation:
    top_k: int
    items: list[RetrievalItemEval] = field(default_factory=list)
    avg_vector_score: float = 0.0
    avg_relevance_score: float = 0.0
    context_precision: float = 0.0
    hit_quality: str = "poor"


@dataclass
class AnswerEvaluation:
    faithfulness: float = 0.0
    answer_relevance: float = 0.0
    completeness: float = 0.0
    overall_score: float = 0.0
    verdict: str = "acceptable"
    issues: list[str] = field(default_factory=list)
    judge_model: str = ""


@dataclass
class CitationItem:
    rank: int
    cited: bool
    source: str = ""
    page: int = 0
    excerpt: str = ""


@dataclass
class CitationEvaluation:
    cited_source_ranks: list[int] = field(default_factory=list)
    items: list[CitationItem] = field(default_factory=list)
    citation_coverage: float = 0.0


@dataclass
class EvaluationRecord:
    id: str
    created_at: str
    user_id: str
    session_id: str | None
    pipeline: str
    question: str
    answer: str
    top_k: int
    model: str
    embedding_model: str
    sources: list[dict]
    context: str
    retrieval: RetrievalEvaluation
    answer_eval: AnswerEvaluation
    citation: CitationEvaluation
    latency_ms: dict[str, int] = field(default_factory=dict)
    eval_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def relevance_label_from_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.3:
        return "low"
    return "irrelevant"


def hit_quality_from_precision(precision: float) -> str:
    if precision >= 0.6:
        return "good"
    if precision >= 0.3:
        return "fair"
    return "poor"
