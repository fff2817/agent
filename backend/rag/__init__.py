"""
RAG 模块 — 检索增强生成。

完整流水线:
    入库: Loader → Chunker → Embedder → FAISS (ingest)
    问答: 问题 → Embedding → FAISS → Top-K → Prompt → LLM (rag_ask)
"""

from rag.catalog import DocumentCatalog, DocumentRecord, get_document_catalog
from rag.chain import RAGResult, rag_ask
from rag.chunker import chunk_document, chunk_plain_text
from rag.embedder import embed_chunks, embed_text, embed_texts, cosine_similarity
from rag.ingest import IngestResult, ingest_document, ingest_file, ingest_pdf, ingest_text, ingest_text_file
from rag.loader import load_pdf, load_text_file
from rag.prompt_builder import build_rag_messages, format_context
from rag.retriever import search_similar, search_with_routing
from rag.router import RoutingResult, route_documents
from rag.types import EmbeddedChunk, ExtractedDocument, PageText, SearchResult, TextChunk
from rag.vectorstore import FaissVectorStore

__all__ = [
    "load_pdf",
    "load_text_file",
    "chunk_document",
    "chunk_plain_text",
    "embed_text",
    "embed_texts",
    "embed_chunks",
    "cosine_similarity",
    "FaissVectorStore",
    "search_similar",
    "ingest_text",
    "ingest_file",
    "IngestResult",
    "ingest_pdf",
    "ingest_text_file",
    "ingest_document",
    "search_with_routing",
    "route_documents",
    "RoutingResult",
    "get_document_catalog",
    "DocumentRecord",
    "DocumentCatalog",
    "rag_ask",
    "RAGResult",
    "build_rag_messages",
    "format_context",
    "ExtractedDocument",
    "PageText",
    "TextChunk",
    "EmbeddedChunk",
    "SearchResult",
]
