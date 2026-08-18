"""
RAG 完整链路 — 从用户问题到 LLM 回答。

完整数据流:

    用户问题
        ↓  [Step 1] 接收问题
    Embedding（问题向量化）
        ↓  [Step 2] embed_text()
    Chroma Search（相似度检索）
        ↓  [Step 3] vectorstore.search()
    Top-K Chunk（最相关的文档片段）
        ↓  [Step 4] SearchResult[]
    Prompt 拼接（资料 + 问题 → messages）
        ↓  [Step 5] build_rag_messages()
    LLM 回答（基于资料生成最终回复）
        ↓  [Step 6] chat_completion()
    返回 RAGResult
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from lc.llm.chat import chat_completion, stream_text_completion
from lc.rag.prompt_builder import build_rag_messages
from lc.rag.retriever import search_with_routing
from lc.rag.router import RoutingResult
from lc.rag.types import SearchResult
from infra.rag_vectorstore import RagVectorStore, get_rag_vector_store

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    """
    RAG 问答完整结果 — 包含答案、引用来源、使用的上下文。

    属性:
        question:        用户原始问题
        answer:          LLM 最终回答
        sources:         Top-K 检索结果（含 score、chunk、页码）
        context:         拼接后注入 LLM 的参考资料文本
        messages:        发给 LLM 的完整 messages（调试用）
    """

    question: str
    answer: str
    sources: list[SearchResult] = field(default_factory=list)
    context: str = ""
    messages: list[dict] = field(default_factory=list)
    routing: RoutingResult | None = None


def rag_ask(
    question: str,
    *,
    user_id: str,
    store: RagVectorStore | None = None,
    top_k: int | None = None,
    history: list[dict] | None = None,
) -> RAGResult:
    """
    执行完整 RAG 流程: 问题 → 检索 → Prompt → LLM → 回答。

    参数:
        question: 用户自然语言问题
        store:    Chroma 向量库；None 则加载默认路径
        top_k:    检索条数
        history:  Session 历史 messages

    返回:
        RAGResult — 含 answer、sources、context

    异常:
        ValueError: API Key 未配置 / 索引为空 / LLM 返回空
    """
    question = question.strip()
    if not question:
        raise ValueError("问题不能为空")

    history = history or []
    sources, messages, context, routing = _prepare_rag_messages(
        question,
        user_id=user_id,
        store=store,
        top_k=top_k,
        history=history,
    )

    # ------------------------------------------------------------------
    # Step 6: LLM 回答
    # 作用: LLM 阅读资料和问题，生成基于事实的回答（而非凭空编造）
    # ------------------------------------------------------------------
    logger.info("[RAG] Step 6 — LLM 回答: 调用 chat_completion（无 tools）")

    response = chat_completion(messages, tools=None)
    answer = (response.content or "").strip()

    if not answer:
        raise ValueError("LLM returned an empty answer")

    logger.info("[RAG] Step 6 — LLM 回答完成, 长度=%d", len(answer))
    logger.info("[RAG] ========== RAG 流程结束 ==========")
    logger.info("[RAG] 最终回答: %s", answer[:200])

    return RAGResult(
        question=question,
        answer=answer,
        sources=sources,
        context=context,
        messages=messages,
        routing=routing,
    )


def _sources_to_dicts(sources: list[SearchResult]) -> list[dict]:
    return [
        {
            "rank": s.rank,
            "score": round(s.score, 4),
            "source": s.chunk.source,
            "page": s.chunk.page,
            "text": s.chunk.text,
        }
        for s in sources
    ]


def _prepare_rag_messages(
    question: str,
    *,
    user_id: str,
    store: RagVectorStore | None = None,
    top_k: int | None = None,
    history: list[dict] | None = None,
) -> tuple[list[SearchResult], list[dict], str, RoutingResult]:
    """RAG 检索 + Prompt 拼接，供同步/流式共用。"""
    question = question.strip()
    if not question:
        raise ValueError("问题不能为空")

    history = history or []
    vector_store = store or get_rag_vector_store(user_id)

    logger.info("[RAG] ========== 开始 RAG 流程 ==========")
    logger.info("[RAG] Step 1 — 用户问题: %s", question)
    if history:
        logger.info("[RAG] 注入 Session 历史: %d 条 messages", len(history))

    if vector_store.count == 0:
        raise ValueError(
            "向量库为空，请先入库文档。运行: python -m rag.demo_rag --ingest"
        )

    logger.info("[RAG] Step 2 — Embedding: 问题向量化")
    logger.info("[RAG] Step 3 — 文档路由 + Chroma Search")

    sources, routing = search_with_routing(
        question,
        user_id=user_id,
        store=vector_store,
        top_k=top_k,
    )
    if routing.selected_doc_ids and not routing.fallback_all:
        logger.info("[RAG] 路由选中 doc_ids=%s method=%s", routing.selected_doc_ids, routing.method)
    else:
        logger.info("[RAG] 路由 fallback 全库: %s", routing.reason)

    logger.info("[RAG] Step 4 — Top-K Chunk: 命中 %d 条", len(sources))
    for s in sources:
        logger.info(
            "[RAG]   #%d score=%.4f | %s p.%d | %r",
            s.rank,
            s.score,
            s.chunk.source,
            s.chunk.page,
            s.chunk.text[:60],
        )

    logger.info("[RAG] Step 5 — Prompt 拼接: 资料 + 问题 → messages")
    messages = build_rag_messages(question, sources, history=history)
    context = messages[-1]["content"] if messages else ""

    return sources, messages, context, routing


def rag_ask_stream(
    question: str,
    *,
    user_id: str,
    store: RagVectorStore | None = None,
    top_k: int | None = None,
    history: list[dict] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[dict]:
    """
    流式 RAG 问答 — 检索完成后逐 token 推送 LLM 回答。

    事件:
      - context: 检索到的 sources + context_preview
      - token:   回答文本片段
      - done:    完整 RAGResult 字段
      - cancelled: 用户中断（含 partial answer）
    """
    sources, messages, context, routing = _prepare_rag_messages(
        question,
        user_id=user_id,
        store=store,
        top_k=top_k,
        history=history,
    )

    yield {
        "type": "context",
        "sources": _sources_to_dicts(sources),
        "context_preview": context[:500] if context else "",
        "routing": {
            "method": routing.method,
            "reason": routing.reason,
            "selected_doc_ids": routing.selected_doc_ids,
            "fallback_all": routing.fallback_all,
        },
    }

    logger.info("[RAG] Step 6 — LLM 流式回答")
    answer_parts: list[str] = []

    try:
        for token in stream_text_completion(messages, should_cancel=should_cancel):
            answer_parts.append(token)
            yield {"type": "token", "content": token}
    except Exception:
        partial = "".join(answer_parts).strip()
        if partial and should_cancel and should_cancel():
            yield {"type": "cancelled", "answer": partial, "question": question.strip()}
            return
        raise

    if should_cancel and should_cancel():
        partial = "".join(answer_parts).strip()
        yield {"type": "cancelled", "answer": partial, "question": question.strip()}
        return

    answer = "".join(answer_parts).strip()
    if not answer:
        raise ValueError("LLM returned an empty answer")

    logger.info("[RAG] Step 6 — 流式回答完成, 长度=%d", len(answer))
    logger.info("[RAG] ========== RAG 流程结束 ==========")

    yield {
        "type": "done",
        "question": question.strip(),
        "answer": answer,
        "sources": _sources_to_dicts(sources),
        "context_preview": context[:500] if context else "",
    }
