"""
list_documents 工具 — 列出当前用户知识库中的文档目录。

使用 LangChain @tool，供 Agent 自动 Function Calling。
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from auth.context import get_current_user_id
from infra.catalog import ensure_catalog_synced, get_document_catalog

logger = logging.getLogger(__name__)


def _list_documents_impl() -> str:
    user_id = get_current_user_id()
    if not user_id:
        return "Error: 未识别用户身份，无法列出文档。"

    ensure_catalog_synced(user_id)
    catalog = get_document_catalog(user_id)
    briefs = catalog.list_briefs()

    if not briefs:
        logger.info("[Tool] list_documents: 知识库为空 user=%s", user_id)
        return "知识库中暂无已入库文档。请先在页面上传文件。"

    lines = [f"共 {len(briefs)} 份文档："]
    for item in briefs:
        lines.append(item.format_line())
        lines.append(f"    摘要: {item.one_line}")
    return "\n".join(lines)


@tool
def list_documents() -> str:
    """列出当前用户已上传并入库的知识库文档。当用户询问有哪些文档、需要对比多份文件、或需确认文件名再检索时使用。"""
    return _list_documents_impl()


def run_list_documents() -> str:
    """兼容旧调用名。"""
    return list_documents.invoke({})
