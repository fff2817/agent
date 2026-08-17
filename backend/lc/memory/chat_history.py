"""
LangChain ChatMessageHistory 适配器 — 绑定现有 SessionStore（SQLite）。

保留完整会话轮次；Prompt 侧压缩见 compressor / ConversationMemory。
"""

from __future__ import annotations

import logging
from typing import Sequence

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from lc.llm.chat import dict_messages_to_lc
from infra.session_store import SessionStore, get_session_store

logger = logging.getLogger(__name__)


class SessionChatMessageHistory(BaseChatMessageHistory):
    """
    将 SessionStore 暴露为 LangChain BaseChatMessageHistory。

    - messages: 从 SQLite 加载的 Human/AI 消息
    - add_message: 成对写入（Human 后接 AI 触发 add_turn）
    """

    def __init__(
        self,
        session_id: str,
        *,
        store: SessionStore | None = None,
    ) -> None:
        self.session_id = session_id
        self._store = store or get_session_store()
        self._pending_human: str | None = None

    @property
    def messages(self) -> list[BaseMessage]:
        history = self._store.get_history_messages(self.session_id)
        return dict_messages_to_lc(history)

    def add_message(self, message: BaseMessage) -> None:
        if isinstance(message, HumanMessage):
            content = message.content if isinstance(message.content, str) else str(message.content)
            self._pending_human = content
            return

        if isinstance(message, AIMessage):
            if self._pending_human is None:
                raise ValueError("Cannot add AIMessage without a preceding HumanMessage")
            content = message.content if isinstance(message.content, str) else str(message.content)
            self._store.add_turn(self.session_id, self._pending_human, content)
            self._pending_human = None
            return

        raise TypeError(
            f"SessionChatMessageHistory only supports HumanMessage/AIMessage, got {type(message)}"
        )

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        for message in messages:
            self.add_message(message)

    def clear(self) -> None:
        self._pending_human = None
        self._store.clear_turns(self.session_id)
        logger.info("[LC-History] cleared session=%s", self.session_id)


def get_session_chat_history(
    session_id: str,
    *,
    store: SessionStore | None = None,
) -> SessionChatMessageHistory:
    return SessionChatMessageHistory(session_id, store=store)
