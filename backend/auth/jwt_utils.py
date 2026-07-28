"""JWT 签发与校验。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from core.config import get_settings


def create_access_token(user_id: str, username: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.auth_token_expire_hours)
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
