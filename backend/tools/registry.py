"""
工具注册表 — 所有工具的索引和调度中心。

Agent 只需要知道 registry 的两个接口：
  - get_tool_schemas()  →  获取工具说明书列表，发给 LLM
  - execute_tool()      →  按名称执行工具，返回结果字符串

新增工具时：在 _TOOL_REGISTRY 里加一条即可，Agent 代码不用改。
"""

import json
import logging
from collections.abc import Callable

from tools.calculator import CALCULATOR_TOOL_SCHEMA, run_calculator
from tools.list_documents import LIST_DOCUMENTS_TOOL_SCHEMA, run_list_documents
from tools.search_docs import SEARCH_DOCS_TOOL_SCHEMA, run_search_docs

logger = logging.getLogger(__name__)

# 工具注册表：name → { schema, handler }
# schema  : 给 LLM 看的说明书
# handler : 实际执行的 Python 函数，签名为 (kwargs) -> str
_TOOL_REGISTRY: dict[str, dict] = {
    "calculator": {
        "schema": CALCULATOR_TOOL_SCHEMA,
        "handler": lambda args: run_calculator(args["expression"]),
    },
    "search_docs": {
        "schema": SEARCH_DOCS_TOOL_SCHEMA,
        "handler": lambda args: run_search_docs(
            args["query"],
            filenames=args.get("filenames"),
            scope=args.get("scope", "auto"),
        ),
    },
    "list_documents": {
        "schema": LIST_DOCUMENTS_TOOL_SCHEMA,
        "handler": lambda _args: run_list_documents(),
    },
}


def get_tool_schemas() -> list[dict]:
    """
    返回所有已注册工具的 schema 列表，供 LLM 的 tools 参数使用。

    返回:
        OpenAI Function Calling 格式的工具定义列表
    """
    schemas = [entry["schema"] for entry in _TOOL_REGISTRY.values()]
    tool_names = [s["function"]["name"] for s in schemas]
    logger.info("[Registry] 已注册工具: %s", tool_names)
    return schemas


def execute_tool(tool_name: str, arguments_json: str) -> str:
    """
    按名称查找并执行工具。

    参数:
        tool_name:       LLM 返回的工具名，如 "calculator"
        arguments_json:  LLM 返回的参数 JSON 字符串，如 '{"expression": "123 * 456"}'

    返回:
        工具执行结果字符串；找不到工具或参数错误时返回 Error 信息
    """
    logger.info("[Registry] 准备执行工具: name=%s, args=%s", tool_name, arguments_json)

    entry = _TOOL_REGISTRY.get(tool_name)
    if entry is None:
        logger.error("[Registry] 未知工具: %s", tool_name)
        return f"Error: unknown tool '{tool_name}'"

    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        logger.error("[Registry] 参数 JSON 解析失败: %s", exc)
        return f"Error: invalid arguments JSON — {exc}"

    handler: Callable = entry["handler"]

    try:
        result = handler(arguments)
        logger.info("[Registry] 工具 %s 执行完毕, 结果=%s", tool_name, result)
        return result
    except KeyError as exc:
        logger.error("[Registry] 缺少必要参数: %s", exc)
        return f"Error: missing required argument — {exc}"
    except Exception as exc:
        logger.exception("[Registry] 工具 %s 执行异常", tool_name)
        return f"Error: tool execution failed — {exc}"
