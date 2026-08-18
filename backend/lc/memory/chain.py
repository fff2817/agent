"""
Long-term Memory 完整检索链路 — 对标 rag/chain.py。

完整数据流:

    用户提问
        ↓  [Step 1] should_retrieve_memory() — 是否需要检索
    Embedding（问题向量化）
        ↓  [Step 2] embed_text()
    Chroma Search（相似度检索）
        ↓  [Step 3] MemoryVectorStore.search() → Top-K
    Prompt 拼接
        ↓  [Step 4] build_memory_messages() / build_memory_system_section()
    LLM 回答（memory_ask 路径）
        ↓  [Step 5] chat_completion()
    返回 MemoryRetrievalResult / MemoryAskResult
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from core.config import get_settings
from lc.llm.chat import chat_completion, stream_text_completion
from lc.memory.prompt_builder import (
    build_memory_messages,
    build_memory_system_section,
    format_memory_context,
)
from lc.memory.router import should_retrieve_memory
from infra.memory_vectorstore import MemorySearchResult, MemoryVectorStore, get_memory_vector_store
from lc.llm.embeddings import embed_text

logger = logging.getLogger(__name__)


@dataclass
class MemoryRetrievalResult:
    """
    长期记忆检索结果 — 不含 LLM 生成（供 Agent 注入用）。

    属性:
        question:         用户原始问题
        should_retrieve:  是否执行了检索
        skip_reason:      跳过检索的原因（should_retrieve=False 时有值）
        memories:         Top-K 检索结果
        hints:            注入 Prompt 的记忆文本列表
        context:          格式化后的记忆上下文
    """

    question: str
    should_retrieve: bool
    skip_reason: str = ""
    memories: list[MemorySearchResult] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    context: str = ""


@dataclass
class MemoryAskResult:
    """长期记忆问答完整结果 — 含 LLM 最终回答。"""

    question: str
    answer: str
    should_retrieve: bool
    skip_reason: str = ""
    memories: list[MemorySearchResult] = field(default_factory=list)
    context: str = ""
    messages: list[dict] = field(default_factory=list)


def _filter_by_min_score(
    results: list[MemorySearchResult],
    min_score: float,
) -> list[MemorySearchResult]:
    filtered = [r for r in results if r.score >= min_score]
    for rank, item in enumerate(filtered, start=1):
        item.rank = rank
    return filtered


def retrieve_memories_for_question(
    question: str,
    *,
    user_id: str,
    store: MemoryVectorStore | None = None,
    top_k: int | None = None,
) -> MemoryRetrievalResult:
    """
    执行长期记忆检索（Step 1~4 的前半段，不含 LLM）。

    供 /chat Agent 路径使用：返回 hints 注入 ReAct system prompt。
    """
    question = question.strip()
    if not question:
        return MemoryRetrievalResult(
            question=question,
            should_retrieve=False,
            skip_reason="empty_query",
        )

    settings = get_settings()
    vector_store = store or get_memory_vector_store(user_id)

    logger.info("[MemoryChain] ========== 开始记忆检索 ==========")
    logger.info("[MemoryChain] Step 1 — 判断是否需要检索: %s", question[:100])

    decision = should_retrieve_memory(question, user_id=user_id, store=vector_store)
    if not decision.should_retrieve:
        logger.info("[MemoryChain] 跳过检索: reason=%s", decision.reason)
        return MemoryRetrievalResult(
            question=question,
            should_retrieve=False,
            skip_reason=decision.reason,
        )

    logger.info("[MemoryChain] Step 2 — Embedding: 问题向量化")
    logger.info("[MemoryChain] Step 3 — Chroma Search: Top-K 检索")

    k = top_k or settings.memory_top_k
    query_vector = embed_text(question)
    raw_results = vector_store.search(query_vector, user_id=user_id, top_k=k)
    memories = _filter_by_min_score(raw_results, settings.memory_min_retrieval_score)

    logger.info(
        "[MemoryChain] Step 3 — 命中 %d 条 (阈值=%.2f)",
        len(memories),
        settings.memory_min_retrieval_score,
    )
    for item in memories:
        logger.info(
            "[MemoryChain]   #%d score=%.4f type=%s | %r",
            item.rank,
            item.score,
            item.record.memory_type.value,
            item.record.content[:60],
        )

    hints = [m.record.content for m in memories]
    context = format_memory_context(memories)

    logger.info("[MemoryChain] Step 4 — Prompt 片段就绪: %d 条 hints", len(hints))
    logger.info("[MemoryChain] ========== 记忆检索结束 ==========")

    return MemoryRetrievalResult(
        question=question,
        should_retrieve=True,
        skip_reason="",
        memories=memories,
        hints=hints,
        context=context,
    )


def memory_ask(
    question: str,
    *,
    user_id: str,
    store: MemoryVectorStore | None = None,
    top_k: int | None = None,
    history: list[dict] | None = None,
) -> MemoryAskResult:
    """
    完整长期记忆问答: 检索 → Prompt → LLM → 回答。

    供 POST /memory/ask 独立 API 使用。
    """
    history = history or []

    retrieval = retrieve_memories_for_question(
        question,
        user_id=user_id,
        store=store,
        top_k=top_k,
    )

    skip_reason = retrieval.skip_reason
    if retrieval.should_retrieve and not retrieval.memories:
        skip_reason = "no_relevant_memories"
        logger.info("[MemoryChain] 检索无命中，降级为无记忆回答")
    elif not retrieval.should_retrieve:
        logger.info("[MemoryChain] 无检索，直接 LLM 回答（无记忆上下文）")
    else:
        logger.info("[MemoryChain] Step 4 — Prompt 拼接: 记忆 + 问题 → messages")

    messages = _build_memory_ask_messages(question, retrieval, history)

    logger.info("[MemoryChain] Step 5 — LLM 回答")
    response = chat_completion(messages, tools=None)
    answer = (response.content or "").strip()
    if not answer:
        raise ValueError("LLM returned an empty answer")

    logger.info("[MemoryChain] Step 5 — 完成, 回答长度=%d", len(answer))
    logger.info("[MemoryChain] ========== 记忆问答结束 ==========")

    return MemoryAskResult(
        question=question,
        answer=answer,
        should_retrieve=retrieval.should_retrieve,
        skip_reason=skip_reason,
        memories=retrieval.memories,
        context=retrieval.context,
        messages=messages,
    )


def _memories_to_dicts(memories: list[MemorySearchResult]) -> list[dict]:
    return [
        {
            "rank": m.rank,
            "score": round(m.score, 4),
            "memory_type": m.record.memory_type.value,
            "content": m.record.content,
        }
        for m in memories
    ]


def _build_memory_ask_messages(
    question: str,
    retrieval: MemoryRetrievalResult,
    history: list[dict],
) -> list[dict]:
    """根据检索结果构建 LLM messages，供同步/流式共用。"""
    if not retrieval.should_retrieve:
        return [
            {"role": "system", "content": "你是一个有帮助的 AI 助手。"},
            *history,
            {"role": "user", "content": question},
        ]

    if not retrieval.memories:
        return [
            {"role": "system", "content": "你是一个有帮助的 AI 助手。"},
            *history,
            {"role": "user", "content": question},
        ]

    return build_memory_messages(question, retrieval.memories, history=history)


def memory_ask_stream(
    question: str,
    *,
    user_id: str,
    store: MemoryVectorStore | None = None,
    top_k: int | None = None,
    history: list[dict] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[dict]:
    """
    流式长期记忆问答 — 检索完成后逐 token 推送 LLM 回答。

    事件:
      - context: 检索到的 memories + should_retrieve / skip_reason
      - token:   回答文本片段
      - done:    完整结果
      - cancelled: 用户中断
    """
    history = history or []

    retrieval = retrieve_memories_for_question(
        question,
        user_id=user_id,
        store=store,
        top_k=top_k,
    )

    skip_reason = retrieval.skip_reason
    if retrieval.should_retrieve and not retrieval.memories:
        skip_reason = "no_relevant_memories"

    yield {
        "type": "context",
        "should_retrieve": retrieval.should_retrieve,
        "skip_reason": skip_reason,
        "memories": _memories_to_dicts(retrieval.memories),
        "context_preview": retrieval.context[:500] if retrieval.context else "",
    }

    messages = _build_memory_ask_messages(question, retrieval, history)

    logger.info("[MemoryChain] Step 5 — LLM 流式回答")
    answer_parts: list[str] = []

    for token in stream_text_completion(messages, should_cancel=should_cancel):
        answer_parts.append(token)
        yield {"type": "token", "content": token}

    if should_cancel and should_cancel():
        partial = "".join(answer_parts).strip()
        yield {"type": "cancelled", "answer": partial, "question": question.strip()}
        return

    answer = "".join(answer_parts).strip()
    if not answer:
        raise ValueError("LLM returned an empty answer")

    logger.info("[MemoryChain] Step 5 — 流式完成, 回答长度=%d", len(answer))
    logger.info("[MemoryChain] ========== 记忆问答结束 ==========")

    yield {
        "type": "done",
        "question": question.strip(),
        "answer": answer,
        "should_retrieve": retrieval.should_retrieve,
        "skip_reason": skip_reason,
        "memories": _memories_to_dicts(retrieval.memories),
        "context_preview": retrieval.context[:500] if retrieval.context else "",
    }


def hints_from_retrieval(result: MemoryRetrievalResult) -> list[str]:
    """从检索结果提取 Agent 可用的 hints（空则返回 []）。"""
    if not result.should_retrieve or not result.hints:
        return []
    return result.hints


def system_section_from_retrieval(result: MemoryRetrievalResult) -> str:
    """从检索结果生成可追加到 system prompt 的段落。"""
    return build_memory_system_section(result.hints)
