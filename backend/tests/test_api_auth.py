"""Auth 与 Session 归属 API 集成测试。"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("MEMORY_STORE_PATH", str(tmp_path / "memory"))
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag"))

    from core.config import get_settings

    get_settings.cache_clear()

    from main import app

    yield TestClient(app)

    get_settings.cache_clear()


def _register(client: TestClient, username: str) -> dict:
    resp = client.post(
        "/auth/register",
        json={"username": username, "password": "pass1234"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_register_login_and_chat(client: TestClient):
    reg = _register(client, f"user_{uuid.uuid4().hex[:8]}")
    token = reg["access_token"]

    resp = client.post(
        "/chat",
        json={"message": "你好"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user_id"] == reg["user_id"]
    assert data["session_id"]
    assert data["response"]


def test_unauthenticated_chat_rejected(client: TestClient):
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 401


def test_session_cross_user_forbidden(client: TestClient):
    user_a = _register(client, f"alice_{uuid.uuid4().hex[:6]}")
    user_b = _register(client, f"bob_{uuid.uuid4().hex[:6]}")

    # 通过 /memory 创建 session，无需调用 LLM
    first = client.get(
        "/memory",
        headers={"Authorization": f"Bearer {user_a['access_token']}"},
    )
    assert first.status_code == 200, first.text
    session_id = first.json()["session_id"]

    second = client.post(
        "/chat",
        json={"message": "steal session", "session_id": session_id},
        headers={"Authorization": f"Bearer {user_b['access_token']}"},
    )
    assert second.status_code == 403


def test_memory_overview_requires_auth(client: TestClient):
    reg = _register(client, f"mem_{uuid.uuid4().hex[:6]}")
    resp = client.get(
        "/memory",
        headers={"Authorization": f"Bearer {reg['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user_id"] == reg["user_id"]
    assert data["session_id"]


def test_api_key_auth(client: TestClient):
    reg = _register(client, f"key_{uuid.uuid4().hex[:6]}")
    resp = client.post(
        "/chat",
        json={"message": "via api key"},
        headers={"X-API-Key": reg["api_key"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == reg["user_id"]
