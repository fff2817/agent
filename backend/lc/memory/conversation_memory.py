"""
ConversationMemory — LangChain 风格对话记忆门面。

职责:
  1. 短期历史：SessionChatMessageHistory + SQLite（保留记录）
  2. 上下文压缩：ContextCompressor（摘要 / 窗口 / trim）
  3. 长期记忆扩展点：LongTermMemoryBackend（默认接现有 LongTermStore）

API 层应优先使用本门面的 load_history_for_prompt / add_turn，
而不是直接拼 SessionStore 原始 messages。
"""

from __future__ import annotations

import logging
from typing import Protocol

from lc.memory.chat_history import SessionChatMessageHistory, get_session_chat_history
from lc.memory.compressor import ContextCompressor, messages_to_openai_dicts
from infra.longterm_store import LongTermStore, get_longterm_store
from infra.session_store import SessionStore, get_session_store
from lc.memory.chain import MemoryRetrievalResult
from lc.memory.types import ExtractionResult

logger = logging.getLogger(__name__)


class LongTermMemoryBackend(Protocol):
    """长期记忆扩展接口 — 可替换为其他向量库 / LangChain Retriever。"""

    def retrieve(self, user_id: str, query: str) -> MemoryRetrievalResult: ...

    def save_turn(
        self,
        user_message: str,
        assistant_message: str,
        *,
        user_id: str,
        session_id: str | None = None,
    ) -> ExtractionResult: ...


class ConversationMemory:
    """统一对话记忆：短期（可压缩）+ 长期（可插拔）。"""

    def __init__(
        self,
        *,
        session_store: SessionStore | None = None,
        longterm: LongTermMemoryBackend | None = None,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self.session_store = session_store or get_session_store()
        self.longterm: LongTermMemoryBackend = longterm or get_longterm_store()
        self.compressor = compressor or ContextCompressor()

    def get_chat_history(self, session_id: str) -> SessionChatMessageHistory:
        return get_session_chat_history(session_id, store=self.session_store)

    def load_raw_history(self, session_id: str) -> list[dict]:
        """未压缩的完整短期历史（OpenAI dict），用于调试 / 兼容。"""
        return self.session_store.get_history_messages(session_id)

    def load_history_for_prompt(self, session_id: str) -> list[dict]:
        """
        供 Agent / RAG Prompt 注入的历史（已压缩）。

        保留存储层全量记录；仅对送入模型的上下文做压缩。
        """
        history = self.get_chat_history(session_id)
        raw = history.messages
        compressed = self.compressor.compress(raw)
        dicts = messages_to_openai_dicts(compressed)
        logger.info(
            "[ConversationMemory] prompt history session=%s raw_msgs=%d compressed=%d",
            session_id,
            len(raw),
            len(dicts),
        )
        return dicts

    def add_turn(self, session_id: str, user: str, assistant: str) -> None:
        """追加一轮对话到短期存储（保留历史）。"""
        self.session_store.add_turn(session_id, user, assistant)

    def retrieve_longterm(self, user_id: str, query: str) -> MemoryRetrievalResult:
        """长期记忆检索（扩展点）。"""
        return self.longterm.retrieve(user_id, query)

    def save_longterm(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> ExtractionResult:
        """长期记忆写入（扩展点）。"""
        return self.longterm.save_turn(
            user_message,
            assistant_message,
            user_id=user_id,
            session_id=session_id,
        )


_memory = ConversationMemory()


def get_conversation_memory() -> ConversationMemory:
    return _memory
