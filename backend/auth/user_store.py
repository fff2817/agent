"""用户持久化 — SQLite。"""

from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class UserRecord:
    user_id: str
    username: str
    password_hash: str
    api_key: str
    created_at: str


class UserStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.users_db_path)
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
                CREATE TABLE IF NOT EXISTS users (
                    user_id       TEXT PRIMARY KEY,
                    username      TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    api_key       TEXT UNIQUE NOT NULL,
                    created_at    TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return f"{salt}${digest}"

    @staticmethod
    def verify_password(password: str, stored: str) -> bool:
        if "$" not in stored:
            return False
        salt, _ = stored.split("$", 1)
        return UserStore.hash_password(password, salt) == stored

    def create_user(self, username: str, password: str) -> UserRecord:
        username = username.strip()
        if not username:
            raise ValueError("用户名不能为空")
        if len(password) < 4:
            raise ValueError("密码至少 4 位")

        user_id = str(uuid.uuid4())
        api_key = f"sk-{secrets.token_urlsafe(24)}"
        salt = secrets.token_hex(16)
        password_hash = self.hash_password(password, salt)
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users (user_id, username, password_hash, api_key, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, username, password_hash, api_key, created_at),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("用户名已存在") from exc

        logger.info("[Auth] 注册用户: user_id=%s username=%s", user_id, username)
        return UserRecord(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            api_key=api_key,
            created_at=created_at,
        )

    def get_by_username(self, username: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_by_api_key(self, api_key: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE api_key = ?",
                (api_key.strip(),),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_or_create_dev_user(self, user_id: str, username: str) -> UserRecord:
        existing = self.get_by_id(user_id)
        if existing:
            return existing

        api_key = f"sk-{secrets.token_urlsafe(24)}"
        salt = secrets.token_hex(16)
        password_hash = self.hash_password(secrets.token_urlsafe(16), salt)
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, password_hash, api_key, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, username, password_hash, api_key, created_at),
            )

        logger.info("[Auth] 创建开发用户: user_id=%s username=%s", user_id, username)
        return UserRecord(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            api_key=api_key,
            created_at=created_at,
        )


def _row_to_record(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        user_id=row["user_id"],
        username=row["username"],
        password_hash=row["password_hash"],
        api_key=row["api_key"],
        created_at=row["created_at"],
    )


_store: UserStore | None = None


def get_user_store() -> UserStore:
    global _store
    if _store is None:
        _store = UserStore()
    return _store
