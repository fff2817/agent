"""
知识库文档路由 — 根据用户问题选择应检索的文件。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from core.config import get_settings
from infra.catalog import DocumentCatalog, DocumentRecord, ensure_catalog_synced, get_document_catalog
from lc.llm.embeddings import embed_text

logger = logging.getLogger(__name__)

_FILENAME_HINT = re.compile(
    r"(《(.+?)》|「(.+?)」|\"(.+?)\"|'(.+?)'|([\w\u4e00-\u9fff\-_.]+\.(?:pdf|docx|md|txt|markdown)))",
    re.I,
)


@dataclass
class RoutingResult:
    """文档路由决策。"""

    selected_doc_ids: list[str]
    scores: dict[str, float] = field(default_factory=dict)
    method: str = "none"
    reason: str = ""
    fallback_all: bool = False


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_boost(query: str, record: DocumentRecord) -> float:
    q = query.lower()
    boost = 0.0
    for kw in record.keywords:
        if kw.lower() in q or q in kw.lower():
            boost += 0.08
    for topic in record.topics:
        if topic.lower() in q or q in topic.lower():
            boost += 0.06
    stem = record.filename.rsplit(".", 1)[0].lower()
    if stem and stem in q:
        boost += 0.12
    if record.doc_type == "requirements" and re.search(r"需求|总结|项目", q):
        boost += 0.15
    if record.doc_type == "notes" and re.search(r"讲|介绍|是什么|原理", q):
        boost += 0.05
    return min(boost, 0.35)


def _filename_hints_in_query(query: str, catalog: DocumentCatalog) -> list[str]:
    hinted: list[str] = []
    for match in _FILENAME_HINT.finditer(query):
        for group in match.groups():
            if not group:
                continue
            record = catalog.get_by_filename(group) or catalog.get_by_filename(
                group if "." in group else f"{group}.md"
            )
            if record and record.doc_id not in hinted:
                hinted.append(record.doc_id)
    return hinted


def route_documents(
    query: str,
    *,
    user_id: str,
    catalog: DocumentCatalog | None = None,
    doc_ids: list[str] | None = None,
    filenames: list[str] | None = None,
    scope: str = "auto",
) -> RoutingResult:
    """
    阶段 A：选择应检索的 doc_id 集合。

    scope:
        auto — 自动路由（默认）
        all  — 跳过路由，全库检索
    """
    settings = get_settings()
    text = query.strip()
    catalog = catalog or get_document_catalog(user_id)
    ensure_catalog_synced(user_id)
    ready = catalog.list_ready()

    if scope == "all":
        return RoutingResult(
            selected_doc_ids=[],
            method="all",
            reason="scope=all",
            fallback_all=True,
        )

    if doc_ids:
        valid = [d for d in doc_ids if catalog.get(d) and catalog.get(d).status == "ready"]
        if valid:
            return RoutingResult(
                selected_doc_ids=valid,
                method="explicit_doc_ids",
                reason=f"agent specified {len(valid)} doc(s)",
            )

    if filenames:
        resolved = catalog.resolve_filenames(filenames)
        if resolved:
            return RoutingResult(
                selected_doc_ids=resolved,
                method="explicit_filenames",
                reason=f"matched filenames: {filenames}",
            )

    if not settings.rag_route_enabled or not ready:
        return RoutingResult(
            selected_doc_ids=[],
            method="disabled_or_empty",
            reason="routing disabled or empty catalog",
            fallback_all=True,
        )

    if len(ready) == 1:
        doc = ready[0]
        return RoutingResult(
            selected_doc_ids=[doc.doc_id],
            scores={doc.doc_id: 1.0},
            method="single_doc",
            reason=f"only one document: {doc.filename}",
        )

    hinted = _filename_hints_in_query(text, catalog)
    if hinted:
        return RoutingResult(
            selected_doc_ids=hinted[: settings.rag_max_route_docs],
            method="filename_hint",
            reason="filename mentioned in query",
        )

    query_vec = embed_text(text)
    scored: list[tuple[str, float]] = []

    for record in ready:
        if not record.summary_embedding:
            continue
        base = _cosine_similarity(query_vec, record.summary_embedding)
        base += _keyword_boost(text, record)
        scored.append((record.doc_id, base))

    if not scored:
        logger.warning("[Router] 无 summary_embedding，fallback 全库")
        return RoutingResult(
            selected_doc_ids=[],
            method="no_embeddings",
            reason="catalog missing summary embeddings",
            fallback_all=True,
        )

    scored.sort(key=lambda x: x[1], reverse=True)
    scores = {doc_id: score for doc_id, score in scored}
    top_id, top_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0

    if top_score < settings.rag_route_min_score:
        logger.info("[Router] 最高分 %.3f < 阈值，fallback 全库", top_score)
        return RoutingResult(
            selected_doc_ids=[],
            scores=scores,
            method="low_confidence",
            reason=f"top score {top_score:.3f} below threshold",
            fallback_all=True,
        )

    selected = [top_id]
    if len(scored) > 1 and (top_score - second_score) < settings.rag_route_score_delta:
        selected.append(scored[1][0])

    selected = selected[: settings.rag_max_route_docs]
    names = [catalog.get(d).filename for d in selected if catalog.get(d)]
    logger.info("[Router] 选中文档: %s (scores=%s)", names, {d: round(scores[d], 3) for d in selected})

    return RoutingResult(
        selected_doc_ids=selected,
        scores=scores,
        method="embedding_hybrid",
        reason=f"top match: {names[0] if names else top_id}",
    )
