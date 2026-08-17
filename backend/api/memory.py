"""

Long-term Memory API — 记忆检索问答 HTTP 接口。



POST /memory/ask         触发完整记忆检索 + LLM 回答链路

POST /memory/ask/stream  流式记忆问答（SSE）

"""



import logging



from fastapi import APIRouter, Depends, HTTPException, Query, Request



from auth.context import UserContext

from auth.dependencies import get_current_user

from core.sse import create_sse_response

from lc.memory.chain import memory_ask, memory_ask_stream
from lc.memory.conversation_memory import get_conversation_memory
from infra.longterm_store import get_longterm_store
from infra.session_store import SessionForbiddenError, get_session_store

from infra.memory_vectorstore import get_memory_vector_store

from models.schemas import (

    LongTermMemoryItemSchema,

    MemoryAskRequest,

    MemoryAskResponse,

    MemoryOverviewResponse,

    MemorySourceSchema,

)



logger = logging.getLogger(__name__)



router = APIRouter(prefix="/memory", tags=["memory"])





def _memory_source_label(source_session_id: str | None) -> str:

    if source_session_id:

        return "conversation_history"

    return "long_term_store"





def _resolve_session(session_store, session_id: str | None, user_id: str):

    try:

        return session_store.get_or_create(session_id, user_id)

    except SessionForbiddenError as exc:

        raise HTTPException(status_code=403, detail=str(exc)) from exc





@router.get("", response_model=MemoryOverviewResponse)

async def get_memory_overview(

    session_id: str | None = Query(None, description="Session ID; omit to start new"),

    user: UserContext = Depends(get_current_user),

) -> MemoryOverviewResponse:

    """

    获取 Memory 面板数据 — 短期 + 长期记忆概览。



    数据流:

        user_id → SessionStore（短期 turns）

               → MemoryVectorStore（长期 FAISS metadata）

    """

    session_store = get_session_store()

    resolved_session_id, _ = _resolve_session(session_store, session_id, user.user_id)



    short_term = session_store.get_short_term_items(resolved_session_id)



    vector_store = get_memory_vector_store(user.user_id)

    long_term_records = vector_store.list_for_user(user.user_id)

    long_term = [

        LongTermMemoryItemSchema(

            content=record.content,

            memory_type=record.memory_type.value,

            importance=record.importance,

            source=_memory_source_label(record.source_session_id),

            created_at=record.created_at,

        )

        for record in long_term_records

    ]



    logger.info(

        "[API/Memory] GET overview: user=%s session=%s, short=%d, long=%d",

        user.user_id,

        resolved_session_id,

        len(short_term),

        len(long_term),

    )



    return MemoryOverviewResponse(

        user_id=user.user_id,

        session_id=resolved_session_id,

        short_term_memory=short_term,

        long_term_memory=long_term,

    )





@router.post("/ask", response_model=MemoryAskResponse)

async def memory_ask_endpoint(

    request: MemoryAskRequest,

    user: UserContext = Depends(get_current_user),

) -> MemoryAskResponse:

    """

    长期记忆问答 — 完整链路 HTTP 入口。



    数据流:

        用户提问 → 是否检索 → FAISS Top-K → 拼 Prompt → LLM → 回答

    """

    session_store = get_session_store()

    longterm = get_longterm_store()

    session_id, _ = _resolve_session(session_store, request.session_id, user.user_id)



    logger.info(

        "[API/Memory] 收到问题: user=%s session=%s, q=%s",

        user.user_id,

        session_id,

        request.question[:100],

    )



    history = get_conversation_memory().load_history_for_prompt(session_id)



    try:

        result = memory_ask(

            request.question,

            user_id=user.user_id,

            top_k=request.top_k,

            history=history,

        )

    except ValueError as exc:

        logger.warning("[API/Memory] 业务错误: %s", exc)

        raise HTTPException(status_code=503, detail=str(exc)) from exc

    except Exception as exc:

        logger.exception("[API/Memory] 记忆问答失败")

        raise HTTPException(status_code=502, detail="Memory pipeline failed") from exc



    get_conversation_memory().add_turn(session_id, request.question, result.answer)

    longterm.save_turn(

        request.question,

        result.answer,

        user_id=user.user_id,

        session_id=session_id,

    )



    sources = [

        MemorySourceSchema(

            rank=m.rank,

            score=m.score,

            memory_type=m.record.memory_type.value,

            content=m.record.content,

        )

        for m in result.memories

    ]



    return MemoryAskResponse(

        question=result.question,

        answer=result.answer,

        session_id=session_id,

        user_id=user.user_id,

        should_retrieve=result.should_retrieve,

        skip_reason=result.skip_reason,

        memories=sources,

        context_preview=result.context[:500] if result.context else "",

    )





@router.post("/ask/stream")

async def memory_ask_stream_endpoint(

    request: MemoryAskRequest,

    http_request: Request,

    user: UserContext = Depends(get_current_user),

):

    """

    流式长期记忆问答（SSE）。



    事件: context → token* → done | cancelled | error

    """

    session_store = get_session_store()

    longterm = get_longterm_store()

    session_id, _ = _resolve_session(session_store, request.session_id, user.user_id)

    history = get_conversation_memory().load_history_for_prompt(session_id)

    cancelled = {"value": False}

    partial_answer = {"value": ""}



    logger.info(

        "[API/Memory] 流式问题: user=%s session=%s, q=%s",

        user.user_id,

        session_id,

        request.question[:100],

    )



    def should_cancel() -> bool:

        return cancelled["value"]



    def producer():

        for event in memory_ask_stream(

            request.question,

            user_id=user.user_id,

            top_k=request.top_k,

            history=history,

            should_cancel=should_cancel,

        ):

            if event.get("type") == "token":

                partial_answer["value"] += event.get("content", "")



            if event.get("type") == "done":

                get_conversation_memory().add_turn(session_id, request.question, event["answer"])

                longterm.save_turn(

                    request.question,

                    event["answer"],

                    user_id=user.user_id,

                    session_id=session_id,

                )

                event["session_id"] = session_id

                event["user_id"] = user.user_id



            if event.get("type") == "cancelled":

                answer = event.get("answer") or partial_answer["value"]

                if answer.strip():

                    get_conversation_memory().add_turn(session_id, request.question, answer)

                    longterm.save_turn(

                        request.question,

                        answer,

                        user_id=user.user_id,

                        session_id=session_id,

                    )

                event["session_id"] = session_id

                event["user_id"] = user.user_id



            yield event



    return create_sse_response(

        producer,

        http_request=http_request,

        should_cancel=should_cancel,

    )


