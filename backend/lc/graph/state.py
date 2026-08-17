"""LangGraph 二期骨架 — AgentState。"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """后续 StateGraph 使用的状态（一期占位）。"""

    messages: Annotated[list, add_messages]
    user_id: str
    memory_hints: list[str]
