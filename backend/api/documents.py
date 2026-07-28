"""
文档上传 API — 多格式入库入口。

POST /documents/upload  接收 PDF/DOCX/TXT/MD → 保存 → 切分 → Embedding → FAISS（按用户隔离）
GET  /documents         列出当前用户已上传文件
"""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth.context import UserContext
from auth.dependencies import get_current_user
from core.config import get_settings
from file_parser.parser import get_supported_extensions
from models.schemas import DocumentItemSchema, DocumentListResponse, DocumentUploadResponse
from rag.ingest import ingest_file
from rag.vectorstore import get_rag_vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_SUFFIXES = get_supported_extensions()

_SUFFIX_TO_TYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
}


def _file_type_from_suffix(suffix: str) -> str:
    return _SUFFIX_TO_TYPE.get(suffix.lower(), "unknown")


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
    for path in sorted(uploads_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
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


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
) -> DocumentUploadResponse:
    """上传文档并入库到当前用户的 FAISS 向量库。支持 PDF、DOCX、TXT、MD。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        supported = ", ".join(sorted(ALLOWED_SUFFIXES))
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
