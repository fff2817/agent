"""
纯文本 (.txt) 文件解析器。

设计原因
--------
- 最简单的格式，整文件即内容
- 编码不确定（UTF-8 / GBK），使用 ``read_text_with_fallback`` 统一处理
- metadata.type 为 ``txt``，与 Markdown 区分，便于统计与过滤

与 Markdown 的关系：
- .txt 走本 Parser；.md 走 MarkdownParser（type 不同，便于后续 MD 专用处理）
"""

from __future__ import annotations

import logging
from pathlib import Path

from file_parser.parser import (
    BaseFileParser,
    ParseResult,
    normalize_whitespace,
    read_text_with_fallback,
)

logger = logging.getLogger(__name__)


class TxtParser(BaseFileParser):
    """读取 UTF-8 / GBK 纯文本文件。"""

    supported_extensions = frozenset({".txt"})
    file_type = "txt"

    def parse(self, path: str | Path) -> ParseResult:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"文本文件不存在: {file_path}")

        logger.info("[TxtParser] 读取: %s", file_path.name)

        raw = read_text_with_fallback(file_path)
        full_text = normalize_whitespace(raw)

        logger.info("[TxtParser] %d 字符", len(full_text))

        return self.build_result(file_path, full_text)
