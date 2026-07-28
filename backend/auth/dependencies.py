"""FastAPI 鉴权 Dependency。"""

from __future__ import annotations

import logging
import uuid

from fastapi import Header, HTTPException

from auth.context import UserContext, set_current_user
from auth.jwt_utils import decode_access_token
from auth.user_store import get_user_store
from core.config import get_settings

logger = logging.getLogger(__name__)

DEV_DEFAULT_USER_ID = "dev-default"
DEV_DEFAULT_USERNAME = "dev-user"


async def get_current_user(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> UserContext:
    """
    解析当前用户身份并写入 ContextVar。

    优先级:
      1. Authorization: Bearer <jwt>
      2. X-API-Key
      3. auth_disabled 模式下 X-User-Id 或 dev-default
    """
    settings = get_settings()
    store = get_user_store()

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        try:
            payload = decode_access_token(token)
            user_id = payload["sub"]
            username = payload.get("username")
        except Exception as exc:
            raise HTTPException(status_code=401, detail="无效或过期的 Token") from exc

        user = store.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        ctx = UserContext(user_id=user.user_id, username=user.username, auth_method="jwt")
        set_current_user(ctx)
        return ctx

    if x_api_key:
        user = store.get_by_api_key(x_api_key)
        if not user:
            raise HTTPException(status_code=401, detail="无效的 API Key")
        ctx = UserContext(user_id=user.user_id, username=user.username, auth_method="api_key")
        set_current_user(ctx)
        return ctx

    if settings.auth_disabled:
        dev_user_id = (x_user_id or DEV_DEFAULT_USER_ID).strip()
        if not dev_user_id:
            dev_user_id = str(uuid.uuid4())
        username = f"dev-{dev_user_id[:8]}"
        user = store.get_or_create_dev_user(dev_user_id, username)
        ctx = UserContext(user_id=user.user_id, username=user.username, auth_method="dev_header")
        set_current_user(ctx)
        logger.debug("[Auth] 开发模式用户: %s", user.user_id)
        return ctx

    raise HTTPException(
        status_code=401,
        detail="未登录。请提供 Authorization Bearer Token 或 X-API-Key。",
    )
