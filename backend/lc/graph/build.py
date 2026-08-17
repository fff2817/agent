"""编译 LangGraph StateGraph（二期）。

一期 Agent 使用 lc.agent.factory.create_tool_calling_agent_executor。
本模块预留 build_graph()，后续可无缝替换 service 内核。
"""

from __future__ import annotations

from typing import Any


def build_graph() -> Any:
    """返回 compiled StateGraph（尚未实现）。"""
    raise NotImplementedError(
        "LangGraph build_graph is reserved for phase 2; "
        "use lc.agent.factory.create_tool_calling_agent_executor for now"
    )
