"""RAG 评估 API — 查询历史评估记录与统计。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.context import UserContext
from auth.dependencies import get_current_user
from eval.serializers import record_to_detail
from eval.store import get_eval_store
from models.schemas import (
    RAGEvaluationDetailSchema,
    RAGEvaluationListItemSchema,
    RAGEvaluationStatsSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag/evaluations", tags=["rag-evaluation"])


@router.get("", response_model=list[RAGEvaluationListItemSchema])
async def list_evaluations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(get_current_user),
) -> list[RAGEvaluationListItemSchema]:
    rows = get_eval_store().list_records(user_id=user.user_id, limit=limit, offset=offset)
    return [RAGEvaluationListItemSchema(**row) for row in rows]


@router.get("/stats", response_model=RAGEvaluationStatsSchema)
async def evaluation_stats(
    user: UserContext = Depends(get_current_user),
) -> RAGEvaluationStatsSchema:
    return RAGEvaluationStatsSchema(**get_eval_store().stats(user_id=user.user_id))


@router.get("/{evaluation_id}", response_model=RAGEvaluationDetailSchema)
async def get_evaluation(
    evaluation_id: str,
    user: UserContext = Depends(get_current_user),
) -> RAGEvaluationDetailSchema:
    record = get_eval_store().get(evaluation_id, user_id=user.user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return record_to_detail(record)
