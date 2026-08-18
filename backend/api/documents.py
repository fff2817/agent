"""
文档上传 API — 多格式入库入口。

POST   /documents/upload              接收文件 → 保存 → 切分 → Embedding → Chroma
GET    /documents                     列出当前用户已上传文件
POST   /documents/delete?filename=... 删除文件及对应向量 / catalog
"""

import logging
import shutil
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from auth.context import UserContext
from auth.dependencies import get_current_user
from core.config import get_settings
from infra.file_parser.parser import get_supported_extensions
from models.schemas import (
    DocumentItemSchema,
    DocumentListResponse,
    DocumentUploadResponse,
)
from infra.catalog import get_document_catalog
from lc.rag.ingest import ingest_file
from infra.rag_vectorstore import get_rag_vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_SUFFIX_TO_TYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
}


def _allowed_suffixes() -> frozenset[str]:
    return get_supported_extensions()


def _file_type_from_suffix(suffix: str) -> str:
    return _SUFFIX_TO_TYPE.get(suffix.lower(), "unknown")


def _safe_filename(name: str) -> str:
    """防止路径穿越，只保留文件名本身。"""
    return Path(unquote(name)).name


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    user: UserContext = Depends(get_current_user),
) -> DocumentListResponse:
    """列出当前用户 uploads 目录下的已上传文档。"""
    settings = get_settings()
    uploads_dir = Path(settings.rag_store_path) / user.user_id / "uploads"

    if not uploads_dir.exists():
        return DocumentListResponse(documents=[])

    documents: list[DocumentItemSchema] = []
    allowed = _allowed_suffixes()
    for path in sorted(uploads_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in allowed:
            continue
        stat = path.stat()
        documents.append(
            DocumentItemSchema(
                filename=path.name,
                file_type=_file_type_from_suffix(suffix),
                size=stat.st_size,
                uploaded_at=stat.st_mtime,
            )
        )

    return DocumentListResponse(documents=documents)


@router.post("/delete")
async def delete_document(
    filename: str = Query(..., min_length=1, description="要删除的文件名"),
    user: UserContext = Depends(get_current_user),
) -> dict:
    """删除已上传文档：磁盘文件 + catalog + Chroma chunks。"""
    safe_name = _safe_filename(filename)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Filename is required")

    settings = get_settings()
    uploads_dir = Path(settings.rag_store_path) / user.user_id / "uploads"
    file_path = uploads_dir / safe_name

    catalog = get_document_catalog(user.user_id)
    record = catalog.get_by_filename(safe_name)

    store = get_rag_vector_store(user.user_id)
    removed_chunks = store.remove_by_doc_id_or_source(
        doc_id=record.doc_id if record else None,
        source=safe_name,
    )

    if record:
        catalog.remove(record.doc_id)

    file_deleted = False
    if file_path.exists() and file_path.is_file():
        try:
            file_path.unlink()
            file_deleted = True
        except OSError as exc:
            logger.exception("[API/Docs] 删除文件失败: %s", safe_name)
            raise HTTPException(status_code=500, detail="Failed to delete file") from exc

    if not file_deleted and not record and removed_chunks == 0:
        raise HTTPException(status_code=404, detail=f"文档不存在: {safe_name}")

    logger.info(
        "[API/Docs] 已删除: user=%s file=%s chunks=%d catalog=%s file=%s",
        user.user_id,
        safe_name,
        removed_chunks,
        bool(record),
        file_deleted,
    )
    return {
        "status": "ok",
        "filename": safe_name,
        "chunks_removed": removed_chunks,
        "file_deleted": file_deleted,
    }


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
) -> DocumentUploadResponse:
    """上传文档并入库到当前用户的 Chroma 向量库。支持 PDF、DOCX、TXT、MD、图片。"""
    if not file.filename:
        logger.warning("[API/Docs] 上传缺少文件名（多为 multipart Content-Type 错误）")
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    allowed = _allowed_suffixes()
    if suffix not in allowed:
        supported = ", ".join(sorted(allowed))
        logger.warning(
            "[API/Docs] 不支持的文件类型: filename=%r suffix=%r",
            file.filename,
            suffix,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {supported}",
        )

    settings = get_settings()
    uploads_dir = Path(settings.rag_store_path) / user.user_id / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    dest_path = uploads_dir / safe_name

    logger.info("[API/Docs] 收到上传: user=%s file=%s", user.user_id, safe_name)

    try:
        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except OSError as exc:
        logger.exception("[API/Docs] 保存文件失败")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from exc
    finally:
        await file.close()

    try:
        result = ingest_file(dest_path, user_id=user.user_id)
        chunks_added = result.chunk_count
    except ValueError as exc:
        logger.warning("[API/Docs] 入库失败: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[API/Docs] 入库异常")
        detail = str(exc) or "Document ingest failed"
        raise HTTPException(status_code=502, detail=detail) from exc

    store = get_rag_vector_store(user.user_id)
    total_chunks = store.count

    logger.info(
        "[API/Docs] 入库成功: user=%s file=%s, 新增 %d chunks, 索引总量 %d",
        user.user_id,
        safe_name,
        chunks_added,
        total_chunks,
    )

    return DocumentUploadResponse(
        status="ok",
        doc_id=result.doc_id,
        filename=safe_name,
        file_type=_file_type_from_suffix(suffix),
        chunks_added=chunks_added,
        total_chunks=total_chunks,
    )
