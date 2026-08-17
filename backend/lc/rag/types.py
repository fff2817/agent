"""
RAG 数据类型定义。

把「PDF 提取」和「Chunk 切分」各阶段的产物用清晰的数据结构表示，
方便后续 Embedding、向量库存储时携带 metadata（来源、页码等）。
"""

from dataclasses import dataclass, field


@dataclass
class PageText:
    """
    单页 PDF 提取结果。

    属性:
        page:  页码（从 1 开始，与 PDF 阅读器一致）
        text:  该页的纯文本内容
    """

    page: int
    text: str


@dataclass
class ExtractedDocument:
    """
    整份 PDF 提取结果。

    属性:
        source:    文件路径或文件名，用于溯源
        pages:     按页拆分的文本列表
        full_text: 全部页面拼接后的完整文本（页与页之间用换行连接）
    """

    source: str
    pages: list[PageText] = field(default_factory=list)
    full_text: str = ""


@dataclass
class TextChunk:
    """
    切分后的文本块 — RAG 检索的最小单元。

    向量数据库里存的不仅是 text，还有 metadata；
    这里用 dataclass 把「内容 + 来源信息」绑在一起。

    属性:
        chunk_id:   全局序号，从 0 开始
        text:       块内的文本内容
        source:     来自哪个文件
        page:       主要来自 PDF 哪一页（单页切分时明确；跨页时为起始页）
        char_count: 字符数，便于统计和调试
        doc_id:     所属文档 ID（知识库路由用）
    """

    chunk_id: int
    text: str
    source: str
    page: int
    char_count: int = 0
    doc_id: str = ""

    def __post_init__(self) -> None:
        if self.char_count == 0:
            self.char_count = len(self.text)


@dataclass
class EmbeddedChunk:
    """
    带向量的文本块 — Chunker + Embedder 之后的产物。

    属性:
        chunk:      原始 TextChunk（文本 + 页码 + 来源）
        embedding:  向量，浮点数列表
        model:      使用的 Embedding 模型名
        dimensions: 向量维度（如 1536）
    """

    chunk: TextChunk
    embedding: list[float]
    model: str
    dimensions: int


@dataclass
class SearchResult:
    """
    向量检索结果 — Top-K 中的单条。

    属性:
        rank:     排名，1 表示最相似
        score:    相似度分数（余弦相似度，越高越像）
        faiss_id: 内部序号 ID（字段名保留以兼容 API / Eval）
        chunk:    对应的文本块（原文 + 来源 + 页码）
    """

    rank: int
    score: float
    faiss_id: int
    chunk: TextChunk
