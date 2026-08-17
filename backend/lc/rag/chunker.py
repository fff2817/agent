"""
文本切分模块（Chunker）。

教学要点 — 为什么需要 Chunk?

    1. LLM 上下文有限 — 不能把整本 PDF 塞进一次提问
    2. 检索要精准     — 用户问「报销流程」，应命中相关段落，而非整本书
    3. Embedding 有最优长度 — 太短语义不全，太长噪音多

Chunk Size 怎么选?（见模块末尾 CHUNK_SIZE_GUIDE）

本模块采用「滑动窗口 + 重叠（Overlap）」策略:
    - 在每一页内按固定字符数切分
    - 相邻块之间重叠 overlap 个字符，避免一句话被拦腰截断
"""

import logging

from lc.rag.types import ExtractedDocument, PageText, TextChunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunk 参数选择指南（教学用，也可通过 config 覆盖）
# ---------------------------------------------------------------------------
# | 场景              | chunk_size | overlap | 说明                    |
# |-------------------|------------|---------|-------------------------|
# | 通用中文文档      | 400~600    | 50~100  | 约 200~300 汉字         |
# | 技术文档/代码     | 800~1200   | 100~200 | 保留更多上下文          |
# | FAQ / 短段落      | 200~400    | 30~50   | 块小、检索更准          |
# | 英文文档          | 500~1000   | 50~100  | 英文信息密度与中文不同  |
#
# 原则:
#   - overlap 约为 chunk_size 的 10%~20%
#   - 先用 500/50 跑通，再根据检索效果调
# ---------------------------------------------------------------------------

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50


def chunk_document(
    document: ExtractedDocument,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    doc_id: str = "",
) -> list[TextChunk]:
    """
    把 ExtractedDocument 切分为 TextChunk 列表。

    策略: 逐页切分 — 每个 chunk 明确归属某一页，便于 RAG 回答时引用页码。

    参数:
        document:      Loader 的输出
        chunk_size:    每块最大字符数
        chunk_overlap: 相邻块重叠字符数（必须 < chunk_size）

    返回:
        TextChunk 列表
    """
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) 必须小于 chunk_size ({chunk_size})"
        )

    logger.info(
        "[Chunker] 开始切分: source=%s, chunk_size=%d, overlap=%d",
        document.source,
        chunk_size,
        chunk_overlap,
    )

    all_chunks: list[TextChunk] = []
    global_id = 0

    for page in document.pages:
        if not page.text.strip():
            logger.info("[Chunker] 跳过空页: page=%d", page.page)
            continue

        page_chunks = _chunk_single_page(
            page=page,
            source=document.source,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            start_id=global_id,
            doc_id=doc_id,
        )

        all_chunks.extend(page_chunks)
        global_id += len(page_chunks)

        logger.info(
            "[Chunker] 第 %d 页 → %d 个 chunk",
            page.page,
            len(page_chunks),
        )

    logger.info("[Chunker] 切分完成, 共 %d 个 chunk", len(all_chunks))
    return all_chunks


def _chunk_single_page(
    page: PageText,
    source: str,
    chunk_size: int,
    chunk_overlap: int,
    start_id: int,
    doc_id: str = "",
) -> list[TextChunk]:
    """
    对单页文本做滑动窗口切分。

    滑动窗口示意（chunk_size=8, overlap=2）:

        文本: "ABCDEFGHIJKLMNOP"
        块1:  "ABCDEFGH"     [0:8]
        块2:      "GHIJKLMN"  [6:14]  ← 从 8-2=6 开始，与块1 重叠 "GH"
        块3:          "MNOP"  ...
    """
    text = page.text
    chunks: list[TextChunk] = []
    start = 0
    local_id = start_id

    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()

        if piece:
            chunks.append(
                TextChunk(
                    chunk_id=local_id,
                    text=piece,
                    source=source,
                    page=page.page,
                    char_count=len(piece),
                    doc_id=doc_id,
                )
            )
            local_id += 1

        # 已到文本末尾，结束
        if end >= len(text):
            break

        # 下一步起点 = 当前块末尾 - overlap（形成重叠）
        start = end - chunk_overlap

    return chunks


def chunk_plain_text(
    text: str,
    source: str = "inline",
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    doc_id: str = "",
) -> list[TextChunk]:
    """
    直接对字符串切分（demo / 测试用）。

    视为单页文档，与 load_text_file + chunk_document 效果一致。
    """
    doc = ExtractedDocument(
        source=source,
        pages=[PageText(page=1, text=text)],
        full_text=text,
    )
    return chunk_document(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap, doc_id=doc_id)
