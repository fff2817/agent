"""LLM 工厂 — ChatOpenAI 与 Embeddings。"""

from lc.llm.chat import (
    ChatMessageCompat,
    chat_completion,
    chat_completion_stream,
    dict_messages_to_lc,
    get_chat_model,
    get_openai_client,
    stream_text_completion,
    vision_completion,
)

__all__ = [
    "get_chat_model",
    "chat_completion",
    "chat_completion_stream",
    "stream_text_completion",
    "vision_completion",
    "dict_messages_to_lc",
    "get_openai_client",
    "ChatMessageCompat",
    "embed_text",
    "embed_texts",
    "embed_chunks",
    "cosine_similarity",
]


def __getattr__(name: str):
    if name in {"embed_text", "embed_texts", "embed_chunks", "cosine_similarity"}:
        from lc.llm import embeddings as emb

        return getattr(emb, name)
    raise AttributeError(name)
