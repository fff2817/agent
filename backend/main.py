import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.chat import router as chat_router
from api.conversations import router as conversations_router
from api.documents import router as documents_router
from api.eval import router as eval_router
from api.memory import router as memory_router
from api.rag import router as rag_router
from auth.router import router as auth_router
from core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)

_cors_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]
if not _cors_origins:
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(documents_router)
app.include_router(rag_router)
app.include_router(eval_router)
app.include_router(memory_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _mount_frontend() -> None:
    if not settings.serve_frontend or not _FRONTEND_DIST.is_dir():
        return

    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        # 避免吞掉后端 API（否则非 GET 会变成 405）
        api_prefixes = (
            "auth/",
            "chat",
            "conversations",
            "documents",
            "rag/",
            "memory",
            "eval",
            "health",
            "docs",
            "openapi.json",
            "redoc",
        )
        if full_path.startswith("api/") or any(
            full_path == p.rstrip("/") or full_path.startswith(p)
            for p in api_prefixes
        ):
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")


_mount_frontend()
