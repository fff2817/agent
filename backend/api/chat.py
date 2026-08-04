import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent.loop import AgentCancelledError, run_react_agent, run_react_agent_stream
from auth.context import UserContext, set_current_user_id
from auth.dependencies import get_current_user
from conversation.store import (
    ConversationForbiddenError,
    get_conversation_store,
)
from core.sse import create_sse_response
from memory.chain import MemoryRetrievalResult
from memory.longterm_store import get_longterm_store
from memory.session_store import SessionForbiddenError, get_session_store
from memory.types import Session
from models.schemas import ChatRequest, ChatResponse, ReActStepSchema, RetrievedMemorySchema

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _resolve_chat_id(request: ChatRequest) -> str | None:
    """conversation_id 优先，与 session_id 共用同一 UUID。"""
    return request.conversation_id or request.session_id


def _resolve_session(session_store, session_id: str | None, user_id: str) -> tuple[str, Session]:
    try:
        return session_store.get_or_create(session_id, user_id)
    except SessionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _ensure_conversation(conversation_id: str, user_id: str) -> None:
    store = get_conversation_store()
    try:
        store.ensure_conversation(conversation_id, user_id)
    except ConversationForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _persist_conversation_turn(
    conversation_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
    *,
    steps: list | None = None,
    retrieved_memories: list | None = None,
    memory_retrieval_skipped: bool = False,
    memory_skip_reason: str = "",
) -> None:
    store = get_conversation_store()
    assistant_meta = {
        "steps": steps or [],
        "retrieved_memories": retrieved_memories or [],
        "memory_retrieval_skipped": memory_retrieval_skipped,
        "memory_skip_reason": memory_skip_reason or "",
    }
    try:
        store.append_turn(
            conversation_id,
            user_id,
            user_message,
            assistant_message,
            assistant_meta=assistant_meta,
        )
    except Exception:
        logger.exception("[API] Conversation 持久化失败: %s", conversation_id)


def _retrieve_longterm_memory(user_id: str, message: str) -> MemoryRetrievalResult:
    longterm = get_longterm_store()
    return longterm.retrieve(user_id, message)


