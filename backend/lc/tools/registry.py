"""
工具注册表 — LangChain Tool 索引与调度中心。

Agent 接口保持不变:
  - get_tool_schemas()  → OpenAI tools 列表，供 chat_completion / bind_tools
  - execute_tool()      → 按名称执行，返回 Observation 字符串
  - get_tools()         → list[BaseTool]，供后续 create_agent / LangGraph

新增工具: 用 @tool 定义后加入 _TOOLS 即可。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from lc.tools.calculator import calculator
from lc.tools.list_documents import list_documents
from lc.tools.search_docs import search_docs

logger = logging.getLogger(__name__)

# 已注册的 LangChain Tools（顺序即 schema 顺序）
_TOOLS: list[BaseTool] = [
    calculator,
    search_docs,
    list_documents,
]


def get_tools() -> list[BaseTool]:
    """返回全部 LangChain Tool，供 Agent / LangGraph 绑定。"""
    return list(_TOOLS)


def get_tool_by_name(name: str) -> BaseTool | None:
    """按名称查找 Tool。"""
    for item in _TOOLS:
        if item.name == name:
            return item
    return None


def get_tool_schemas() -> list[dict]:
    """
    返回 OpenAI Function Calling 格式的工具定义列表。

    由 LangChain Tool 自动生成，供 planner 传入 LLM tools= 参数。
    """
    schemas = [convert_to_openai_tool(t) for t in _TOOLS]
    tool_names = [s["function"]["name"] for s in schemas]
    logger.info("[Registry] 已注册工具: %s", tool_names)
    return schemas


def execute_tool(tool_name: str, arguments_json: str) -> str:
    """
    按名称查找并执行 LangChain Tool。

    参数:
        tool_name:       LLM 返回的工具名，如 "calculator"
        arguments_json:  LLM 返回的参数 JSON 字符串

    返回:
        工具执行结果字符串；找不到工具或参数错误时返回 Error 信息
    """
    logger.info("[Registry] 准备执行工具: name=%s, args=%s", tool_name, arguments_json)

    tool = get_tool_by_name(tool_name)
    if tool is None:
        logger.error("[Registry] 未知工具: %s", tool_name)
        return f"Error: unknown tool '{tool_name}'"

    try:
        arguments: dict[str, Any] = json.loads(arguments_json) if arguments_json.strip() else {}
        if not isinstance(arguments, dict):
            return "Error: tool arguments must be a JSON object"
    except json.JSONDecodeError as exc:
        logger.error("[Registry] 参数 JSON 解析失败: %s", exc)
        return f"Error: invalid arguments JSON — {exc}"

    try:
        result = tool.invoke(arguments)
        result_str = result if isinstance(result, str) else str(result)
        logger.info("[Registry] 工具 %s 执行完毕, 结果=%s", tool_name, result_str)
        return result_str
    except KeyError as exc:
        logger.error("[Registry] 缺少必要参数: %s", exc)
        return f"Error: missing required argument — {exc}"
    except Exception as exc:
        logger.exception("[Registry] 工具 %s 执行异常", tool_name)
        return f"Error: tool execution failed — {exc}"
