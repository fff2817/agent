"""LangChain Agent 包。"""

from lc.agent.factory import create_tool_calling_agent_executor
from lc.agent.service import (
    AgentCancelledError,
    ReActResult,
    run_react_agent,
    run_react_agent_stream,
)
from lc.agent.trace import AgentMemory, ReActStep

# 与方案命名对齐的别名
run_agent = run_react_agent
run_agent_stream = run_react_agent_stream

__all__ = [
    "create_tool_calling_agent_executor",
    "run_react_agent",
    "run_react_agent_stream",
    "run_agent",
    "run_agent_stream",
    "ReActResult",
    "AgentCancelledError",
    "ReActStep",
    "AgentMemory",
]
