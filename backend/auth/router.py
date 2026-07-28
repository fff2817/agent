"""Auth API — 注册 / 登录。"""

import logging

from fastapi import APIRouter, HTTPException

from auth.jwt_utils import create_access_token
from auth.user_store import get_user_store
from models.schemas import AuthResponse, LoginRequest, RegisterRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest) -> AuthResponse:
    store = get_user_store()
    try:
        user = store.create_user(request.username, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = create_access_token(user.user_id, user.username)
    logger.info("[Auth] 注册成功: %s", user.username)

    return AuthResponse(
        user_id=user.user_id,
        username=user.username,
        access_token=token,
        api_key=user.api_key,
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest) -> AuthResponse:
    store = get_user_store()
    user = store.get_by_username(request.username)
    if not user or not store.verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.user_id, user.username)
    logger.info("[Auth] 登录成功: %s", user.username)

    return AuthResponse(
        user_id=user.user_id,
        username=user.username,
        access_token=token,
        api_key=user.api_key,
    )
