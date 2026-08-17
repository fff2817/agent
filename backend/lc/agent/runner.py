"""
LangChain Agent 运行适配 — 保持与旧 ReAct 门面相同的返回/SSE 契约。

入口仍由 agent.loop.run_react_agent / run_react_agent_stream 调用。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

from langchain_core.agents import AgentAction

from lc.agent.factory import create_tool_calling_agent_executor
from lc.agent.react_memory import ReActStep
from lc.agent.parser import _extract_final_answer, _parse_text_action
from auth.context import set_current_user_id
from lc.llm.chat import dict_messages_to_lc
from lc.tools.registry import execute_tool

logger = logging.getLogger(__name__)


class AgentCancelledError(Exception):
    """用户主动停止生成时抛出，携带已生成的部分回答。"""

    def __init__(self, partial_response: str = "") -> None:
        self.partial_response = partial_response
        super().__init__("Agent run cancelled by client")


def _normalize_final_answer(text: str) -> str:
    raw = (text or "").strip()
    lower = raw.lower()
    marker = "final answer:"
    idx = lower.find(marker)
    if idx != -1:
        return raw[idx + len(marker) :].strip()
    return raw


def _format_action(action: AgentAction) -> str:
    tool = action.tool
    tool_input = action.tool_input
    if isinstance(tool_input, dict):
        try:
            args = json.dumps(tool_input, ensure_ascii=False)
        except TypeError:
            args = str(tool_input)
        return f"{tool}({args})"
    return f"{tool}({tool_input})"


def _thought_from_action(action: AgentAction) -> str:
    log = (action.log or "").strip()
    if log:
        return log[:500]
    return f"调用工具 {action.tool}"


def _steps_from_intermediate(
    intermediate_steps: list[tuple[AgentAction, str]],
    *,
    final_answer: str | None = None,
) -> list[ReActStep]:
    trace: list[ReActStep] = []
    for idx, (action, observation) in enumerate(intermediate_steps, start=1):
        trace.append(
            ReActStep(
                step=idx,
                thought=_thought_from_action(action),
                action=_format_action(action),
                observation=str(observation),
            )
        )
    if final_answer is not None:
        trace.append(
            ReActStep(
                step=len(trace) + 1,
                thought="已收集足够信息，给出最终回答",
                final_answer=final_answer,
            )
        )
    return trace


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


def _history_to_lc(history: list[dict] | None) -> list:
    if not history:
        return []
    return dict_messages_to_lc(history)


def _recover_text_action(
    output: str,
    *,
    user_message: str,
    history: list[dict],
    memory_hints: list[str] | None,
) -> tuple[str, list[tuple[AgentAction, str]]] | None:
    """
    部分模型会把 Action 写在纯文本里而不发 tool_calls。
    此处解析文本 Action → 执行工具 → 再跑一轮 Agent，兼容旧 parser 行为。
    """
    action = _parse_text_action(output)
    if action is None:
        return None

    logger.info("[LC-Agent] 文本 Action fallback: %s", action.display())
    observation = execute_tool(action.tool_name, action.arguments)
    try:
        tool_input: Any = json.loads(action.arguments)
    except json.JSONDecodeError:
        tool_input = action.arguments
    synthetic = AgentAction(
        tool=action.tool_name,
        tool_input=tool_input,
        log=output[:500],
    )
    steps: list[tuple[AgentAction, str]] = [(synthetic, observation)]

    follow_history = list(history) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": output},
        {
            "role": "user",
            "content": f"Observation: {observation}\n请基于 Observation 给出 Final Answer。",
        },
    ]
    # follow_history 已含当前 user，executor 的 input 用催促语
    executor = create_tool_calling_agent_executor(memory_hints=memory_hints)
    result = executor.invoke(
        {
            "input": "请给出最终回答。",
            "chat_history": _history_to_lc(follow_history),
        }
    )
    follow_out = _normalize_final_answer(str(result.get("output") or ""))
    extra = result.get("intermediate_steps") or []
    steps.extend(extra)
    if not follow_out:
        # 若仍空，至少返回 observation
        follow_out = observation
    return follow_out, steps


def run_lc_agent(
    user_message: str,
    *,
    history: list[dict] | None = None,
    memory_hints: list[str] | None = None,
    user_id: str | None = None,
) -> tuple[str, list[ReActStep]]:
    """同步运行 create_tool_calling_agent；返回 (final_answer, trace)。"""
    if user_id:
        set_current_user_id(user_id)

    history = history or []
    logger.info(
        "[LC-Agent] 同步运行: message=%s history=%d hints=%d",
        user_message[:80],
        len(history),
        len(memory_hints or []),
    )

    executor = create_tool_calling_agent_executor(memory_hints=memory_hints)
    result: dict[str, Any] = executor.invoke(
        {
            "input": user_message,
            "chat_history": _history_to_lc(history),
        }
    )

    output = _normalize_final_answer(str(result.get("output") or ""))
    intermediate = list(result.get("intermediate_steps") or [])

    if not intermediate:
        recovered = _recover_text_action(
            str(result.get("output") or ""),
            user_message=user_message,
            history=history,
            memory_hints=memory_hints,
        )
        if recovered:
            output, intermediate = recovered

    if not output:
        raise ValueError("LangChain Agent returned empty output")

    # 若模型把 Final Answer 嵌在长文本里，再抽一次
    if "final answer:" in output.lower() or "Final Answer:" in (
        result.get("output") or ""
    ):
        extracted = _extract_final_answer(str(result.get("output") or output))
        if extracted:
            output = extracted

    trace = _steps_from_intermediate(intermediate, final_answer=output)
    logger.info("[LC-Agent] 完成: steps=%d output_len=%d", len(trace), len(output))
    return output, trace


def run_lc_agent_stream(
    user_message: str,
    *,
    history: list[dict] | None = None,
    memory_hints: list[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    user_id: str | None = None,
) -> Iterator[dict]:
    """
    流式运行 AgentExecutor，产出与旧 loop 兼容的 SSE 事件:
      token / step / done
    """
    if user_id:
        set_current_user_id(user_id)
        logger.info("[LC-Agent] 流式绑定用户: %s", user_id)

    history = history or []
    partial = ""
    collected_steps: list[tuple[AgentAction, str]] = []
    step_num = 0

    def _check_cancel() -> None:
        if should_cancel and should_cancel():
            raise AgentCancelledError(partial)

    executor = create_tool_calling_agent_executor(memory_hints=memory_hints)
    payload = {
        "input": user_message,
        "chat_history": _history_to_lc(history),
    }

    logger.info("[LC-Agent] 流式运行: message=%s", user_message[:80])

    for chunk in executor.stream(payload):
        _check_cancel()
        if not isinstance(chunk, dict):
            continue

        # 工具调用意图
        actions = chunk.get("actions")
        if actions:
            for action in actions:
                if not isinstance(action, AgentAction):
                    continue
                step_num += 1
                step_data = {
                    "step": step_num,
                    "thought": _thought_from_action(action),
                    "action": _format_action(action),
                    "observation": None,
                    "final_answer": None,
                }
                yield {"type": "step", "step": step_data}

        # 工具执行结果
        steps = chunk.get("steps")
        if steps:
            for agent_step in steps:
                action = getattr(agent_step, "action", None)
                observation = getattr(agent_step, "observation", None)
                if action is None:
                    continue
                collected_steps.append((action, str(observation)))
                step_data = {
                    "step": len(collected_steps),
                    "thought": _thought_from_action(action),
                    "action": _format_action(action),
                    "observation": str(observation),
                    "final_answer": None,
                }
                yield {"type": "step", "step": step_data}

        # 最终输出
        if "output" in chunk and chunk["output"] is not None:
            output = _normalize_final_answer(str(chunk["output"]))
            if not output:
                continue
            # 逐段推送，贴近打字机效果
            for i in range(0, len(output), 16):
                _check_cancel()
                piece = output[i : i + 16]
                partial += piece
                yield {"type": "token", "content": piece}

            final = _normalize_final_answer(partial) or output
            trace = _steps_from_intermediate(collected_steps, final_answer=final)
            yield {
                "type": "step",
                "step": {
                    "step": len(trace),
                    "thought": "已收集足够信息，给出最终回答",
                    "action": None,
                    "observation": None,
                    "final_answer": final,
                },
            }
            yield {
                "type": "done",
                "response": final,
                "steps": _trace_to_dicts(trace),
            }
            logger.info("[LC-Agent] 流式完成: steps=%d", len(trace))
            return

    # 未产出 output 时兜底
    if partial.strip():
        final = _normalize_final_answer(partial)
        trace = _steps_from_intermediate(collected_steps, final_answer=final)
        yield {
            "type": "done",
            "response": final,
            "steps": _trace_to_dicts(trace),
        }
        return

    raise ValueError("LangChain Agent stream ended without output")
