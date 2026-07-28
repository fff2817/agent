"""
Session 短期记忆 — 跨请求保存最近 N 轮对话。

多用户改造:
  - 每个 Session 绑定 user_id
  - SQLite 持久化，重启不丢失
  - 访问时校验 Session 归属，防止跨用户越权
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.config import get_settings
from memory.types import ChatTurn, Session

logger = logging.getLogger(__name__)


class SessionForbiddenError(Exception):
    """Session 不属于当前用户。"""


class SessionStore:
    """会话存储 — SQLite 持久化，按 user_id 隔离。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.sessions_db_path)
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
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id  TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL,
                    turns_json  TEXT NOT NULL DEFAULT '[]',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)"
            )

    def get_or_create(
        self,
        session_id: str | None,
        user_id: str,
    ) -> tuple[str, Session]:
        """
        获取或创建会话，并校验 user_id 归属。

        参数:
            session_id: 前端传来的 ID；None 或空则新建
            user_id:    当前登录用户 ID

        异常:
            SessionForbiddenError: session 存在但属于其他用户
        """
        if not session_id or not session_id.strip():
            session_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            session = Session(session_id=session_id, user_id=user_id, created_at=now, updated_at=now)
            self._save(session)
            logger.info("[Session] 创建新会话: %s user=%s", session_id, user_id)
            return session_id, session

        existing = self._load(session_id)
        if existing is None:
            now = datetime.now(timezone.utc).isoformat()
            session = Session(session_id=session_id, user_id=user_id, created_at=now, updated_at=now)
            self._save(session)
            logger.info("[Session] 恢复/新建会话: %s user=%s", session_id, user_id)
            return session_id, session

        if existing.user_id != user_id:
            logger.warning(
                "[Session] 越权访问: session=%s owner=%s requester=%s",
                session_id,
                existing.user_id,
                user_id,
            )
            raise SessionForbiddenError(
                f"Session {session_id} 不属于当前用户"
            )

        return session_id, existing

    def get_history_messages(self, session_id: str) -> list[dict]:
        session = self._load(session_id)
        if not session or not session.turns:
            logger.info("[Session] 无历史记录: session_id=%s", session_id)
            return []

        messages: list[dict] = []
        for turn in session.turns:
            messages.append({"role": "user", "content": turn.user})
            messages.append({"role": "assistant", "content": turn.assistant})

        logger.info(
            "[Session] 加载历史: session_id=%s, %d 轮, %d 条 messages",
            session_id,
            len(session.turns),
            len(messages),
        )
        return messages

    def add_turn(self, session_id: str, user: str, assistant: str) -> None:
        session = self._load(session_id)
        if session is None:
            raise KeyError(f"Session 不存在: {session_id}")

        session.turns.append(ChatTurn(user=user, assistant=assistant))
        session.updated_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "[Session] 追加对话: session_id=%s, 当前 %d 轮",
            session_id,
            len(session.turns),
        )
        self._trim(session)
        self._save(session)

    def _trim(self, session: Session) -> None:
        settings = get_settings()
        max_turns = settings.max_session_turns

        if len(session.turns) <= max_turns:
            return

        removed = len(session.turns) - max_turns
        session.turns = session.turns[removed:]
        logger.info(
            "[Session] 截断历史: session_id=%s, 删除最早 %d 轮, 保留 %d 轮",
            session.session_id,
            removed,
            len(session.turns),
        )

    def get_turn_count(self, session_id: str) -> int:
        session = self._load(session_id)
        return len(session.turns) if session else 0

    def get_short_term_items(self, session_id: str) -> list[str]:
        session = self._load(session_id)
        if not session or not session.turns:
            return []

        items: list[str] = []
        for turn in session.turns:
            if turn.user.strip():
                items.append(turn.user.strip())
            if turn.assistant.strip():
                items.append(turn.assistant.strip())
        return items

    def list_session_ids(self, user_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [row["session_id"] for row in rows]

    def _load(self, session_id: str) -> Session | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return _row_to_session(row)

    def _save(self, session: Session) -> None:
        turns_json = json.dumps(
            [
                {"user": t.user, "assistant": t.assistant, "created_at": t.created_at}
                for t in session.turns
            ],
            ensure_ascii=False,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, user_id, turns_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    turns_json = excluded.turns_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session.session_id,
                    session.user_id,
                    turns_json,
                    session.created_at,
                    session.updated_at,
                ),
            )


def _row_to_session(row: sqlite3.Row) -> Session:
    turns_data = json.loads(row["turns_json"] or "[]")
    turns = [
        ChatTurn(
            user=item["user"],
            assistant=item["assistant"],
            created_at=item.get("created_at", ""),
        )
        for item in turns_data
    ]
    return Session(
        session_id=row["session_id"],
        user_id=row["user_id"],
        turns=turns,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
