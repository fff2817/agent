"""
Embedding 模块 — 把文本变成向量（一串数字）。

教学要点 — 什么是向量?

    文本（人类能读的）          向量（机器用来比较的）
    ─────────────────          ───────────────────────
    "苹果手机"          →       [0.12, -0.45, 0.88, 0.03, ...]
    "iPhone"            →       [0.19, -0.42, 0.85, 0.01, ...]  ← 与上一条很接近
    "今天下雨"          →       [0.91,  0.22, -0.11, ...]       ← 与上两条较远

    · 向量 = 一组有序浮点数，长度叫「维度」（如 1536）
    · 意思相近的文本 → 向量在空间中距离更近
    · RAG 检索就是：把用户问题变成向量，找与之最接近的 chunk 向量

本模块使用 OpenAI 兼容的 Embeddings API:
    - 官方 OpenAI: text-embedding-3-small
    - 智谱等兼容服务: 在 .env 中配置 OPENAI_BASE_URL + EMBEDDING_MODEL
"""

import logging
import math
from typing import Any

from openai import OpenAI

from core.config import get_settings
from rag.types import EmbeddedChunk, TextChunk

logger = logging.getLogger(__name__)


def _build_client() -> OpenAI:
    """创建 OpenAI 兼容客户端（与 core/llm.py 相同配置源）。"""
    settings = get_settings()
    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**client_kwargs)


def embed_text(text: str) -> list[float]:
    """
    把单段文本转换为 embedding 向量。

    参数:
        text: 任意字符串（通常是一个 TextChunk 的内容）

    返回:
        浮点数列表，如 [0.12, -0.45, 0.88, ...]

    异常:
        ValueError: API Key 未配置或文本为空
    """
    text = text.strip()
    if not text:
        raise ValueError("embed_text: 文本不能为空")

    vectors = embed_texts([text])
    return vectors[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量把多段文本转换为向量（一次 API 调用，更高效）。

    参数:
        texts: 字符串列表

    返回:
        与 texts 等长的向量列表，顺序一一对应
    """
    settings = get_settings()

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    cleaned = [t.strip() for t in texts]
    if not cleaned or any(not t for t in cleaned):
        raise ValueError("embed_texts: 列表不能为空，且不能含空字符串")

    client = _build_client()
    model = settings.embedding_model

    logger.info("[Embedding] 请求向量化: model=%s, 条数=%d", model, len(cleaned))

    response = client.embeddings.create(
        model=model,
        input=cleaned,
    )

    # API 按 index 排序返回，确保顺序与 input 一致
    sorted_data = sorted(response.data, key=lambda item: item.index)
    vectors = [item.embedding for item in sorted_data]

    dim = len(vectors[0]) if vectors else 0
    logger.info("[Embedding] 完成: 维度=%d, 共 %d 条向量", dim, len(vectors))

    return vectors


def embed_chunks(chunks: list[TextChunk]) -> list[EmbeddedChunk]:
    """
    为 TextChunk 列表批量生成向量，并包装为 EmbeddedChunk。

    这是 RAG 入库前的标准步骤:
        PDF → Loader → Chunker → 【Embedder】→ 向量库

    参数:
        chunks: chunker.py 的输出

    返回:
        EmbeddedChunk 列表（chunk 原文 + embedding 向量）
    """
    if not chunks:
        return []

    settings = get_settings()
    texts = [c.text for c in chunks]
    vectors = embed_texts(texts)

    results: list[EmbeddedChunk] = []
    for chunk, vector in zip(chunks, vectors):
        results.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding=vector,
                model=settings.embedding_model,
                dimensions=len(vector),
            )
        )
        logger.info(
            "[Embedding] Chunk #%d → 向量维度=%d, 文本预览=%r",
            chunk.chunk_id,
            len(vector),
            chunk.text[:40],
        )

    return results


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    计算两个向量的余弦相似度（教学 / 调试用）。

    返回值范围 [-1, 1]:
        接近 1  →  方向几乎相同，语义非常相近
        接近 0  →  无关
        接近 -1 →  相反（文本 embedding 中较少见）

    RAG 检索本质就是在向量库里找与「问题向量」余弦相似度最高的 chunk 向量。
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("两个向量维度必须相同")

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def format_vector_preview(vector: list[float], head: int = 8, tail: int = 4) -> str:
    """
    把长向量格式化为易读的预览字符串（用于打印/demo）。

    示例: [0.1234, -0.4567, ... (共1536维) ..., 0.0123, -0.0456]
    """
    if not vector:
        return "[]"

    dim = len(vector)
    if dim <= head + tail:
        parts = ", ".join(f"{v:.4f}" for v in vector)
        return f"[{parts}]"

    head_part = ", ".join(f"{v:.4f}" for v in vector[:head])
    tail_part = ", ".join(f"{v:.4f}" for v in vector[-tail:])
    return f"[{head_part}, ... (共{dim}维) ..., {tail_part}]"
