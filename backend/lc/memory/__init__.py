"""Memory 编排层（短期压缩 + 长期检索）。

保持 __init__ 轻量，避免与 infra.session_store 循环导入。
"""

__all__ = [
    "ConversationMemory",
    "LongTermMemoryBackend",
    "get_conversation_memory",
    "ChatTurn",
    "Session",
    "MemoryRecord",
    "MemoryType",
    "ExtractionResult",
]


def __getattr__(name: str):
    if name in {"ConversationMemory", "LongTermMemoryBackend", "get_conversation_memory"}:
        from lc.memory.conversation_memory import (
            ConversationMemory,
            LongTermMemoryBackend,
            get_conversation_memory,
        )

        return {
            "ConversationMemory": ConversationMemory,
            "LongTermMemoryBackend": LongTermMemoryBackend,
            "get_conversation_memory": get_conversation_memory,
        }[name]
    if name in {"ChatTurn", "Session", "MemoryRecord", "MemoryType", "ExtractionResult"}:
        from lc.memory import types as t

        return getattr(t, name)
    raise AttributeError(name)
