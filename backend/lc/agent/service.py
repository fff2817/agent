"""
Agent 主入口 — 对外保持 run_react_agent / run_react_agent_stream 不变。

内部已切换为 LangChain create_tool_calling_agent + AgentExecutor
（见 agent.lc_factory / agent.lc_runner），并接入现有 Tools 与 Memory。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from lc.agent.runner import AgentCancelledError
from lc.agent.runner import run_lc_agent, run_lc_agent_stream
from lc.agent.react_memory import ReActStep

logger = logging.getLogger(__name__)


@dataclass
class ReActResult:
    """Agent 运行结果 — 保持旧字段名以兼容 API。"""

    response: str
    trace: list


def run_react_agent(
    user_message: str,
    *,
    history: list[dict] | None = None,
    memory_hints: list[str] | None = None,
    user_id: str | None = None,
) -> ReActResult:
    """
    同步 Agent 入口（API 契约不变）。

    history:      ConversationMemory 压缩后的短期历史
    memory_hints: 长期记忆 hints（写入 system prompt）
    """
    logger.info("[Agent] 使用 LangChain tool-calling agent")
    response, trace = run_lc_agent(
        user_message,
        history=history,
        memory_hints=memory_hints,
        user_id=user_id,
    )
    return ReActResult(response=response, trace=trace)


def run_react_agent_stream(
    user_message: str,
    *,
    history: list[dict] | None = None,
    memory_hints: list[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    user_id: str | None = None,
) -> Iterator[dict]:
    """
    流式 Agent 入口 — SSE 事件: token / step / done（契约不变）。
    """
    logger.info("[Agent] 使用 LangChain tool-calling agent（stream）")
    yield from run_lc_agent_stream(
        user_message,
        history=history,
        memory_hints=memory_hints,
        should_cancel=should_cancel,
        user_id=user_id,
    )


def _trace_to_dicts(trace: list[ReActStep]) -> list[dict]:
    return [
        {
            "step": s.step,
            "thought": s.thought,
            "action": s.action,
            "observation": s.observation,
            "final_answer": s.final_answer,
        }
        for s in trace
    ]
