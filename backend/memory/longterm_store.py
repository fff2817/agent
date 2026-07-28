"""
Long-term Memory 门面 — 对外提供 retrieve / save_turn。

接入方式:
    1. retrieve(user_id, query) → MemoryRetrievalResult（检索 + Top-K + hints）
    2. save_turn(...) → 筛选 + Embedding + FAISS 入库
    3. search(...) → hints[] 简写（兼容旧调用）
"""

from __future__ import annotations

import logging

from memory.chain import MemoryRetrievalResult, retrieve_memories_for_question
from memory.ingester import ingest_turn
from memory.types import ExtractionResult

logger = logging.getLogger(__name__)


class LongTermStore:
    """长期记忆存储与检索。"""

    def retrieve(self, user_id: str, query: str) -> MemoryRetrievalResult:
        """
        完整检索链路: 判断是否检索 → FAISS Top-K → 生成 hints/context。

        供 /chat Agent 路径在 run_react_agent 之前调用。
        """
        return retrieve_memories_for_question(query, user_id=user_id)

    def search(self, user_id: str, query: str) -> list[str]:
        """
        简写接口 — 仅返回 hints 字符串列表。

        内部调用 retrieve()，保持向后兼容。
        """
        result = self.retrieve(user_id, query)
        return result.hints

    def save_turn(
        self,
        user_message: str,
        assistant_message: str,
        *,
        user_id: str,
        session_id: str | None = None,
    ) -> ExtractionResult:
        """从一轮对话中提取并持久化长期记忆。"""
        return ingest_turn(
            user_message,
            assistant_message,
            user_id=user_id,
            session_id=session_id,
        )


_store = LongTermStore()


def get_longterm_store() -> LongTermStore:
    return _store
