"""
RAG Prompt 拼接 — 把 Top-K Chunk 组装成 LLM 可读的上下文。

教学要点 — 这一步做什么?

    检索到的 chunk 是「原材料」，LLM 需要的是「带指令的完整 Prompt」。

    数据流:
        Top-K SearchResult[]  →  format_context()  →  上下文字符串
                                                    →  messages[]  →  LLM

    关键原则:
        - 明确告诉 LLM「仅根据资料回答，不要编造」
        - 每条 chunk 带来源和页码，便于引用
        - 资料不足时允许 LLM 说「不知道」
"""

import logging

from rag.types import SearchResult

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """你是一个专业的文档问答助手。

请严格根据【检索到的资料】回答用户问题，遵循以下规则：
1. 只使用资料中的信息，不要编造或推测
2. 如果资料中没有相关内容，请明确说「根据现有文档，未找到相关信息」
3. 回答时可自然引用来源（如「根据员工手册第12页…」）
4. 回答要清晰、准确、面向用户
"""


def format_context(sources: list[SearchResult]) -> str:
    """
    把 Top-K 检索结果格式化为上下文字符串。

    参数:
        sources: FAISS 返回的 SearchResult 列表

    返回:
        拼接后的参考资料文本
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
    构建发给 LLM 的完整 messages 列表。

    结构:
        system  →  RAG 行为规则
        history →  Session 历史（可选）
        user    →  【检索到的资料】+【用户问题】

    参数:
        question: 用户原始问题
        sources:  Top-K 检索结果
        history:  Session 历史 messages

    返回:
        OpenAI 格式的 messages
    """
    history = history or []
    context = format_context(sources)

    user_content = f"""【检索到的资料】
{context}

【用户问题】
{question}"""

    messages: list[dict] = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
        logger.info("[PromptBuilder] 注入 Session 历史: %d 条 messages", len(history))
    messages.append({"role": "user", "content": user_content})

    logger.info(
        "[PromptBuilder] messages 构建完成: system + history(%d) + user(%d 字符)",
        len(history),
        len(user_content),
    )
    return messages
