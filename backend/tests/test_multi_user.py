"""多用户 Memory 隔离测试。"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import numpy as np
import pytest

from auth.user_store import UserStore
from infra.session_store import SessionForbiddenError, SessionStore
from lc.memory.types import MemoryRecord, MemoryType
from infra.memory_vectorstore import clear_memory_store_cache, get_memory_vector_store
from infra.rag_vectorstore import clear_rag_store_cache, get_rag_vector_store


@pytest.fixture
def temp_dirs(tmp_path: Path):
    users_db = tmp_path / "users.db"
    sessions_db = tmp_path / "sessions.db"
    memory_root = tmp_path / "memory"
    rag_root = tmp_path / "rag"
    memory_root.mkdir()
    rag_root.mkdir()
    return {
        "users_db": users_db,
        "sessions_db": sessions_db,
        "memory_root": memory_root,
        "rag_root": rag_root,
    }


def test_user_register_and_login(temp_dirs):
    store = UserStore(db_path=temp_dirs["users_db"])
    user = store.create_user("alice", "password123")
    assert user.user_id
    assert user.api_key.startswith("sk-")

    fetched = store.get_by_username("alice")
    assert fetched is not None
    assert store.verify_password("password123", fetched.password_hash)
    assert not store.verify_password("wrong", fetched.password_hash)


def test_session_belongs_to_user(temp_dirs):
    session_store = SessionStore(db_path=temp_dirs["sessions_db"])
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())

    sid, session = session_store.get_or_create(None, user_a)
    assert session.user_id == user_a

    session_store.add_turn(sid, "hello", "hi there")
    assert session_store.get_turn_count(sid) == 1

    with pytest.raises(SessionForbiddenError):
        session_store.get_or_create(sid, user_b)


def test_memory_vector_store_per_user_isolation(temp_dirs, monkeypatch):
    monkeypatch.setenv("MEMORY_STORE_PATH", str(temp_dirs["memory_root"]))

    from core.config import get_settings

    get_settings.cache_clear()
    clear_memory_store_cache()

    user_a = "user-a"
    user_b = "user-b"
    store_a = get_memory_vector_store(user_a)
    store_b = get_memory_vector_store(user_b)

    dim = 8
    record_a = MemoryRecord(
        user_id=user_a,
        content="用户姓名：Alice",
        memory_type=MemoryType.IDENTITY,
        importance=0.9,
    )
    record_b = MemoryRecord(
        user_id=user_b,
        content="用户姓名：Bob",
        memory_type=MemoryType.IDENTITY,
        importance=0.9,
    )

    vec_a = np.random.rand(dim).astype(np.float32).tolist()
    vec_b = np.random.rand(dim).astype(np.float32).tolist()

    store_a.add_memory(record_a, vec_a, model="test")
    store_b.add_memory(record_b, vec_b, model="test")
    store_a.save()
    store_b.save()

    assert store_a.count == 1
    assert store_b.count == 1
    assert (temp_dirs["memory_root"] / user_a / "chroma.sqlite3").exists()
    assert (temp_dirs["memory_root"] / user_b / "chroma.sqlite3").exists()

    hits_a = store_a.search(vec_a, top_k=1)
    hits_b = store_b.search(vec_b, top_k=1)

    assert hits_a[0].record.content == "用户姓名：Alice"
    assert hits_b[0].record.content == "用户姓名：Bob"

    get_settings.cache_clear()


def test_rag_vector_store_per_user_isolation(temp_dirs, monkeypatch):
    monkeypatch.setenv("RAG_STORE_PATH", str(temp_dirs["rag_root"]))

    from core.config import get_settings
    from lc.rag.types import EmbeddedChunk, TextChunk

    get_settings.cache_clear()
    clear_rag_store_cache()

    user_a = "user-a"
    user_b = "user-b"
    store_a = get_rag_vector_store(user_a)
    store_b = get_rag_vector_store(user_b)

    dim = 8
    chunk_a = EmbeddedChunk(
        chunk=TextChunk(
            chunk_id="c1",
            text="Alice 的文档内容",
            source="a.pdf",
            page=1,
            char_count=10,
        ),
        embedding=np.random.rand(dim).astype(np.float32).tolist(),
        dimensions=dim,
        model="test",
    )
    chunk_b = EmbeddedChunk(
        chunk=TextChunk(
            chunk_id="c2",
            text="Bob 的文档内容",
            source="b.pdf",
            page=1,
            char_count=10,
        ),
        embedding=np.random.rand(dim).astype(np.float32).tolist(),
        dimensions=dim,
        model="test",
    )

    store_a.add_embeddings([chunk_a])
    store_b.add_embeddings([chunk_b])
    store_a.save()
    store_b.save()

    assert store_a.count == 1
    assert store_b.count == 1
    assert (temp_dirs["rag_root"] / user_a / "chroma.sqlite3").exists()
    assert (temp_dirs["rag_root"] / user_b / "chroma.sqlite3").exists()

    get_settings.cache_clear()


def test_auth_dependency_dev_mode(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    from core.config import get_settings

    get_settings.cache_clear()

    from auth.dependencies import get_current_user
    import asyncio

    ctx = asyncio.run(get_current_user(None, None, None))
    assert ctx.user_id
    assert ctx.auth_method == "dev_header"

    get_settings.cache_clear()
