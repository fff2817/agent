"""多用户 API 集成测试。"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("CONVERSATIONS_DB_PATH", str(tmp_path / "conversations.db"))
    monkeypatch.setenv("MEMORY_STORE_PATH", str(tmp_path / "memory"))
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag"))

    from core.config import get_settings

    get_settings.cache_clear()

    # 清除单例缓存
    import infra.session_store as ss
    import auth.user_store as us
    from conversation.store import reset_conversation_store

    ss._store = ss.SessionStore(db_path=tmp_path / "sessions.db")
    us._store = us.UserStore(db_path=tmp_path / "users.db")
    reset_conversation_store()

    from main import app

    yield TestClient(app)

    reset_conversation_store()
    get_settings.cache_clear()


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_and_login(client: TestClient):
    reg = client.post("/auth/register", json={"username": "testuser", "password": "pass1234"})
    assert reg.status_code == 200
    data = reg.json()
    assert data["user_id"]
    assert data["access_token"]
    assert data["api_key"].startswith("sk-")

    login = client.post("/auth/login", json={"username": "testuser", "password": "pass1234"})
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_memory_overview_dev_mode(client: TestClient):
    resp = client.get("/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"]
    assert body["session_id"]


def test_two_users_isolated_sessions(client: TestClient):
    """两个 X-User-Id 用户拥有独立 session。"""
    user_a = "user-aaa"
    user_b = "user-bbb"

    resp_a = client.get("/memory", headers={"X-User-Id": user_a})
    resp_b = client.get("/memory", headers={"X-User-Id": user_b})

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert resp_a.json()["user_id"] == user_a
    assert resp_b.json()["user_id"] == user_b
    assert resp_a.json()["session_id"] != resp_b.json()["session_id"]
