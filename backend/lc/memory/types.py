"""
Memory 数据结构 — Session 短期 + Long-term 长期。

Short-term Memory 只存用户视角的干净对话（user + assistant），
不存 ReAct 中间步骤（那些属于 agent/memory.py 的 Run Memory）。

Long-term Memory 存经筛选后的语义事实，供向量检索跨 session 复用。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid


@dataclass
class ChatTurn:
    """
    一轮对话 — 用户一句 + 助手最终回答一句。

    属性:
        user:       用户消息
        assistant:  助手最终回复（不是 Thought/Action 中间过程）
        created_at: 创建时间（ISO 格式字符串）
    """

    user: str
    assistant: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Session:
    """
    一个聊天会话 — 包含最近 N 轮对话。

    属性:
        session_id:        会话唯一 ID
        user_id:           所属用户 ID（多用户隔离）
        turns:             对话轮次列表（FIFO，最多 max_session_turns 条）
        long_term_hints:   预留：长期记忆检索结果（未来扩展）
        created_at:        创建时间
        updated_at:        最后更新时间
    """

    session_id: str
    user_id: str
    turns: list[ChatTurn] = field(default_factory=list)
    long_term_hints: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MemoryType(str, Enum):
    """长期记忆分类 — 影响 importance 默认值与检索权重。"""

    IDENTITY = "identity"
    PREFERENCE = "preference"
    FACT = "fact"
    GOAL = "goal"
    EPISODIC = "episodic"


@dataclass
class MemoryRecord:
    """
    一条长期记忆 — Chroma metadata 与业务层共用。

    content 必须是第三人称事实句（便于检索），
    例如「用户姓名：张三」，而不是 raw「我叫张三」。
    """

    user_id: str
    content: str
    memory_type: MemoryType
    importance: float
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_session_id: str | None = None
    raw_user: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ExtractionResult:
    """extractor 输出 — 是否入库及原因（便于日志与调试）。"""

    should_save: bool
    record: MemoryRecord | None = None
    reason: str = ""
    score: float = 0.0
