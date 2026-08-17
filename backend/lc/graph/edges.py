"""LangGraph 边 / 路由占位（二期实现）。"""

from __future__ import annotations

from typing import Any, Literal


def should_continue(state: dict[str, Any]) -> Literal["tools", "end"]:
    """占位：根据最后一条消息是否含 tool_calls 决定走向。"""
    raise NotImplementedError("lc.graph edges will be implemented in phase 2")
