"""
Markdown (.md / .markdown) 文件解析器。

设计原因
--------
- 阶段一：Markdown 当「带标记的纯文本」入库 RAG
  Embedding 模型对 ``# 标题``、``**bold**`` 仍有一定语义理解
- 与 .txt 分开注册的原因：
  * metadata.type = ``markdown``，前端/API 可展示不同图标
  * 未来可在此 Parser 内做 AST 分节（按 ``#`` 切 section）而不改接口

阶段二扩展点（本文件内改即可）：
- 剥离 YAML front matter
- 按标题层级生成 section metadata
"""

from __future__ import annotations

import logging
from pathlib import Path

from infra.file_parser.parser import (
    BaseFileParser,
    ParseResult,
    normalize_whitespace,
    read_text_with_fallback,
)

logger = logging.getLogger(__name__)


class MarkdownParser(BaseFileParser):
    """读取 Markdown 源文件为 plain text。"""

    supported_extensions = frozenset({".md", ".markdown"})
    file_type = "markdown"

    def parse(self, path: str | Path) -> ParseResult:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"Markdown 文件不存在: {file_path}")

        logger.info("[MarkdownParser] 读取: %s", file_path.name)

        raw = read_text_with_fallback(file_path)
        # 阶段一保留 MD 标记；仅做空白规范化
        full_text = normalize_whitespace(raw)

        logger.info("[MarkdownParser] %d 字符", len(full_text))

        return self.build_result(file_path, full_text)
