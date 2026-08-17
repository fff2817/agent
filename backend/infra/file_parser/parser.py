"""
通用文件解析器 — 注册表 + 统一入口。

设计原因
--------
1. **独立一层，不侵入 RAG**
   现有 RAG 仍走 ``rag/loader.py`` → ``ingest_pdf``。本模块是并行能力，
   供后续多格式上传接入；今天不修改 ``ingest.py`` / ``chunker.py``。

2. **策略模式 + 注册表**
   每种文件格式一个 Parser 类；新增格式只需：
   - 新建 ``xxx_parser.py`` 继承 ``BaseFileParser``
   - 在 ``_register_default_parsers()`` 里 ``registry.register(...)``
   调用方始终使用 ``parse_file(path)``，无需改 if-elif 分支。

3. **统一返回契约**
   无论 PDF 还是 DOCX，下游（标准化、Chunk、Embedding）只消费::

       {"text": "...", "metadata": {"filename", "type", "size"}}

   避免 RAG 各层感知具体格式。

4. **按扩展名路由（阶段一）**
   与当前 ``documents.py`` 的 ``ALLOWED_SUFFIXES`` 策略一致；
   未来可在 ``parse_file`` 内插入 magic-byte 检测，Parser 接口不变。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 统一返回类型（与 API / 前端 JSON 字段一致）
# ---------------------------------------------------------------------------


class FileMetadata(TypedDict):
    """解析结果中的 metadata 字段。"""

    filename: str
    type: str
    size: str


class ParseResult(TypedDict):
    """
    所有 Parser 必须返回此结构。

    - text:     提取后的纯文本（已做基础空白规范化）
    - metadata: 文件溯源信息；size 为字节数的字符串，便于 JSON 序列化
    """

    text: str
    metadata: FileMetadata


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------


class BaseFileParser(ABC):
    """
    文件解析器抽象基类。

    子类只需实现 ``parse``；``build_result`` 负责填充统一 metadata，
    避免每个 Parser 重复写 filename / size 逻辑。
    """

    #: 支持的扩展名（含点，小写），例如 {".pdf"}
    supported_extensions: frozenset[str] = frozenset()

    #: 写入 metadata.type 的标识，例如 "pdf"、"docx"
    file_type: str = ""

    def supports(self, path: Path) -> bool:
        """根据扩展名判断是否由本 Parser 处理。"""
        return path.suffix.lower() in self.supported_extensions

    def build_result(self, path: Path, text: str) -> ParseResult:
        """
        组装统一返回结构。

        设计原因：filename / size 的读取方式对所有格式相同，
        集中在基类可减少重复与遗漏。
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        stat = path.stat()
        return {
            "text": text,
            "metadata": {
                "filename": path.name,
                "type": self.file_type,
                "size": str(stat.st_size),
            },
        }

    @abstractmethod
    def parse(self, path: str | Path) -> ParseResult:
        """从磁盘读取并提取文本，返回 ParseResult。"""


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------


class ParserRegistry:
    """
    扩展名 → Parser 实例 的映射表。

    使用注册表而非 giant if-elif 的原因：
    - 开闭原则：扩展新格式不修改 ``parse_file`` 核心逻辑
    - 可测试：可对单个 Parser 注入 mock 路径单独单测
    - 可配置：未来可按租户禁用某 Parser
    """

    def __init__(self) -> None:
        self._parsers: list[BaseFileParser] = []

    def register(self, parser: BaseFileParser) -> None:
        """注册一个 Parser；后注册的同扩展名 Parser 会覆盖先前的。"""
        self._parsers.append(parser)
        logger.debug(
            "[FileParser] 注册 %s, 扩展名=%s",
            parser.__class__.__name__,
            sorted(parser.supported_extensions),
        )

    def get_parser(self, path: str | Path) -> BaseFileParser:
        """
        按扩展名查找 Parser。

        遍历顺序为注册顺序；后注册者优先（便于测试时 override）。
        """
        path = Path(path)
        suffix = path.suffix.lower()

        for parser in reversed(self._parsers):
            if suffix in parser.supported_extensions:
                return parser

        supported = sorted(
            ext for p in self._parsers for ext in p.supported_extensions
        )
        raise ValueError(
            f"不支持的文件类型: {path.name!r} (扩展名 {suffix!r})。"
            f"当前支持: {', '.join(supported) or '(无)'}"
        )

    def supported_extensions(self) -> frozenset[str]:
        """返回所有已注册扩展名并集。"""
        exts: set[str] = set()
        for parser in self._parsers:
            exts.update(parser.supported_extensions)
        return frozenset(exts)


