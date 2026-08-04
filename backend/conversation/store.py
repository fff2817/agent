"""
Conversation 持久化 — SQLite 保存对话元数据与完整消息。

设计约定:
  - conversation_id 与现有 session_id 使用同一 UUID
  - SessionStore 继续负责 Agent 短期记忆注入；本模块负责 UI 历史列表与完整恢复
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from conversation.types import Conversation, ConversationMessage
from core.config import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_TITLE = "新对话"
_TITLE_MAX_LEN = 36


class ConversationForbiddenError(Exception):
    """Conversation 不属于当前用户。"""


class ConversationNotFoundError(Exception):
    """Conversation 不存在。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_title_from_message(message: str) -> str:
    text = " ".join((message or "").strip().split())
    if not text:
        return _DEFAULT_TITLE
    if len(text) <= _TITLE_MAX_LEN:
        return text
    return text[: _TITLE_MAX_LEN - 1] + "…"


class ConversationStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.conversations_db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id         TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id               TEXT PRIMARY KEY,
                    conversation_id  TEXT NOT NULL,
                    role             TEXT NOT NULL,
                    content          TEXT NOT NULL,
                    meta_json        TEXT NOT NULL DEFAULT '{}',
                    created_at       TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_user_updated "
                "ON conversations(user_id, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_msg_conv "
                "ON conversation_messages(conversation_id, created_at)"
            )

    def ensure_conversation(
        self,
        conversation_id: str | None,
        user_id: str,
        *,
        title: str | None = None,
    ) -> Conversation:
        """获取或创建对话；存在时校验归属。"""
        if not conversation_id or not conversation_id.strip():
            return self.create(user_id, title=title)

        existing = self.get(conversation_id)
        if existing is None:
            now = _now()
            conv = Conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                title=(title or _DEFAULT_TITLE).strip() or _DEFAULT_TITLE,
                created_at=now,
                updated_at=now,
                message_count=0,
            )
            self._insert_conversation(conv)
            logger.info("[Conversation] 创建: %s user=%s", conv.conversation_id, user_id)
            return conv

        if existing.user_id != user_id:
            raise ConversationForbiddenError(
                f"Conversation {conversation_id} 不属于当前用户"
            )
        return existing

    def create(self, user_id: str, *, title: str | None = None) -> Conversation:
        now = _now()
        conv = Conversation(
            conversation_id=str(uuid.uuid4()),
            user_id=user_id,
            title=(title or _DEFAULT_TITLE).strip() or _DEFAULT_TITLE,
            created_at=now,
            updated_at=now,
            message_count=0,
        )
        self._insert_conversation(conv)
        logger.info("[Conversation] 新建空对话: %s user=%s", conv.conversation_id, user_id)
        return conv

    def get(self, conversation_id: str) -> Conversation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                return None
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM conversation_messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["c"]
        return Conversation(
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            message_count=int(count),
        )

    def get_owned(self, conversation_id: str, user_id: str) -> Conversation:
        conv = self.get(conversation_id)
        if conv is None:
            raise ConversationNotFoundError(f"Conversation 不存在: {conversation_id}")
        if conv.user_id != user_id:
            raise ConversationForbiddenError(
                f"Conversation {conversation_id} 不属于当前用户"
            )
        return conv

    def list_for_user(self, user_id: str, *, limit: int = 100) -> list[Conversation]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*,
                       (SELECT COUNT(*) FROM conversation_messages m
                        WHERE m.conversation_id = c.conversation_id) AS message_count
                FROM conversations c
                WHERE c.user_id = ?
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [
            Conversation(
                conversation_id=row["conversation_id"],
                user_id=row["user_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                message_count=int(row["message_count"] or 0),
            )
            for row in rows
        ]

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [_row_to_message(row) for row in rows]

    def append_turn(
        self,
        conversation_id: str,
        user_id: str,
        user_content: str,
        assistant_content: str,
        *,
        user_meta: dict | None = None,
        assistant_meta: dict | None = None,
    ) -> Conversation:
        """追加一轮 user/assistant，并在首条用户消息时自动生成标题。"""
        conv = self.get_owned(conversation_id, user_id)
        now = _now()
        user_msg = ConversationMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="user",
            content=user_content,
            created_at=now,
            meta=user_meta or {},
        )
        assistant_msg = ConversationMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            created_at=now,
            meta=assistant_meta or {},
        )

        new_title = conv.title
        if conv.message_count == 0 and conv.title in ("", _DEFAULT_TITLE):
            new_title = make_title_from_message(user_content)

        with self._connect() as conn:
            for msg in (user_msg, assistant_msg):
                conn.execute(
                    """
                    INSERT INTO conversation_messages
                        (id, conversation_id, role, content, meta_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg.id,
                        msg.conversation_id,
                        msg.role,
                        msg.content,
                        json.dumps(msg.meta, ensure_ascii=False),
                        msg.created_at,
                    ),
                )
            conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE conversation_id = ?
                """,
                (new_title, now, conversation_id),
            )

        updated = self.get_owned(conversation_id, user_id)
        logger.info(
            "[Conversation] 追加一轮: %s messages=%d title=%s",
            conversation_id,
            updated.message_count,
            updated.title,
        )
        return updated

    def rename(self, conversation_id: str, user_id: str, title: str) -> Conversation:
        conv = self.get_owned(conversation_id, user_id)
        cleaned = (title or "").strip() or _DEFAULT_TITLE
        if len(cleaned) > 80:
            cleaned = cleaned[:79] + "…"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE conversation_id = ?",
                (cleaned, now, conversation_id),
            )
        return self.get_owned(conversation_id, user_id)

    def delete(self, conversation_id: str, user_id: str) -> None:
        self.get_owned(conversation_id, user_id)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
        logger.info("[Conversation] 已删除: %s user=%s", conversation_id, user_id)

    def _insert_conversation(self, conv: Conversation) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations
                    (conversation_id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conv.conversation_id,
                    conv.user_id,
                    conv.title,
                    conv.created_at,
                    conv.updated_at,
                ),
            )


def _row_to_message(row: sqlite3.Row) -> ConversationMessage:
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except json.JSONDecodeError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return ConversationMessage(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        meta=meta,
    )


_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store


def reset_conversation_store() -> None:
    """测试用：清空单例，以便重新读取 Settings 路径。"""
    global _store
    _store = None
