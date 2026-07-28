"""请求级用户上下文 — 供 API 与 Agent 工具链共享 user_id。"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    """当前请求的用户身份。"""

    user_id: str
    username: str | None = None
    auth_method: str = "jwt"


_current_user: ContextVar[UserContext | None] = ContextVar("current_user", default=None)


def set_current_user(user: UserContext) -> None:
    _current_user.set(user)


def get_current_user_ctx() -> UserContext | None:
    return _current_user.get()


def set_current_user_id(user_id: str) -> None:
    set_current_user(UserContext(user_id=user_id, auth_method="context"))


def get_current_user_id() -> str | None:
    ctx = get_current_user_ctx()
    return ctx.user_id if ctx else None
