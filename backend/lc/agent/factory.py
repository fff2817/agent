"""
LangChain Tool-Calling Agent 工厂。

使用 langchain_classic.agents.create_tool_calling_agent + AgentExecutor，
绑定现有 @tool 工具与 ChatOpenAI；支持 chat_history（Memory）注入。
"""

from __future__ import annotations

import logging

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from core.config import get_settings
from lc.llm.chat import get_chat_model
from lc.prompts import REACT_SYSTEM_PROMPT, build_memory_system_section
from lc.tools.registry import get_tools

logger = logging.getLogger(__name__)


def build_agent_prompt(system_content: str) -> ChatPromptTemplate:
    """
    Tool-calling Agent 标准 Prompt：
      system + chat_history(Memory) + input + agent_scratchpad
    """
    return ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=system_content),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )


def build_system_content(memory_hints: list[str] | None = None) -> str:
    """ReAct 行为手册 + 可选长期记忆段落 + Tool Calling 约束。"""
    extra = (
        "\n\n## Tool Calling 强制规则（LangChain Agent）\n"
        "- 需要工具时，必须通过 API 的 tool_call / function calling 发起调用，"
        "不要只在纯文本里写 `Action: ...`。\n"
        "- 工具返回结果后，再用自然语言给出最终回答；"
        "最终回答可以带 `Final Answer:` 前缀，也可以直接回答。\n"
    )
    return REACT_SYSTEM_PROMPT + extra + build_memory_system_section(memory_hints or [])


def create_tool_calling_agent_executor(
    *,
    memory_hints: list[str] | None = None,
) -> AgentExecutor:
    """
    构建可自动调工具的 AgentExecutor。

    - LLM: core.llm.get_chat_model() → ChatOpenAI
    - Tools: tools.registry.get_tools()
    - Memory: 运行时通过 chat_history 传入（见 lc_runner）
    """
    settings = get_settings()
    llm = get_chat_model()
    tools = get_tools()
    system_content = build_system_content(memory_hints)
    prompt = build_agent_prompt(system_content)

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=settings.debug,
        max_iterations=settings.max_agent_steps,
        return_intermediate_steps=True,
        handle_tool_error=True,
    )

    logger.info(
        "[LC-Agent] 已创建 tool-calling agent: tools=%s max_iter=%d",
        [t.name for t in tools],
        settings.max_agent_steps,
    )
    return executor
