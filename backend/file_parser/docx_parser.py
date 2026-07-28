"""
DOCX（Word）文件解析器。

设计原因
--------
- DOCX 本质是 ZIP + XML，不能当纯文本读取
- python-docx 按文档顺序遍历段落，保留阅读顺序
- 输出统一 plain text，表格/图片暂不结构化（阶段一足够 RAG 使用）

依赖：python-docx（见 requirements.txt）
"""

from __future__ import annotations

import logging
from pathlib import Path

from docx import Document

from file_parser.parser import BaseFileParser, ParseResult, normalize_whitespace

logger = logging.getLogger(__name__)


class DocxParser(BaseFileParser):
    """从 Word .docx 提取段落文本。"""

    supported_extensions = frozenset({".docx"})
    file_type = "docx"

    def parse(self, path: str | Path) -> ParseResult:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"DOCX 文件不存在: {file_path}")

        if file_path.suffix.lower() != ".docx":
            raise ValueError(f"不是 DOCX 文件: {file_path}")

        logger.info("[DocxParser] 打开: %s", file_path.name)

        try:
            document = Document(str(file_path))
        except Exception as exc:
            raise ValueError(f"无法读取 DOCX 文件: {file_path.name}") from exc

        # 逐段落提取；跳过空段，减少无意义 chunk
        paragraphs: list[str] = []
        for para in document.paragraphs:
            cleaned = normalize_whitespace(para.text)
            if cleaned:
                paragraphs.append(cleaned)

        full_text = "\n\n".join(paragraphs)

        if not full_text.strip():
            logger.warning("[DocxParser] 文档无可见段落文本: %s", file_path.name)

        logger.info("[DocxParser] 共 %d 段, %d 字符", len(paragraphs), len(full_text))

        return self.build_result(file_path, full_text)
