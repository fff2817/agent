"""知识库文档路由测试。"""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest

from infra.catalog import DocumentCatalog, DocumentRecord
from lc.rag.router import route_documents
from lc.rag.types import EmbeddedChunk, TextChunk
from infra.rag_vectorstore import FaissVectorStore


@pytest.fixture
def temp_rag_env(tmp_path: Path, monkeypatch):
    rag_root = tmp_path / "rag"
    rag_root.mkdir()
    monkeypatch.setenv("RAG_STORE_PATH", str(rag_root))
    monkeypatch.setenv("RAG_ROUTE_ENABLED", "true")
    monkeypatch.setenv("RAG_ROUTE_MIN_SCORE", "0.1")

    from core.config import get_settings

    get_settings.cache_clear()
    yield rag_root
    get_settings.cache_clear()


def _make_record(
    user_id: str,
    filename: str,
    topics: list[str],
    keywords: list[str],
    embedding: list[float],
    doc_type: str = "other",
) -> DocumentRecord:
    return DocumentRecord(
        doc_id=str(uuid.uuid4()),
        user_id=user_id,
        filename=filename,
        file_type="markdown",
        storage_path=f"/uploads/{filename}",
        content_hash="abc",
        uploaded_at="2026-01-01T00:00:00+00:00",
        title=Path(filename).stem,
        summary=f"关于 {', '.join(topics)} 的笔记",
        topics=topics,
        keywords=keywords,
        doc_type=doc_type,
        chunk_count=3,
        embedding_model="test",
        summary_embedding=embedding,
    )


def test_route_selects_faiss_notes(temp_rag_env, monkeypatch):
    user_id = "user-route"
    catalog = DocumentCatalog(user_id, store_dir=temp_rag_env / user_id)

    vec_faiss = [1.0, 0.0, 0.0]
    vec_req = [0.0, 1.0, 0.0]
    record_notes = _make_record(
        user_id,
        "AI笔记.md",
        topics=["FAISS", "向量检索"],
        keywords=["faiss", "embedding"],
        embedding=vec_faiss,
        doc_type="notes",
    )
    record_req = _make_record(
        user_id,
        "项目文档.docx",
        topics=["需求", "里程碑"],
        keywords=["需求", "功能"],
        embedding=vec_req,
        doc_type="requirements",
    )
    catalog._records = {
        record_notes.doc_id: record_notes,
        record_req.doc_id: record_req,
    }

    def fake_embed(text: str) -> list[float]:
        if "FAISS" in text or "faiss" in text.lower():
            return vec_faiss
        if "需求" in text:
            return vec_req
        return [0.5, 0.5, 0.0]

    monkeypatch.setattr("lc.rag.router.embed_text", fake_embed)

    result = route_documents("讲一下FAISS", user_id=user_id, catalog=catalog)
    assert record_notes.doc_id in result.selected_doc_ids
    assert not result.fallback_all

    result2 = route_documents("帮我总结项目需求", user_id=user_id, catalog=catalog)
    assert record_req.doc_id in result2.selected_doc_ids


def test_route_explicit_filename(temp_rag_env):
    user_id = "user-filename"
    catalog = DocumentCatalog(user_id, store_dir=temp_rag_env / user_id)
    record = _make_record(
        user_id,
        "员工手册.pdf",
        topics=["报销"],
        keywords=["报销"],
        embedding=[0.1, 0.2, 0.3],
    )
    catalog._records = {record.doc_id: record}

    result = route_documents(
        "查一下",
        user_id=user_id,
        catalog=catalog,
        filenames=["员工手册.pdf"],
    )
    assert result.selected_doc_ids == [record.doc_id]
    assert result.method == "explicit_filenames"


def test_vectorstore_doc_id_filter(temp_rag_env):
    store = FaissVectorStore(store_dir=temp_rag_env / "filter-user")
    dim = 4
    doc_a = "doc-a-id"
    doc_b = "doc-b-id"

    for i, (doc_id, text) in enumerate(
        [
            (doc_a, "FAISS 向量检索教程"),
            (doc_b, "项目需求文档内容"),
        ]
    ):
        vec = np.zeros(dim, dtype=np.float32)
        vec[i] = 1.0
        store.add_embeddings(
            [
                EmbeddedChunk(
                    chunk=TextChunk(
                        chunk_id=i,
                        text=text,
                        source=f"{doc_id}.md",
                        page=1,
                        doc_id=doc_id,
                    ),
                    embedding=vec.tolist(),
                    model="test",
                    dimensions=dim,
                )
            ]
        )

    query = [1.0, 0.0, 0.0, 0.0]
    hits = store.search(query, top_k=1, doc_ids=[doc_a])
    assert len(hits) == 1
    assert hits[0].chunk.doc_id == doc_a
    assert "FAISS" in hits[0].chunk.text
