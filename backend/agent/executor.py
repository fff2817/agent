"""
Executor — ReAct 的「手脚」，负责 Action → Observation。

接收 planner 给出的 Action，调用 tools/registry 执行工具，
把结果包装为 Observation 字符串返回。

Executor 不决定调哪个工具，只负责「执行并汇报」。
"""

import logging

from agent.parser import Action
from tools.registry import execute_tool

logger = logging.getLogger(__name__)


def execute(action: Action) -> str:
    """
    执行一个 Action，返回 Observation（工具执行结果）。

    参数:
        action: Action 对象 — 含 tool_name、arguments、tool_call_id

    返回:
        工具执行结果字符串；出错时为 "Error: ..." 格式
    """
    logger.info("[Executor] 准备执行 Action: %s", action.display())

    observation = execute_tool(action.tool_name, action.arguments)

    logger.info("[Executor] 获得 Observation: %s", observation)

    return observation
