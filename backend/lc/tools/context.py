"""工具运行时上下文（显式依赖注入，替代仅靠 ContextVar）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolContext:
    """供工具读取的请求级上下文。"""

    user_id: str | None = None
    session_id: str | None = None


_current: ToolContext | None = None


def set_tool_context(ctx: ToolContext | None) -> None:
    global _current
    _current = ctx


def get_tool_context() -> ToolContext:
    return _current or ToolContext()
