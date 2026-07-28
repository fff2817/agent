"""
Long-term Memory Prompt 拼接 — Top-K 记忆 → LLM messages。

数据流:
    MemorySearchResult[] → format_memory_context() → context 字符串
                        → build_memory_messages() → messages[] → LLM
"""

from __future__ import annotations

import logging

from memory.vectorstore import MemorySearchResult

logger = logging.getLogger(__name__)

MEMORY_QA_SYSTEM_PROMPT = """你是一个具备长期记忆能力的 AI 助手。

请根据【检索到的用户长期记忆】回答用户问题，遵循以下规则：
1. 优先使用记忆中与用户问题相关的信息
2. 记忆中没有的内容不要编造；可结合通用知识补充，但要区分「已知记忆」与「推测」
3. 自然融入记忆，不要逐条复述「根据记忆1…记忆2…」
4. 若记忆与当前问题无关，可忽略记忆直接回答
"""

MEMORY_AGENT_SECTION_HEADER = (
    "\n\n## 用户长期记忆\n"
    "以下是与该用户相关的已知信息，请在回答中自然运用，不要逐条复述：\n"
)


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


def build_memory_system_section(hints: list[str]) -> str:
    """
    将长期记忆格式化为可追加到 ReAct system prompt 的段落。

    无 hints 时返回空字符串。
    """
    if not hints:
        return ""

    lines = "\n".join(f"- {hint}" for hint in hints)
    return f"{MEMORY_AGENT_SECTION_HEADER}{lines}\n"


def build_memory_messages(
    question: str,
    sources: list[MemorySearchResult],
    *,
    history: list[dict] | None = None,
) -> list[dict]:
    """
    构建长期记忆问答的完整 messages（独立 /memory/ask 链路用）。

    结构:
        system → 记忆问答规则
        history → Session 历史（可选）
        user   → 【检索到的记忆】+【用户问题】
    """
    history = history or []
    context = format_memory_context(sources)

    user_content = f"""【检索到的用户长期记忆】
{context}

【用户问题】
{question}"""

    messages: list[dict] = [{"role": "system", "content": MEMORY_QA_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
        logger.info("[MemoryPrompt] 注入 Session 历史: %d 条", len(history))
    messages.append({"role": "user", "content": user_content})

    logger.info(
        "[MemoryPrompt] messages: system + history(%d) + user(%d 字)",
        len(history),
        len(user_content),
    )
    return messages
