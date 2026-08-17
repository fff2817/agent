"""
文档入库流水线 — 文本/PDF → Chunk → Embedding → FAISS + Catalog。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.config import get_settings
from infra.catalog import DocumentRecord, get_document_catalog
from lc.rag.chunker import chunk_document, chunk_plain_text
from lc.rag.doc_profile import (
    build_document_profile,
    build_routing_text,
    compute_content_hash,
    infer_file_type,
)
from lc.llm.embeddings import embed_chunks, embed_text
from lc.rag.loader import load_pdf, load_text_file
from lc.rag.types import ExtractedDocument, PageText
from infra.rag_vectorstore import FaissVectorStore, get_rag_vector_store

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    doc_id: str
    chunk_count: int
    filename: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _register_catalog(
    *,
    user_id: str,
    doc_id: str,
    filename: str,
    storage_path: str,
    content_hash: str,
    document: ExtractedDocument,
    file_type: str,
    chunk_count: int,
    embedding_model: str,
) -> None:
    profile = build_document_profile(
        document.full_text or "",
        filename,
        file_type=file_type,
    )
    routing_text = build_routing_text(
        title=str(profile["title"]),
        summary=str(profile["summary"]),
        topics=list(profile["topics"]),
        keywords=list(profile["keywords"]),
        filename=filename,
    )
    summary_embedding = embed_text(routing_text)

    record = DocumentRecord(
        doc_id=doc_id,
        user_id=user_id,
        filename=filename,
        file_type=file_type,
        storage_path=storage_path,
        content_hash=content_hash,
        uploaded_at=_now_iso(),
        status="ready",
        page_count=len(document.pages) or 1,
        char_count=len(document.full_text or ""),
        title=str(profile["title"]),
        summary=str(profile["summary"]),
        topics=list(profile["topics"]),
        keywords=list(profile["keywords"]),
        doc_type=str(profile["doc_type"]),
        chunk_count=chunk_count,
        embedding_model=embedding_model,
        summary_embedding=summary_embedding,
    )
    get_document_catalog(user_id).upsert(record)


def ingest_text(
    text: str,
    source: str = "inline",
    *,
    user_id: str,
    store: FaissVectorStore | None = None,
    save: bool = True,
    doc_id: str | None = None,
) -> int:
    """把纯文本入库: 切分 → 向量化 → 写入 FAISS。"""
    doc_id = doc_id or str(uuid.uuid4())
    logger.info("[Ingest] 开始入库文本: source=%s, doc_id=%s, 长度=%d", source, doc_id, len(text))

    settings = get_settings()
    chunks = chunk_plain_text(
        text,
        source=source,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        doc_id=doc_id,
    )
    embedded = embed_chunks(chunks)

    vector_store = store or get_rag_vector_store(user_id)
    count = vector_store.add_embeddings(embedded)

    if save:
        vector_store.save()

    document = ExtractedDocument(
        source=source,
        pages=[PageText(page=1, text=text)],
        full_text=text,
    )
    _register_catalog(
        user_id=user_id,
        doc_id=doc_id,
        filename=source,
        storage_path=source,
        content_hash="inline",
        document=document,
        file_type=infer_file_type(Path(source).suffix or ".txt"),
        chunk_count=count,
        embedding_model=embedded[0].model if embedded else settings.embedding_model,
    )

    logger.info("[Ingest] 入库完成, 新增 %d 个 chunk, 索引总量=%d", count, vector_store.count)
    return count


def ingest_pdf(
    pdf_path: str | Path,
    *,
    user_id: str,
    store: FaissVectorStore | None = None,
    save: bool = True,
    doc_id: str | None = None,
    storage_path: str | None = None,
) -> int:
    path = Path(pdf_path)
    document = load_pdf(path)
    return ingest_document(
        document,
        user_id=user_id,
        store=store,
        save=save,
        doc_id=doc_id,
        filename=path.name,
        storage_path=storage_path or str(path),
        content_hash=compute_content_hash(path),
        file_type="pdf",
    )


def ingest_document(
    document: ExtractedDocument,
    *,
    user_id: str,
    store: FaissVectorStore | None = None,
    save: bool = True,
    doc_id: str | None = None,
    filename: str | None = None,
    storage_path: str | None = None,
    content_hash: str | None = None,
    file_type: str | None = None,
) -> int:
    """ExtractedDocument 入库。"""
    doc_id = doc_id or str(uuid.uuid4())
    filename = filename or document.source
    logger.info("[Ingest] 开始入库文档: %s (doc_id=%s)", filename, doc_id)

    settings = get_settings()
    chunks = chunk_document(
        document,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        doc_id=doc_id,
    )
    embedded = embed_chunks(chunks)

    vector_store = store or get_rag_vector_store(user_id)
    count = vector_store.add_embeddings(embedded)

    if save:
        vector_store.save()

    _register_catalog(
        user_id=user_id,
        doc_id=doc_id,
        filename=filename,
        storage_path=storage_path or filename,
        content_hash=content_hash or "",
        document=document,
        file_type=file_type or infer_file_type(Path(filename).suffix),
        chunk_count=count,
        embedding_model=embedded[0].model if embedded else settings.embedding_model,
    )

    logger.info("[Ingest] 入库完成, 新增 %d 个 chunk", count)
    return count


def ingest_text_file(
    text_path: str | Path,
    *,
    user_id: str,
    store: FaissVectorStore | None = None,
    save: bool = True,
) -> int:
    path = Path(text_path)
    document = load_text_file(path)
    return ingest_document(
        document,
        user_id=user_id,
        store=store,
        save=save,
        filename=path.name,
        storage_path=str(path),
        content_hash=compute_content_hash(path),
        file_type=infer_file_type(path.suffix),
    )


def ingest_file(
    file_path: str | Path,
    *,
    user_id: str,
    store: FaissVectorStore | None = None,
    save: bool = True,
) -> IngestResult:
    """通用文件入库：PDF 走逐页提取，其余格式走 file_parser。"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    doc_id = str(uuid.uuid4())

    if suffix == ".pdf":
        chunk_count = ingest_pdf(
            path,
            user_id=user_id,
            store=store,
            save=save,
            doc_id=doc_id,
            storage_path=str(path),
        )
        return IngestResult(doc_id=doc_id, chunk_count=chunk_count, filename=path.name)

    from infra.file_parser.parser import parse_file

    result = parse_file(path)
    text = result["text"]
    if not text.strip():
        raise ValueError(f"未能从文件中提取文本: {path.name}")

    document = ExtractedDocument(
        source=path.name,
        pages=[PageText(page=1, text=text)],
        full_text=text,
    )
    chunk_count = ingest_document(
        document,
        user_id=user_id,
        store=store,
        save=save,
        doc_id=doc_id,
        filename=path.name,
        storage_path=str(path),
        content_hash=compute_content_hash(path),
        file_type=infer_file_type(suffix),
    )
    return IngestResult(doc_id=doc_id, chunk_count=chunk_count, filename=path.name)
