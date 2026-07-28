"""
Tool Calling Agent（旧版）— 保留向后兼容。

新代码请使用 agent.loop.run_react_agent()。
"""

import logging

from agent.loop import run_react_agent

logger = logging.getLogger(__name__)


def run_agent(user_message: str, *, history: list[dict] | None = None) -> str:
    """
    向后兼容入口 — 内部委托给 ReAct loop，只返回 response 字符串。
    """
    logger.info("[Agent] run_agent() 已委托给 ReAct loop")
    result = run_react_agent(user_message, history=history)
    return result.response