# 模块级单例：全应用共享同一套 Parser 配置
registry = ParserRegistry()


# ---------------------------------------------------------------------------
# 共享文本工具（刻意不 import rag.loader，保持模块独立）
# ---------------------------------------------------------------------------


def normalize_whitespace(text: str) -> str:
    """
    基础文本规范化。

    设计原因：
    - PDF/DOCX 提取常带多余空格与空行
    - 在 Parser 层统一处理，后续 RAG Chunker 无需感知来源格式
    - 保留换行以维持段落边界，利于按段切分
    """
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def read_text_with_fallback(path: Path, *, encodings: tuple[str, ...] = ("utf-8", "gbk")) -> str:
    """
    尝试多种编码读取纯文本文件。

    设计原因：中文 Windows 环境常见 GBK 编码的 .txt；
    先 UTF-8 再 GBK，覆盖大部分场景而无需 chardet 依赖。
    """
    raw_bytes = path.read_bytes()
    last_error: UnicodeDecodeError | None = None

    for encoding in encodings:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    raise ValueError(
        f"无法解码文本文件 {path.name}，已尝试编码: {', '.join(encodings)}"
    ) from last_error


# ---------------------------------------------------------------------------
# 默认 Parser 注册 & 统一入口
# ---------------------------------------------------------------------------


def _register_default_parsers() -> None:
    """
    注册内置 Parser。

    延迟 import 各 Parser 模块的原因：
    - 避免 circular import（各 parser 从 parser.py 导入基类）
    - 新增 Parser 时仅改此函数与新建文件，不动 registry 类本身
    """
    # 仅在首次需要时 import，减少启动开销
    from infra.file_parser.docx_parser import DocxParser
    from infra.file_parser.image_parser import ImageParser
    from infra.file_parser.markdown_parser import MarkdownParser
    from infra.file_parser.pdf_parser import PdfParser
    from infra.file_parser.txt_parser import TxtParser

    for parser in (
        PdfParser(),
        DocxParser(),
        TxtParser(),
        MarkdownParser(),
        ImageParser(),
    ):
        registry.register(parser)


_defaults_registered = False


def _ensure_defaults() -> None:
    global _defaults_registered
    if not _defaults_registered:
        _register_default_parsers()
        _defaults_registered = True


def parse_file(path: str | Path) -> ParseResult:
    """
    统一解析入口 — 根据扩展名自动选择 Parser。

    参数:
        path: 本地文件路径

    返回:
        ParseResult 字典

    异常:
        FileNotFoundError: 文件不存在
        ValueError:        不支持的扩展名或解析失败

    用法::

        result = parse_file("/data/report.pdf")
        print(result["text"])
        print(result["metadata"]["type"])  # "pdf"
    """
    _ensure_defaults()

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    parser = registry.get_parser(file_path)
    logger.info(
        "[FileParser] 解析文件: %s, 使用 %s",
        file_path.name,
        parser.__class__.__name__,
    )

    result = parser.parse(file_path)
    logger.info(
        "[FileParser] 解析完成: %s, type=%s, text_len=%d",
        file_path.name,
        result["metadata"]["type"],
        len(result["text"]),
    )
    return result


def register_parser(parser: BaseFileParser) -> None:
    """
    对外暴露的注册 API — 插件式扩展新格式。

    示例::

        registry.register(ExcelParser())
    """
    _ensure_defaults()
    registry.register(parser)


def get_supported_extensions() -> frozenset[str]:
    """返回当前支持的上传扩展名集合，供 API 层校验复用。"""
    _ensure_defaults()
    return registry.supported_extensions()
