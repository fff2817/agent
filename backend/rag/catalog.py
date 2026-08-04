"""
文档目录（Catalog）— 知识库路由用的文档级 metadata。

每个用户一份 catalog.json，与 FAISS chunk metadata 通过 doc_id 关联。
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.config import get_settings
from rag.doc_profile import build_document_profile, build_routing_text, infer_file_type
from rag.embedder import embed_text

logger = logging.getLogger(__name__)

CATALOG_FILENAME = "catalog.json"


@dataclass
class DocumentRecord:
    """单个逻辑文档的元数据。"""

    doc_id: str
    user_id: str
    filename: str
    file_type: str
    storage_path: str
    content_hash: str
    uploaded_at: str
    status: str = "ready"
    page_count: int = 1
    char_count: int = 0
    title: str = ""
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    doc_type: str = "other"
    chunk_count: int = 0
    embedding_model: str = ""
    summary_embedding: list[float] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DocumentRecord:
        return cls(
            doc_id=data["doc_id"],
            user_id=data["user_id"],
            filename=data["filename"],
            file_type=data["file_type"],
            storage_path=data["storage_path"],
            content_hash=data["content_hash"],
            uploaded_at=data["uploaded_at"],
            status=data.get("status", "ready"),
            page_count=int(data.get("page_count", 1)),
            char_count=int(data.get("char_count", 0)),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            topics=list(data.get("topics") or []),
            keywords=list(data.get("keywords") or []),
            doc_type=data.get("doc_type", "other"),
            chunk_count=int(data.get("chunk_count", 0)),
            embedding_model=data.get("embedding_model", ""),
            summary_embedding=data.get("summary_embedding"),
        )


@dataclass
class DocumentBrief:
    """Agent / API 可见的轻量文档摘要。"""

    doc_id: str
    filename: str
    title: str
    topics: list[str]
    doc_type: str
    char_count: int
    uploaded_at: str
    one_line: str

    def format_line(self) -> str:
        topics_str = ", ".join(self.topics[:5]) if self.topics else "—"
        return f"[{self.doc_id[:8]}] {self.filename} — {self.title} | 主题: {topics_str}"


class DocumentCatalog:
    """按用户隔离的文档目录读写。"""

    def __init__(self, user_id: str, store_dir: str | Path | None = None) -> None:
        settings = get_settings()
        base = Path(store_dir or settings.rag_store_path) / user_id
        base.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id
        self.catalog_path = base / CATALOG_FILENAME
        self._records: dict[str, DocumentRecord] = {}
        if self.catalog_path.exists():
            self.load()

    @property
    def count(self) -> int:
        return len(self._records)

    def load(self) -> None:
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        docs = raw.get("documents", [])
        self._records = {item["doc_id"]: DocumentRecord.from_dict(item) for item in docs}
        logger.info("[Catalog] 加载 %d 条文档记录 user=%s", len(self._records), self.user_id)

    def save(self) -> None:
        payload = {
            "version": 1,
            "user_id": self.user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "documents": [r.to_dict() for r in self._records.values()],
        }
        self.catalog_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[Catalog] 已保存 %d 条文档记录", len(self._records))

    def upsert(self, record: DocumentRecord) -> None:
        self._records[record.doc_id] = record
        self.save()

    def get(self, doc_id: str) -> DocumentRecord | None:
        return self._records.get(doc_id)

    def list_all(self) -> list[DocumentRecord]:
        return list(self._records.values())

    def list_ready(self) -> list[DocumentRecord]:
        return [r for r in self._records.values() if r.status == "ready"]

    def list_briefs(self) -> list[DocumentBrief]:
        briefs: list[DocumentBrief] = []
        for record in sorted(self.list_ready(), key=lambda r: r.uploaded_at, reverse=True):
            one_line = record.summary.strip()
            if len(one_line) > 80:
                one_line = one_line[:80] + "..."
            if not one_line:
                one_line = record.title or record.filename
            briefs.append(
                DocumentBrief(
                    doc_id=record.doc_id,
                    filename=record.filename,
                    title=record.title or record.filename,
                    topics=record.topics,
                    doc_type=record.doc_type,
                    char_count=record.char_count,
                    uploaded_at=record.uploaded_at,
                    one_line=one_line,
                )
            )
        return briefs

    def resolve_filenames(self, filenames: list[str]) -> list[str]:
        """把文件名解析为 doc_id（精确匹配 filename，忽略大小写）。"""
        name_map = {r.filename.lower(): r.doc_id for r in self.list_ready()}
        resolved: list[str] = []
        for name in filenames:
            key = name.strip().lower()
            doc_id = name_map.get(key)
            if doc_id:
                resolved.append(doc_id)
        return resolved

    def get_by_filename(self, filename: str) -> DocumentRecord | None:
        key = filename.strip().lower()
        for record in self._records.values():
            if record.filename.lower() == key:
                return record
        return None

    def remove(self, doc_id: str) -> DocumentRecord | None:
        record = self._records.pop(doc_id, None)
        if record is not None:
            self.save()
            logger.info("[Catalog] 已删除文档记录 doc_id=%s file=%s", doc_id, record.filename)
        return record

    def remove_by_filename(self, filename: str) -> DocumentRecord | None:
        record = self.get_by_filename(filename)
        if record is None:
            return None
        return self.remove(record.doc_id)

_catalogs: dict[str, DocumentCatalog] = {}


def get_document_catalog(user_id: str) -> DocumentCatalog:
    if user_id not in _catalogs:
        _catalogs[user_id] = DocumentCatalog(user_id)
    return _catalogs[user_id]


def sync_catalog_from_store(user_id: str) -> int:
    """
    从已有 FAISS chunk metadata 重建 catalog，并为旧 chunk 补 doc_id。

    兼容路由功能上线前已入库的文档。
    """
    from rag.vectorstore import get_rag_vector_store

    catalog = get_document_catalog(user_id)
    if catalog.count > 0:
        return 0

    store = get_rag_vector_store(user_id)
    if store.count == 0:
        return 0

    metas = store.get_chunk_metadata()
    by_source: dict[str, list[int]] = {}
    for idx, meta in enumerate(metas):
        if meta.get("doc_id"):
            continue
        source = meta.get("source", "unknown")
        by_source.setdefault(source, []).append(idx)

    if not by_source:
        return 0

    settings = get_settings()
    created = 0
    now = datetime.now(timezone.utc).isoformat()

    for source, indices in by_source.items():
        doc_id = str(uuid.uuid4())
        texts = [metas[i]["text"] for i in indices]
        full_text = "\n".join(texts)
        file_type = infer_file_type(Path(source).suffix)
        profile = build_document_profile(full_text, source, file_type=file_type)
        routing_text = build_routing_text(
            title=str(profile["title"]),
            summary=str(profile["summary"]),
            topics=list(profile["topics"]),
            keywords=list(profile["keywords"]),
            filename=source,
        )
        try:
            summary_embedding = embed_text(routing_text)
            embedding_model = settings.embedding_model
        except Exception as exc:
            logger.warning("[Catalog] 同步时 embedding 失败，跳过向量: %s", exc)
            summary_embedding = None
            embedding_model = ""

        store.assign_doc_id_to_chunks(indices, doc_id)
        record = DocumentRecord(
            doc_id=doc_id,
            user_id=user_id,
            filename=source,
            file_type=file_type,
            storage_path=source,
            content_hash="",
            uploaded_at=now,
            status="ready",
            page_count=max(metas[i].get("page", 1) for i in indices),
            char_count=len(full_text),
            title=str(profile["title"]),
            summary=str(profile["summary"]),
            topics=list(profile["topics"]),
            keywords=list(profile["keywords"]),
            doc_type=str(profile["doc_type"]),
            chunk_count=len(indices),
            embedding_model=embedding_model,
            summary_embedding=summary_embedding,
        )
        catalog._records[record.doc_id] = record
        created += 1

    if created:
        store.save()
        catalog.save()
        logger.info("[Catalog] 从 FAISS 同步 %d 条文档记录 user=%s", created, user_id)
    return created


def ensure_catalog_synced(user_id: str) -> None:
    """catalog 为空但向量库有数据时，自动同步。"""
    sync_catalog_from_store(user_id)
