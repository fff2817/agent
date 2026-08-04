"""Conversation 数据结构 — 聊天历史列表与完整消息恢复。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversationMessage:
    id: str
    conversation_id: str
    role: str  # user | assistant
    content: str
    created_at: str
    # 可选：附件、ReAct steps、检索记忆等，供前端完整恢复
    meta: dict = field(default_factory=dict)


@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
