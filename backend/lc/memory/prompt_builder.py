"""
Long-term Memory Prompt — 格式化检索结果，经 core.prompts.ChatPromptTemplate 组装。
"""

from __future__ import annotations

import logging

from lc.prompts import (
    MEMORY_AGENT_SECTION_HEADER,
    MEMORY_QA_SYSTEM_PROMPT,
    build_memory_messages as _build_memory_messages,
    build_memory_system_section,
)
from infra.memory_vectorstore import MemorySearchResult

logger = logging.getLogger(__name__)

__all__ = [
    "MEMORY_QA_SYSTEM_PROMPT",
    "MEMORY_AGENT_SECTION_HEADER",
    "format_memory_context",
    "build_memory_system_section",
    "build_memory_messages",
]


def format_memory_context(sources: list[MemorySearchResult]) -> str:
    """把 Top-K 记忆格式化为上下文字符串。"""
    if not sources:
        return "（未检索到相关长期记忆）"

    parts: list[str] = []
    for item in sources:
        record = item.record
        block = (
            f"[{item.rank}] 类型: {record.memory_type.value} | "
            f"相关度: {item.score:.4f}\n"
            f"{record.content}"
        )
        parts.append(block)
        logger.info(
            "[MemoryPrompt] #%d score=%.4f type=%s | %r",
            item.rank,
            item.score,
            record.memory_type.value,
            record.content[:50],
        )

    context = "\n\n".join(parts)
    logger.info("[MemoryPrompt] context 长度=%d", len(context))
    return context


def build_memory_messages(
    question: str,
    sources: list[MemorySearchResult],
    *,
    history: list[dict] | None = None,
) -> list[dict]:
    """
    构建长期记忆问答的完整 messages（独立 /memory/ask 链路用）。
    """
    history = history or []
    context = format_memory_context(sources)
    return _build_memory_messages(question, context, history=history)
