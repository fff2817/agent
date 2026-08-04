"""Conversation API 集成测试（不调用 LLM）。"""

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
    monkeypatch.setenv("CONVERSATIONS_DB_PATH", str(tmp_path / "conversations.db"))
    monkeypatch.setenv("MEMORY_STORE_PATH", str(tmp_path / "memory"))
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag"))

    from core.config import get_settings

    get_settings.cache_clear()

    from conversation.store import reset_conversation_store

    reset_conversation_store()

    from main import app

    yield TestClient(app)

    reset_conversation_store()
    get_settings.cache_clear()


def _register(client: TestClient) -> dict:
    resp = client.post(
        "/auth/register",
        json={"username": f"c_{uuid.uuid4().hex[:8]}", "password": "pass1234"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_conversation_crud(client: TestClient):
    user = _register(client)
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    created = client.post("/conversations", headers=headers)
    assert created.status_code == 200, created.text
    cid = created.json()["conversation_id"]
    assert created.json()["title"] == "新对话"

    listed = client.get("/conversations", headers=headers)
    assert listed.status_code == 200
    ids = [c["conversation_id"] for c in listed.json()["conversations"]]
    assert cid in ids

    # 直接写入一轮，模拟 chat 持久化
    from conversation.store import get_conversation_store

    store = get_conversation_store()
    store.append_turn(cid, user["user_id"], "你好啊助手", "你好，有什么可以帮你？")

    detail = client.get(f"/conversations/{cid}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["title"].startswith("你好啊助手")
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"

    renamed = client.patch(
        f"/conversations/{cid}",
        headers=headers,
        json={"title": "问候"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "问候"

    deleted = client.delete(f"/conversations/{cid}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/conversations/{cid}", headers=headers).status_code == 404
