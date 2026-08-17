"""LangGraph 节点占位（二期实现）。"""

from __future__ import annotations

from typing import Any


def call_model(state: dict[str, Any]) -> dict[str, Any]:
    """占位：调用 LLM。"""
    raise NotImplementedError("lc.graph nodes will be implemented in phase 2")


def call_tools(state: dict[str, Any]) -> dict[str, Any]:
    """占位：执行工具。"""
    raise NotImplementedError("lc.graph nodes will be implemented in phase 2")
