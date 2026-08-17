"""
Long-term Memory 检索路由 — 判断当前问题是否需要查 FAISS。

为什么需要这一步?
    · 不是每个问题都依赖长期记忆（如「1+1」「翻译这段话」）
    · 无谓检索会多一次 Embedding API 调用，且可能注入无关 context
    · 索引为空时直接跳过，避免空跑
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from infra.memory_vectorstore import MemoryVectorStore

logger = logging.getLogger(__name__)

_SMALL_TALK = frozenset(
    {
        "你好",
        "您好",
        "hi",
        "hello",
        "谢谢",
        "感谢",
        "再见",
        "拜拜",
        "好的",
        "好",
        "嗯",
        "ok",
    }
)

_RETRIEVE_TRIGGERS = re.compile(
    r"(记得|还记得|记住过|之前|上次|我叫|我的名字|我是谁|关于我|"
    r"我的偏好|称呼我|你了解我|认识我|知道我是谁)",
    re.IGNORECASE,
)

_PERSONAL_CONTEXT = re.compile(
    r"(我的|我是|我们(公司|团队)|给我推荐|根据我的|按我的)",
    re.IGNORECASE,
)

_PURE_TASK = re.compile(
    r"^(帮?我?(算|计算|翻译|写一段|生成代码|写代码|查一下\s*\d))",
    re.IGNORECASE,
)

_PURE_MATH = re.compile(r"^[\d\s+\-*/().=？?×÷]+$")

_MATH_QUESTION = re.compile(
    r"(\d+\s*[\+\-\*/×÷]\s*\d+|等于多少|等于几|是多少|\d+\s*[加減减乘除]\s*\d+)",
    re.IGNORECASE,
)

_TEMPORAL_SKIP = re.compile(
    r"今天.{0,6}天气|^(今天|刚才|现在|此刻).{0,20}(不错|很好|有点)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RetrievalDecision:
    """是否需要检索长期记忆及其原因。"""

    should_retrieve: bool
    reason: str


def should_retrieve_memory(
    query: str,
    *,
    user_id: str,
    store: MemoryVectorStore,
) -> RetrievalDecision:
    """
    判断用户问题是否应触发长期记忆检索。

    决策顺序:
        1. 空问题 / 用户无记忆 → 不检索
        2. 寒暄 / 纯任务 / 纯算式 → 不检索
        3. 记忆相关关键词 / 个人上下文 → 检索
        4. 默认：用户有记忆且问题足够长 → 检索（由 Top-K + 分数阈值过滤噪声）
    """
    text = query.strip()
    if not text:
        return RetrievalDecision(False, "empty_query")

    if store.count_for_user(user_id) == 0:
        logger.info("[MemoryRouter] 跳过检索: user=%s 无长期记忆", user_id)
        return RetrievalDecision(False, "no_memories_for_user")

    normalized = text.lower().strip("。！？!.? ")
    if normalized in _SMALL_TALK:
        return RetrievalDecision(False, "small_talk")

    if len(text) < 4 and not _RETRIEVE_TRIGGERS.search(text):
        return RetrievalDecision(False, "too_short")

    if _PURE_MATH.match(text):
        return RetrievalDecision(False, "pure_math")

    if _MATH_QUESTION.search(text):
        return RetrievalDecision(False, "math_question")

    if _TEMPORAL_SKIP.search(text):
        return RetrievalDecision(False, "temporal_small_talk")

    if _PURE_TASK.search(text):
        return RetrievalDecision(False, "pure_task")

    if _RETRIEVE_TRIGGERS.search(text):
        logger.info("[MemoryRouter] 触发检索: memory_keywords")
        return RetrievalDecision(True, "trigger:memory_keywords")

    if _PERSONAL_CONTEXT.search(text):
        logger.info("[MemoryRouter] 触发检索: personal_context")
        return RetrievalDecision(True, "trigger:personal_context")

    logger.info("[MemoryRouter] 默认检索: user_has_memories")
    return RetrievalDecision(True, "default:user_has_memories")
