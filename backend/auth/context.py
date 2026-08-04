"""请求级用户上下文 — 供 API 与 Agent 工具链共享 user_id。"""

from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    """当前请求的用户身份。"""

    user_id: str
    username: str | None = None
    auth_method: str = "jwt"


_current_user: ContextVar[UserContext | None] = ContextVar("current_user", default=None)
# SSE 在独立线程跑 Agent；ContextVar 在部分场景会丢失，用 thread-local 兜底
_thread_user = threading.local()


def set_current_user(user: UserContext) -> None:
    _current_user.set(user)
    _thread_user.user_id = user.user_id
    _thread_user.username = user.username


def get_current_user_ctx() -> UserContext | None:
    ctx = _current_user.get()
    if ctx is not None:
        return ctx
    user_id = getattr(_thread_user, "user_id", None)
    if user_id:
        return UserContext(
            user_id=user_id,
            username=getattr(_thread_user, "username", None),
            auth_method="thread_local",
        )
    return None


def set_current_user_id(user_id: str) -> None:
    set_current_user(UserContext(user_id=user_id, auth_method="context"))


def get_current_user_id() -> str | None:
    ctx = get_current_user_ctx()
    return ctx.user_id if ctx else None


def clear_current_user() -> None:
    _current_user.set(None)
    if hasattr(_thread_user, "user_id"):
        del _thread_user.user_id
    if hasattr(_thread_user, "username"):
        del _thread_user.username