def _save_longterm_memory(
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    if not assistant_message.strip():
        return
    longterm = get_longterm_store()
    result = longterm.save_turn(
        user_message,
        assistant_message,
        user_id=user_id,
        session_id=session_id,
    )
    if result.should_save:
        logger.info("[API] 长期记忆已入库: %s", result.record.content if result.record else "")


def _memory_source_label(source_session_id: str | None) -> str:
    if source_session_id:
        return "conversation_history"
    return "long_term_store"


def _serialize_retrieved_memories(
    memory_result: MemoryRetrievalResult,
) -> list[RetrievedMemorySchema]:
    return [
        RetrievedMemorySchema(
            rank=item.rank,
            score=round(item.score, 4),
            content=item.record.content,
            memory_type=item.record.memory_type.value,
            source=_memory_source_label(item.record.source_session_id),
        )
        for item in memory_result.memories
    ]


def _build_context_event(memory_result: MemoryRetrievalResult) -> dict:
    return {
        "type": "context",
        "retrieved_memories": [
            m.model_dump() for m in _serialize_retrieved_memories(memory_result)
        ],
        "memory_retrieval_skipped": not memory_result.should_retrieve,
        "memory_skip_reason": memory_result.skip_reason,
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: UserContext = Depends(get_current_user),
) -> ChatResponse:
    """
    聊天接口 — HTTP 入口。

    Session Memory 流程:
      1. 加载 session 历史（校验 user_id 归属）
      2. 交给 ReAct Agent（history 注入 Prompt）
      3. 保存本轮 user + assistant（Session + Conversation）
      4. 返回 session_id / conversation_id 供前端续聊
    """
    session_store = get_session_store()
    session_id, _ = _resolve_session(session_store, _resolve_chat_id(request), user.user_id)
    _ensure_conversation(session_id, user.user_id)

    logger.info(
        "[API] 收到聊天请求: user=%s session=%s, message=%s",
        user.user_id,
        session_id,
        request.message[:100],
    )

    history = session_store.get_history_messages(session_id)
    memory_result = _retrieve_longterm_memory(user.user_id, request.message)

    try:
        result = run_react_agent(
            request.message,
            history=history,
            memory_hints=memory_result.hints,
            user_id=user.user_id,
        )
    except ValueError as exc:
        logger.warning("[API] 配置或响应错误: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[API] ReAct Agent 执行失败")
        raise HTTPException(
            status_code=502,
            detail="Failed to get a response from the language model. Please try again later.",
        ) from exc

    session_store.add_turn(session_id, request.message, result.response)
    _save_longterm_memory(user.user_id, session_id, request.message, result.response)

    steps = [
        ReActStepSchema(
            step=s.step,
            thought=s.thought,
            action=s.action,
            observation=s.observation,
            final_answer=s.final_answer,
        )
        for s in result.trace
    ]
    retrieved = _serialize_retrieved_memories(memory_result)
    _persist_conversation_turn(
        session_id,
        user.user_id,
        request.message,
        result.response,
        steps=[s.model_dump() for s in steps],
        retrieved_memories=[m.model_dump() for m in retrieved],
        memory_retrieval_skipped=not memory_result.should_retrieve,
        memory_skip_reason=memory_result.skip_reason,
    )

    logger.info(
        "[API] 返回回复: user=%s session=%s, 长度=%d, 历史=%d 轮",
        user.user_id,
        session_id,
        len(result.response),
        session_store.get_turn_count(session_id),
    )
    return ChatResponse(
        response=result.response,
        session_id=session_id,
        conversation_id=session_id,
        user_id=user.user_id,
        steps=steps,
        memories_used=memory_result.hints,
        retrieved_memories=retrieved,
        memory_retrieval_skipped=not memory_result.should_retrieve,
        memory_skip_reason=memory_result.skip_reason,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    """
    流式聊天接口（SSE）— 支持逐 token 推送与客户端断开即取消。

    事件类型:
      - context: 本轮 Memory 上下文（流式开始前推送）
      - token:  Final Answer 文本片段
      - step:   ReAct 单步 trace
      - done:   完成（含 response / session_id / conversation_id / steps）
      - cancelled: 用户停止生成
      - error:  错误信息
    """
    session_store = get_session_store()
    session_id, _ = _resolve_session(session_store, _resolve_chat_id(request), user.user_id)
    _ensure_conversation(session_id, user.user_id)
    history = session_store.get_history_messages(session_id)
    memory_result = _retrieve_longterm_memory(user.user_id, request.message)
    cancelled = {"value": False}
    partial_response = {"value": ""}

    logger.info(
        "[API] 流式聊天: user=%s session=%s, message=%s",
        user.user_id,
        session_id,
        request.message[:100],
    )

    def should_cancel() -> bool:
        return cancelled["value"]

    def producer():
        set_current_user_id(user.user_id)
        try:
            for event in run_react_agent_stream(
                request.message,
                history=history,
                memory_hints=memory_result.hints,
                should_cancel=should_cancel,
                user_id=user.user_id,
            ):
                if event.get("type") == "token":
                    partial_response["value"] += event.get("content", "")

                if event.get("type") == "done":
                    session_store.add_turn(
                        session_id,
                        request.message,
                        event["response"],
                    )
                    _save_longterm_memory(
                        user.user_id,
                        session_id,
                        request.message,
                        event["response"],
                    )
                    retrieved = [
                        m.model_dump() for m in _serialize_retrieved_memories(memory_result)
                    ]
                    _persist_conversation_turn(
                        session_id,
                        user.user_id,
                        request.message,
                        event["response"],
                        steps=event.get("steps") or [],
                        retrieved_memories=retrieved,
                        memory_retrieval_skipped=not memory_result.should_retrieve,
                        memory_skip_reason=memory_result.skip_reason,
                    )
                    event["session_id"] = session_id
                    event["conversation_id"] = session_id
                    event["user_id"] = user.user_id
                    event["memories_used"] = memory_result.hints
                    event["retrieved_memories"] = retrieved
                    event["memory_retrieval_skipped"] = not memory_result.should_retrieve
                    event["memory_skip_reason"] = memory_result.skip_reason

                yield event
        except AgentCancelledError as exc:
            partial = exc.partial_response or partial_response["value"]
            if partial.strip():
                session_store.add_turn(session_id, request.message, partial)
                _save_longterm_memory(user.user_id, session_id, request.message, partial)
                _persist_conversation_turn(
                    session_id,
                    user.user_id,
                    request.message,
                    partial,
                )
            logger.info(
                "[API] 流式生成已取消: session=%s, 保留 %d 字",
                session_id,
                len(partial),
            )
            yield {
                "type": "cancelled",
                "response": partial,
                "session_id": session_id,
                "conversation_id": session_id,
                "user_id": user.user_id,
            }

    return create_sse_response(
        producer,
        http_request=http_request,
        should_cancel=should_cancel,
        initial_events=[_build_context_event(memory_result)],
    )
