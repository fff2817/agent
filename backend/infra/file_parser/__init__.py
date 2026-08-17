"""
file_parser — 多格式文件解析包。

对外 API
--------
- ``parse_file(path)``       统一解析入口
- ``register_parser(parser)`` 注册自定义 Parser
- ``get_supported_extensions()`` 当前支持的扩展名

设计原则：与 ``rag/`` 流水线解耦；接入 RAG 时在上层做 ParseResult → ExtractedDocument 适配即可。
"""

from infra.file_parser.parser import (
    BaseFileParser,
    FileMetadata,
    ParseResult,
    get_supported_extensions,
    parse_file,
    register_parser,
)

__all__ = [
    "BaseFileParser",
    "FileMetadata",
    "ParseResult",
    "get_supported_extensions",
    "parse_file",
    "register_parser",
]
