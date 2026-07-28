"""
PDF 文本提取模块（Loader）。

教学要点 — 这一步在 RAG 流水线中的位置:

    PDF 文件  →  【Loader 提取文本】  →  纯文本  →  Chunker 切分  →  Embedding

为什么需要单独一个 Loader?
    - PDF 是二进制格式，LLM 和向量库都不能直接读
    - 提取逻辑（库选型、编码、按页拆分）与切分逻辑解耦，方便测试和替换

本模块使用 pypdf 库:
    - 纯 Python、轻量、无系统依赖
    - 适合文字型 PDF；扫描版 PDF（图片）需要 OCR，不在本模块范围
"""

import logging
from pathlib import Path

from pypdf import PdfReader

from rag.types import ExtractedDocument, PageText

logger = logging.getLogger(__name__)


def load_pdf(pdf_path: str | Path) -> ExtractedDocument:
    """
    从 PDF 文件提取文本，按页返回结构化结果。

    参数:
        pdf_path: PDF 文件路径

    返回:
        ExtractedDocument — 含 source、pages、full_text

    异常:
        FileNotFoundError: 文件不存在
        ValueError:        不是 .pdf 或无法读取
    """
    path = Path(pdf_path)

    # --- Step 1: 校验文件 ---
    if not path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"不是 PDF 文件: {path}")

    logger.info("[Loader] Step 1 — 打开 PDF: %s", path.name)

    # --- Step 2: 用 pypdf 读取 ---
    # PdfReader 解析 PDF 结构，不会把整个文件读进内存的一次性字符串
    reader = PdfReader(str(path))
    total_pages = len(reader.pages)

    logger.info("[Loader] Step 2 — 共 %d 页", total_pages)

    # --- Step 3: 逐页提取文本 ---
    pages: list[PageText] = []

    for index, page in enumerate(reader.pages):
        # PDF 页码通常从 1 开始显示，这里与之一致
        page_number = index + 1

        # extract_text() 把该页排版后的文字抽出来
        # 注意: 复杂排版、表格、多栏可能提取顺序混乱，这是 PDF 提取的通用局限
        raw_text = page.extract_text() or ""

        # 清理多余空白，便于后续切分
        cleaned = _normalize_whitespace(raw_text)

        pages.append(PageText(page=page_number, text=cleaned))

        logger.info(
            "[Loader] Step 3 — 第 %d/%d 页, 提取 %d 字符",
            page_number,
            total_pages,
            len(cleaned),
        )

    # --- Step 4: 拼接 full_text（可选，供需要整文档处理的场景） ---
    full_text = "\n\n".join(p.text for p in pages if p.text)

    logger.info("[Loader] Step 4 — 提取完成, 总字符数=%d", len(full_text))

    return ExtractedDocument(
        source=path.name,
        pages=pages,
        full_text=full_text,
    )


def load_text_file(text_path: str | Path) -> ExtractedDocument:
    """
    从纯文本文件加载（用于没有 PDF 时的测试/demo）。

    整文件视为「第 1 页」，接口与 load_pdf 一致，Chunker 可复用。
    """
    path = Path(text_path)
    if not path.exists():
        raise FileNotFoundError(f"文本文件不存在: {path}")

    content = path.read_text(encoding="utf-8")
    cleaned = _normalize_whitespace(content)

    logger.info("[Loader] 读取文本文件: %s, %d 字符", path.name, len(cleaned))

    return ExtractedDocument(
        source=path.name,
        pages=[PageText(page=1, text=cleaned)],
        full_text=cleaned,
    )


def _normalize_whitespace(text: str) -> str:
    """
    规范化空白字符。

    - 行内多个空格合并为一个
    - 去掉首尾空白
    - 保留换行（段落边界对切分有帮助）
    """
    lines = [line.strip() for line in text.splitlines()]
    # 去掉空行过多的情况，保留段落感
    return "\n".join(line for line in lines if line)
