"""
RAG Prompt 拼接 — 检索结果格式化 + 经 core.prompts.ChatPromptTemplate 组装 messages。
"""

import logging

from lc.prompts import RAG_SYSTEM_PROMPT, build_rag_messages as _build_rag_messages
from lc.rag.types import SearchResult

logger = logging.getLogger(__name__)

# 兼容旧代码: from lc.rag.prompt_builder import RAG_SYSTEM_PROMPT
__all__ = ["RAG_SYSTEM_PROMPT", "format_context", "build_rag_messages"]


def format_context(sources: list[SearchResult]) -> str:
    """
    把 Top-K 检索结果格式化为上下文字符串。
    """
    if not sources:
        logger.warning("[PromptBuilder] 无检索结果，context 为空")
        return "（未检索到任何相关文档片段）"

    parts: list[str] = []
    for item in sources:
        c = item.chunk
        block = (
            f"[{item.rank}] 来源: {c.source} 第{c.page}页 | 相似度: {item.score:.4f}\n"
            f"{c.text}"
        )
        parts.append(block)
        logger.info(
            "[PromptBuilder] 拼接 chunk #%d | score=%.4f | %s p.%d | %d字",
            item.rank,
            item.score,
            c.source,
            c.page,
            len(c.text),
        )

    context = "\n\n".join(parts)
    logger.info("[PromptBuilder] context 拼接完成, 总长度=%d 字符", len(context))
    return context


def build_rag_messages(
    question: str,
    sources: list[SearchResult],
    *,
    history: list[dict] | None = None,
) -> list[dict]:
    """
    构建发给 LLM 的完整 messages 列表（ChatPromptTemplate）。

    结构:
        system  →  RAG 行为规则
        history →  Session 历史（可选）
        user    →  【检索到的资料】+【用户问题】
    """
    history = history or []
    context = format_context(sources)
    return _build_rag_messages(question, context, history=history)
