"""
PDF 文件解析器。

设计原因
--------
- PDF 是二进制排版格式，必须用专用库（pypdf）按页抽取文本
- 与 ``rag/loader.load_pdf`` 使用相同库，但输出契约不同：
  * loader → ``ExtractedDocument``（含逐页结构，供现有 chunk_document 使用）
  * 本 Parser → 统一 ``ParseResult``（plain text + metadata）
- 二者并行存在，**不替换** loader，现有 RAG 入库路径零改动

局限：
- 仅适用于文字型 PDF；扫描版需 OCR Parser（未来扩展）
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

from file_parser.parser import BaseFileParser, ParseResult, normalize_whitespace

logger = logging.getLogger(__name__)


class PdfParser(BaseFileParser):
    """从 PDF 提取纯文本。"""

    supported_extensions = frozenset({".pdf"})
    file_type = "pdf"

    def parse(self, path: str | Path) -> ParseResult:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {file_path}")

        if file_path.suffix.lower() != ".pdf":
            raise ValueError(f"不是 PDF 文件: {file_path}")

        logger.info("[PdfParser] 打开: %s", file_path.name)

        # PdfReader 流式解析 PDF 结构，适合页数较多的文档
        reader = PdfReader(str(file_path))
        page_texts: list[str] = []

        for index, page in enumerate(reader.pages):
            page_number = index + 1
            raw = page.extract_text() or ""
            cleaned = normalize_whitespace(raw)
            page_texts.append(cleaned)
            logger.debug(
                "[PdfParser] 第 %d/%d 页, %d 字符",
                page_number,
                len(reader.pages),
                len(cleaned),
            )

        # 页与页之间空一行，保留「分页」对后续按页引用的潜在价值
        full_text = "\n\n".join(t for t in page_texts if t)

        if not full_text.strip():
            logger.warning("[PdfParser] 未提取到文本（可能是扫描版 PDF）: %s", file_path.name)

        return self.build_result(file_path, full_text)
