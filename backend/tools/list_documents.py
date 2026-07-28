"""
list_documents 工具 — 列出当前用户知识库中的文档目录。
"""

import logging

from auth.context import get_current_user_id
from rag.catalog import get_document_catalog, ensure_catalog_synced

logger = logging.getLogger(__name__)

LIST_DOCUMENTS_TOOL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "list_documents",
        "description": (
            "列出当前用户已上传并入库的知识库文档。"
            "当用户询问有哪些文档、需要对比多份文件、或需确认文件名再检索时使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


def run_list_documents() -> str:
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
