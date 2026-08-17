"""
RAG API — 文档问答 HTTP 接口。

POST /rag/ask         触发完整 RAG 流程（支持 Session Memory + 评估）
POST /rag/ask/stream  流式 RAG 问答（SSE）
POST /rag/ingest      文本入库
"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.context import UserContext
from auth.dependencies import get_current_user
from core.sse import create_sse_response
from eval.pipeline import evaluate_rag_result, rag_result_from_source_dicts
from eval.serializers import record_to_summary, sources_for_response
from lc.memory.conversation_memory import get_conversation_memory
from infra.session_store import SessionForbiddenError, get_session_store
from models.schemas import (
    RAGAskRequest,
    RAGAskResponse,
    RAGIngestRequest,
    RAGIngestResponse,
)
from lc.rag.chain import rag_ask, rag_ask_stream
from lc.rag.ingest import ingest_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


def _resolve_session(session_store, session_id: str | None, user_id: str):
    try:
        return session_store.get_or_create(session_id, user_id)
    except SessionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/ask", response_model=RAGAskResponse)
async def rag_ask_endpoint(
    request: RAGAskRequest,
    user: UserContext = Depends(get_current_user),
) -> RAGAskResponse:
    """RAG 文档问答 — 完整链路 HTTP 入口。"""
    session_store = get_session_store()
    conv_memory = get_conversation_memory()
    session_id, _ = _resolve_session(session_store, request.session_id, user.user_id)

    logger.info(
        "[API/RAG] 收到问题: user=%s session=%s, q=%s",
        user.user_id,
        session_id,
        request.question[:100],
    )

    history = conv_memory.load_history_for_prompt(session_id)

    try:
        t0 = time.perf_counter()
        result = rag_ask(
            request.question,
            user_id=user.user_id,
            top_k=request.top_k,
            history=history,
        )
        generate_ms = int((time.perf_counter() - t0) * 1000)
    except ValueError as exc:
        logger.warning("[API/RAG] 业务错误: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[API/RAG] RAG 执行失败")
        raise HTTPException(status_code=502, detail="RAG pipeline failed") from exc

    conv_memory.add_turn(session_id, request.question, result.answer)

    evaluation = None
    eval_record = None
    if request.evaluate:
        eval_record = evaluate_rag_result(
            result,
            user_id=user.user_id,
            session_id=session_id,
            top_k=request.top_k,
            generate_ms=generate_ms,
        )
        evaluation = record_to_summary(eval_record)

    return RAGAskResponse(
        question=result.question,
        answer=result.answer,
        session_id=session_id,
        user_id=user.user_id,
        sources=sources_for_response(result, eval_record),
        context_preview=result.context[:500] if result.context else "",
        evaluation=evaluation,
    )


@router.post("/ask/stream")
async def rag_ask_stream_endpoint(
    request: RAGAskRequest,
    http_request: Request,
    user: UserContext = Depends(get_current_user),
):
    """流式 RAG 文档问答（SSE）。事件: context → token* → done | cancelled | error"""
    session_store = get_session_store()
    conv_memory = get_conversation_memory()
    session_id, _ = _resolve_session(session_store, request.session_id, user.user_id)
    history = conv_memory.load_history_for_prompt(session_id)
    cancelled = {"value": False}
    partial_answer = {"value": ""}

    logger.info(
        "[API/RAG] 流式问题: user=%s session=%s, q=%s",
        user.user_id,
        session_id,
        request.question[:100],
    )

    def should_cancel() -> bool:
        return cancelled["value"]

    def producer():
        stream_start = time.perf_counter()
        context_full = {"value": ""}

        for event in rag_ask_stream(
            request.question,
            user_id=user.user_id,
            top_k=request.top_k,
            history=history,
            should_cancel=should_cancel,
        ):
            if event.get("type") == "context":
                context_full["value"] = event.get("context_preview", "")

            if event.get("type") == "token":
                partial_answer["value"] += event.get("content", "")

            if event.get("type") == "done":
                conv_memory.add_turn(session_id, request.question, event["answer"])
                event["session_id"] = session_id
                event["user_id"] = user.user_id

                if request.evaluate:
                    generate_ms = int((time.perf_counter() - stream_start) * 1000)
                    rag_result = rag_result_from_source_dicts(
                        event["question"],
                        event["answer"],
                        event.get("sources", []),
                        context=context_full["value"],
                    )
                    record = evaluate_rag_result(
                        rag_result,
                        user_id=user.user_id,
                        session_id=session_id,
                        top_k=request.top_k,
                        generate_ms=generate_ms,
                    )
                    summary = record_to_summary(record)
                    event["evaluation"] = summary.model_dump()
                    event["sources"] = [
                        s.model_dump()
                        for s in sources_for_response(rag_result, record)
                    ]

            if event.get("type") == "cancelled":
                answer = event.get("answer") or partial_answer["value"]
                if answer.strip():
                    conv_memory.add_turn(session_id, request.question, answer)
                event["session_id"] = session_id
                event["user_id"] = user.user_id

            yield event

    return create_sse_response(
        producer,
        http_request=http_request,
        should_cancel=should_cancel,
    )


@router.post("/ingest", response_model=RAGIngestResponse)
async def rag_ingest_endpoint(
    request: RAGIngestRequest,
    user: UserContext = Depends(get_current_user),
) -> RAGIngestResponse:
    """把文本内容入库（切分 + Embedding + FAISS）。"""
    logger.info(
        "[API/RAG] 入库请求: user=%s source=%s, 长度=%d",
        user.user_id,
        request.source,
        len(request.text),
    )

    try:
        count = ingest_text(request.text, source=request.source, user_id=user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[API/RAG] 入库失败")
        raise HTTPException(status_code=502, detail="Ingest failed") from exc

    return RAGIngestResponse(source=request.source, chunks_added=count)
