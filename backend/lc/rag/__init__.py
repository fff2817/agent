"""RAG 编排层（检索 / 入库 / 问答链）。

注意：保持 __init__ 轻量，避免与 lc.llm.embeddings ↔ catalog 循环导入。
"""

__all__ = ["rag_ask", "rag_ask_stream", "ingest_text", "ingest_file"]


def __getattr__(name: str):
    if name in {"rag_ask", "rag_ask_stream"}:
        from lc.rag.chain import rag_ask, rag_ask_stream

        return {"rag_ask": rag_ask, "rag_ask_stream": rag_ask_stream}[name]
    if name in {"ingest_text", "ingest_file"}:
        from lc.rag.ingest import ingest_file, ingest_text

        return {"ingest_text": ingest_text, "ingest_file": ingest_file}[name]
    raise AttributeError(name)
