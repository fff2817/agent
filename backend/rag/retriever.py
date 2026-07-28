"""
RAG 检索器 — 把「用户问题」变成向量，再从 FAISS 取 Top-K。

支持知识库路由：先选文档，再在选定文档的 chunk 中检索。
"""

import logging

from core.config import get_settings
from rag.catalog import get_document_catalog
from rag.embedder import embed_text
from rag.router import RoutingResult, route_documents
from rag.types import SearchResult
from rag.vectorstore import FaissVectorStore, get_rag_vector_store

logger = logging.getLogger(__name__)


def search_similar(
    query: str,
    store: FaissVectorStore | None = None,
    top_k: int | None = None,
    *,
    doc_ids: list[str] | None = None,
    expand_factor: int | None = None,
) -> list[SearchResult]:
    """
    对用户问题做 Similarity Search，返回最相关的 chunk 列表。

    doc_ids 非空时仅返回属于这些文档的 chunk（post-filter）。
    """
    settings = get_settings()
    k = top_k or settings.retrieval_top_k
    vector_store = store or FaissVectorStore()

    logger.info("[Retriever] 收到查询: %r", query[:100])
    logger.info("[Retriever] Step 1 — 问题向量化")

    query_vector = embed_text(query)

    logger.info("[Retriever] Step 2 — FAISS Top-%d 检索", k)
    results = vector_store.search(
        query_vector,
        top_k=k,
        doc_ids=doc_ids,
        expand_factor=expand_factor,
    )

    logger.info("[Retriever] 检索完成, 命中 %d 条", len(results))
    return results


def search_with_routing(
    query: str,
    *,
    user_id: str,
    store: FaissVectorStore | None = None,
    top_k: int | None = None,
    doc_ids: list[str] | None = None,
    filenames: list[str] | None = None,
    scope: str = "auto",
) -> tuple[list[SearchResult], RoutingResult]:
    """路由 + 受限检索的完整入口。"""
    vector_store = store or get_rag_vector_store(user_id)
    catalog = get_document_catalog(user_id)

    routing = route_documents(
        query,
        user_id=user_id,
        catalog=catalog,
        doc_ids=doc_ids,
        filenames=filenames,
        scope=scope,
    )

    filter_ids: list[str] | None = None
    if routing.selected_doc_ids and not routing.fallback_all:
        filter_ids = routing.selected_doc_ids

    results = search_similar(
        query,
        store=vector_store,
        top_k=top_k,
        doc_ids=filter_ids,
    )
    return results, routing
