"""
文档画像生成 — 入库时为路由构建 title / summary / topics / keywords。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from core.config import get_settings

_MD_HEADER = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_WORD = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,}")

_DOC_TYPE_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("requirements", re.compile(r"需求|requirement|spec|规格|功能列表", re.I)),
    ("manual", re.compile(r"手册|指南|guide|manual|操作说明", re.I)),
    ("notes", re.compile(r"笔记|note|学习|教程|tutorial", re.I)),
]

_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "是",
        "在",
        "和",
        "与",
        "或",
        "及",
        "等",
        "我们",
        "可以",
        "进行",
        "通过",
        "使用",
        "一个",
        "这个",
        "that",
        "the",
        "and",
        "for",
        "with",
    }
)


def compute_content_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def infer_file_type(suffix: str) -> str:
    mapping = {
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
    return mapping.get(suffix.lower(), "other")


def _extract_headers(text: str, limit: int = 8) -> list[str]:
    headers = [m.group(1).strip() for m in _MD_HEADER.finditer(text)]
    return headers[:limit]


def _top_terms(text: str, limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for word in _WORD.findall(text):
        key = word.lower()
        if key in _STOPWORDS or len(key) < 2:
            continue
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in ranked[:limit]]


def _infer_doc_type(filename: str, text: str, headers: list[str]) -> str:
    probe = f"{filename}\n{text[:500]}\n" + " ".join(headers)
    for doc_type, pattern in _DOC_TYPE_HINTS:
        if pattern.search(probe):
            return doc_type
    return "other"


def build_document_profile(
    full_text: str,
    filename: str,
    *,
    file_type: str = "other",
) -> dict[str, str | list[str]]:
    """
    从全文抽取路由用 metadata（纯规则，不依赖 LLM）。
    """
    settings = get_settings()
    max_chars = settings.rag_catalog_summary_max_chars

    title = Path(filename).stem
    headers = _extract_headers(full_text)
    if headers:
        title = headers[0]

    cleaned = re.sub(r"\s+", " ", full_text).strip()
    summary = cleaned[:max_chars]
    if len(cleaned) > max_chars:
        summary += "..."

    topics = headers[:6]
    keywords = _top_terms(full_text, limit=10)
    for item in topics:
        if item not in keywords:
            keywords.insert(0, item)
    keywords = keywords[:10]

    doc_type = _infer_doc_type(filename, full_text, headers)
    if doc_type == "requirements" and "需求" not in topics:
        topics = (topics + ["需求"])[:6]
    if file_type == "markdown" and doc_type == "other" and any(
        t.lower() in {"chroma", "rag", "embedding", "向量"} for t in keywords
    ):
        doc_type = "notes"

    return {
        "title": title,
        "summary": summary,
        "topics": topics,
        "keywords": keywords,
        "doc_type": doc_type,
    }


def build_routing_text(
    *,
    title: str,
    summary: str,
    topics: list[str],
    keywords: list[str],
    filename: str,
) -> str:
    """拼接用于 summary embedding 的文本。"""
    parts = [title, filename]
    if topics:
        parts.append("主题: " + ", ".join(topics[:8]))
    if keywords:
        parts.append("关键词: " + ", ".join(keywords[:10]))
    if summary:
        parts.append(summary[:300])
    return "\n".join(p for p in parts if p)
