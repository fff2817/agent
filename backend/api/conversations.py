"""Conversation 管理 API — 列表 / 详情 / 新建 / 重命名 / 删除。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.context import UserContext
from auth.dependencies import get_current_user
from conversation.store import (
    ConversationForbiddenError,
    ConversationNotFoundError,
    get_conversation_store,
)
from models.schemas import (
    ConversationCreateResponse,
    ConversationDetailSchema,
    ConversationListResponse,
    ConversationMessageSchema,
    ConversationRenameRequest,
    ConversationSummarySchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _http_from_store(exc: Exception) -> HTTPException:
    if isinstance(exc, ConversationForbiddenError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ConversationNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _to_summary(conv) -> ConversationSummarySchema:
    return ConversationSummarySchema(
        conversation_id=conv.conversation_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=conv.message_count,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(get_current_user),
) -> ConversationListResponse:
    store = get_conversation_store()
    items = store.list_for_user(user.user_id, limit=limit)
    return ConversationListResponse(conversations=[_to_summary(c) for c in items])


@router.post("", response_model=ConversationCreateResponse)
async def create_conversation(
    user: UserContext = Depends(get_current_user),
) -> ConversationCreateResponse:
    store = get_conversation_store()
    conv = store.create(user.user_id)
    return ConversationCreateResponse(
        conversation_id=conv.conversation_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=conv.message_count,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailSchema)
async def get_conversation(
    conversation_id: str,
    user: UserContext = Depends(get_current_user),
) -> ConversationDetailSchema:
    store = get_conversation_store()
    try:
        conv = store.get_owned(conversation_id, user.user_id)
    except (ConversationForbiddenError, ConversationNotFoundError) as exc:
        raise _http_from_store(exc) from exc

    messages = store.list_messages(conversation_id)
    return ConversationDetailSchema(
        conversation_id=conv.conversation_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=conv.message_count,
        messages=[
            ConversationMessageSchema(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                meta=m.meta,
            )
            for m in messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationSummarySchema)
async def rename_conversation(
    conversation_id: str,
    body: ConversationRenameRequest,
    user: UserContext = Depends(get_current_user),
) -> ConversationSummarySchema:
    store = get_conversation_store()
    try:
        conv = store.rename(conversation_id, user.user_id, body.title)
    except (ConversationForbiddenError, ConversationNotFoundError) as exc:
        raise _http_from_store(exc) from exc
    return _to_summary(conv)


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    store = get_conversation_store()
    try:
        store.delete(conversation_id, user.user_id)
    except (ConversationForbiddenError, ConversationNotFoundError) as exc:
        raise _http_from_store(exc) from exc
    return {"status": "ok", "conversation_id": conversation_id}
