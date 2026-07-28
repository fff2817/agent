"""
search_docs 工具 — 带知识库路由的 RAG 检索。
"""

import logging

from auth.context import get_current_user_id
from core.config import get_settings
from rag.catalog import ensure_catalog_synced, get_document_catalog
from rag.retriever import search_with_routing
from rag.router import RoutingResult
from rag.types import SearchResult
from rag.vectorstore import get_rag_vector_store

logger = logging.getLogger(__name__)

SEARCH_DOCS_TOOL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "search_docs",
        "description": (
            "从已上传的文档知识库中检索相关内容。"
            "当用户询问文档、手册、PDF 中的信息，或需要基于资料回答时使用。"
            "系统会自动选择最相关的文件；若用户指定文件名，可传 filenames。"
            "返回最相关的文档片段（含来源和页码）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索用的自然语言问题或关键词，例如「报销流程」",
                },
                "filenames": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选，限定检索的文件名列表，如 [\"AI笔记.md\"]",
                },
                "scope": {
                    "type": "string",
                    "enum": ["auto", "all"],
                    "description": "auto=自动路由选文件（默认）；all=搜索全部文档",
                },
            },
            "required": ["query"],
        },
    },
}


def _format_routing_header(routing: RoutingResult, user_id: str) -> str:
    catalog = get_document_catalog(user_id)
    if routing.fallback_all or not routing.selected_doc_ids:
        if routing.method == "all":
            return "检索范围: 全部文档"
        return f"检索范围: 全部文档（路由: {routing.reason}）"

    names: list[str] = []
    for doc_id in routing.selected_doc_ids:
        record = catalog.get(doc_id)
        if record:
            score = routing.scores.get(doc_id)
            score_str = f", score={score:.3f}" if score is not None else ""
            names.append(f"{record.filename}{score_str}")

    joined = "、".join(names) if names else "未知"
    return f"检索范围: {joined}（{routing.reason}）"


def format_search_results(
    results: list[SearchResult],
    *,
    routing: RoutingResult | None = None,
    user_id: str = "",
) -> str:
    """把检索结果格式化为 Agent 可读的 Observation 文本。"""
    lines: list[str] = []
    if routing and user_id:
        lines.append(_format_routing_header(routing, user_id))
        lines.append("")

    if not results:
        if lines:
            lines.append("未在选定范围内找到相关文档片段。")
        else:
            return "未在知识库中找到相关文档片段。请确认已上传 PDF 且问题与文档内容相关。"
        return "\n".join(lines)

    for item in results:
        preview = item.chunk.text.strip()
        if len(preview) > 400:
            preview = preview[:400] + "..."
        lines.append(
            f"[{item.rank}] {item.chunk.source} p.{item.chunk.page} "
            f"(score={item.score:.3f}): {preview}"
        )
    return "\n\n".join(lines)


def run_search_docs(
    query: str,
    *,
    filenames: list[str] | None = None,
    scope: str = "auto",
) -> str:
    """search_docs 工具执行入口。"""
    query = query.strip()
    if not query:
        return "Error: query is empty"

    logger.info("[Tool] search_docs 检索: query=%r filenames=%s scope=%s", query, filenames, scope)

    user_id = get_current_user_id()
    if not user_id:
        return "Error: 未识别用户身份，无法检索文档。"

    ensure_catalog_synced(user_id)
    settings = get_settings()
    store = get_rag_vector_store(user_id)

    if store.count == 0:
        logger.warning("[Tool] search_docs: 向量库为空")
        return (
            "知识库为空，尚未入库任何文档。"
            "请先在页面上传 PDF，或调用 POST /rag/ingest 入库文本后再检索。"
        )

    try:
        results, routing = search_with_routing(
            query,
            user_id=user_id,
            store=store,
            top_k=settings.retrieval_top_k,
            filenames=filenames,
            scope=scope or "auto",
        )
        formatted = format_search_results(results, routing=routing, user_id=user_id)
        logger.info(
            "[Tool] search_docs 完成, 命中 %d 条, 路由=%s",
            len(results),
            routing.method,
        )
        return formatted
    except ValueError as exc:
        logger.warning("[Tool] search_docs 失败: %s", exc)
        return f"Error: search failed — {exc}"
    except Exception as exc:
        logger.exception("[Tool] search_docs 异常")
        return f"Error: search failed — {exc}"
