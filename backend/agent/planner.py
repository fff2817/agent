"""
Planner — ReAct 的「大脑」，负责产生 Thought 和 Action。

每一轮循环:
  1. 读取 memory 中的对话历史
  2. 调用 LLM（带工具说明书 + ReAct Prompt）
  3. 用 parser 解析响应 → PlannerResult

Planner 不执行工具，只负责「想」和「决策」。
"""

import logging
from collections.abc import Callable
from typing import Any

from agent.memory import AgentMemory
from agent.parser import PlannerResult, parse_llm_response
from core.llm import chat_completion, chat_completion_stream
from tools.registry import get_tool_schemas

logger = logging.getLogger(__name__)


def plan(memory: AgentMemory) -> PlannerResult:
    """
    基于当前 memory 状态，调用 LLM 进行一步 ReAct 规划。

    参数:
        memory: AgentMemory — 包含完整对话历史和 trace

    返回:
        PlannerResult — 含 thought、action（或 final_answer）

    异常:
        ValueError: API Key 未配置
    """
    tools = get_tool_schemas()

    logger.info("[Planner] 开始规划, 当前 messages=%d 条", len(memory.messages))

    # 调用 LLM，传入当前对话 + 可用工具
    response_message = chat_completion(memory.messages, tools=tools)

    # 解析 LLM 输出为结构化 PlannerResult
    result = parse_llm_response(response_message)

    logger.info(
        "[Planner] 规划完成: is_final=%s, has_action=%s",
        result.is_final,
        result.action is not None,
    )

    return result


def _assemble_streamed_message(content: str, tool_calls_raw: dict[int, dict]) -> Any:
    """把流式 chunk 拼成 parse_llm_response 可接受的 message 对象。"""

    class _Function:
        def __init__(self, name: str, arguments: str) -> None:
            self.name = name
            self.arguments = arguments

    class _ToolCall:
        def __init__(self, tc_id: str, name: str, arguments: str) -> None:
            self.id = tc_id
            self.type = "function"
            self.function = _Function(name, arguments)

    class _Message:
        def __init__(self, text: str, tool_calls: list[_ToolCall] | None) -> None:
            self.content = text or None
            self.tool_calls = tool_calls

    assembled_tool_calls: list[_ToolCall] | None = None
    if tool_calls_raw:
        assembled_tool_calls = []
        for idx in sorted(tool_calls_raw):
            tc = tool_calls_raw[idx]
            assembled_tool_calls.append(_ToolCall(tc["id"], tc["name"], tc["arguments"]))

    return _Message(content, assembled_tool_calls)


def plan_stream(
    memory: AgentMemory,
    *,
    on_answer_token: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> PlannerResult:
    """
    流式规划 — 在生成 Final Answer 时逐 token 回调，支持中途取消。

    仅当检测到 "Final Answer:" 之后的内容才会触发 on_answer_token，
    避免 ReAct 中间 Thought 泄露到聊天气泡。
    """
    tools = get_tool_schemas()

    logger.info("[Planner] 开始流式规划, 当前 messages=%d 条", len(memory.messages))

    content_parts: list[str] = []
    tool_calls_raw: dict[int, dict] = {}
    final_answer_started = False
    pending_answer = ""

    for chunk in chat_completion_stream(
        memory.messages,
        tools=tools,
        should_cancel=should_cancel,
    ):
        if should_cancel and should_cancel():
            break

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        if delta.content:
            content_parts.append(delta.content)
            piece = delta.content

            if not final_answer_started:
                pending_answer += piece
                marker = "Final Answer:"
                idx = pending_answer.find(marker)
                if idx != -1:
                    final_answer_started = True
                    answer_part = pending_answer[idx + len(marker) :]
                    if answer_part and on_answer_token:
                        on_answer_token(answer_part)
            elif on_answer_token:
                on_answer_token(piece)

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_raw:
                    tool_calls_raw[idx] = {"id": "", "name": "", "arguments": ""}
                if tc.id:
                    tool_calls_raw[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tool_calls_raw[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls_raw[idx]["arguments"] += tc.function.arguments

    full_content = "".join(content_parts)
    message = _assemble_streamed_message(full_content, tool_calls_raw)
    result = parse_llm_response(message)

    # 无 Final Answer 标记但判定为最终回答时，补发全文 token
    if result.is_final and on_answer_token and not final_answer_started and result.final_answer:
        on_answer_token(result.final_answer)

    logger.info(
        "[Planner] 流式规划完成: is_final=%s, has_action=%s",
        result.is_final,
        result.action is not None,
    )

    return result
