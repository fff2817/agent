"""
ReAct Agent 主循环 — Thought → Action → Observation → ... → Final Answer

这是 ReAct Agent 的总指挥，协调 planner、executor、memory 完成完整循环。

流程:
    用户问题
      → [Thought + Action]  planner.plan()
      → [Observation]       executor.execute()  （若有 Action）
      → 重复，直到 planner 返回 Final Answer
      → 返回最终回复 + trace

后续接 RAG:
  - 在 memory 中注入检索上下文
  - 在 tools/ 中注册 search_docs 工具
  - loop 本身无需修改
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from agent.executor import execute
from agent.memory import AgentMemory
from agent.planner import plan, plan_stream
from agent.prompts import REACT_SYSTEM_PROMPT
from core.config import get_settings
from memory.prompt_builder import build_memory_system_section

logger = logging.getLogger(__name__)


class AgentCancelledError(Exception):
    """用户主动停止生成时抛出，携带已生成的部分回答。"""

    def __init__(self, partial_response: str = "") -> None:
        self.partial_response = partial_response
        super().__init__("Agent run cancelled by client")


@dataclass
class ReActResult:
    """
    ReAct Agent 运行结果。

    属性:
        response: 给用户的最终回答
        trace:    完整 ReAct 步骤链（Thought/Action/Observation/Final Answer）
    """

    response: str
    trace: list


def _build_initial_messages(
    user_message: str,
    history: list[dict],
    *,
    memory_hints: list[str] | None = None,
) -> list[dict]:
    system_content = REACT_SYSTEM_PROMPT + build_memory_system_section(
        memory_hints or []
    )
    return [
        {"role": "system", "content": system_content},
        *history,
        {"role": "user", "content": user_message},
    ]


def run_react_agent(
    user_message: str,
    *,
    history: list[dict] | None = None,
    memory_hints: list[str] | None = None,
) -> ReActResult:
    """
    ReAct Agent 主入口。

    参数:
        user_message: 用户输入
        history:      Session 历史 messages（user/assistant 交替），不含当前消息

    返回:
        ReActResult — 含 response 和 trace

    异常:
        ValueError: 配置错误或超过最大步数
    """
    settings = get_settings()
    history = history or []

    logger.info("[Agent] 收到用户问题: %s", user_message)
    if history:
        logger.info("[Agent] 注入 Session 历史: %d 条 messages", len(history))
    if memory_hints:
        logger.info("[Agent] 注入长期记忆: %d 条 hints", len(memory_hints))

    initial_messages = _build_initial_messages(
        user_message,
        history,
        memory_hints=memory_hints,
    )

    memory = AgentMemory(
        user_message=user_message,
        messages=initial_messages,
    )

    for step_num in range(1, settings.max_agent_steps + 1):
        logger.info("[Agent] ===== ReAct 第 %d 轮 =====", step_num)

        # ------------------------------------------------------------------
        # 1. Planner: Thought + Action（或 Final Answer）
        # ------------------------------------------------------------------
        planner_result = plan(memory)

        # 打印 Thought 日志
        logger.info("[Thought]\n%s", planner_result.thought)

        # 把 assistant 消息写入 memory（含 tool_calls 或 final content）
        if planner_result.assistant_message:
            memory.append_assistant_message(planner_result.assistant_message)

        # ------------------------------------------------------------------
        # 2. 路径 A: Final Answer — 循环结束
        # ------------------------------------------------------------------
        if planner_result.is_final:
            final_answer = planner_result.final_answer
            if not final_answer:
                raise ValueError("LLM returned empty Final Answer")

            logger.info("[Final Answer]\n%s", final_answer)

            memory.add_trace_step(
                step=step_num,
                thought=planner_result.thought,
                final_answer=final_answer,
            )

            logger.info("[Agent] ReAct 循环结束, 共 %d 步", step_num)
            return ReActResult(response=final_answer, trace=memory.trace)

        # ------------------------------------------------------------------
        # 3. 路径 B: Action — 执行工具，获得 Observation
        # ------------------------------------------------------------------
        if planner_result.action is None:
            raise ValueError("Planner returned neither Action nor Final Answer")

        action = planner_result.action

        # 打印 Action 日志
        logger.info("[Action]\n%s", action.display())

        # Executor: 执行工具
        observation = execute(action)

        # 打印 Observation 日志
        logger.info("[Observation]\n%s", observation)

        # 把 Observation 写入 memory（role=tool）
        if action.tool_call_id:
            memory.append_tool_result(action.tool_call_id, observation)
        else:
            # 文本 Action fallback：用 user 消息模拟 Observation
            memory.messages.append(
                {
                    "role": "user",
                    "content": f"Observation: {observation}",
                }
            )

        # 记录 trace
        memory.add_trace_step(
            step=step_num,
            thought=planner_result.thought,
            action=action.display(),
            observation=observation,
        )

        logger.info("[Agent] 第 %d 轮完成, 进入下一轮", step_num)

    # 超过最大步数
    raise ValueError(
        f"ReAct Agent exceeded maximum steps ({settings.max_agent_steps}) "
        "without a Final Answer"
    )


def run_react_agent_stream(
    user_message: str,
    *,
    history: list[dict] | None = None,
    memory_hints: list[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[dict]:
    """
    可流式、可取消的 ReAct Agent 入口。

    产出 SSE 事件 dict:
      - {"type": "token", "content": "..."}
      - {"type": "step", "step": {...}}
      - {"type": "done", "response": "...", "steps": [...]}
    """
    settings = get_settings()
    history = history or []
    partial_response = ""
    pending_tokens: list[str] = []

    logger.info("[Agent] 流式模式收到用户问题: %s", user_message)
    if memory_hints:
        logger.info("[Agent] 流式注入长期记忆: %d 条 hints", len(memory_hints))

    initial_messages = _build_initial_messages(
        user_message,
        history,
        memory_hints=memory_hints,
    )

    memory = AgentMemory(
        user_message=user_message,
        messages=initial_messages,
    )

    def _check_cancelled() -> None:
        if should_cancel and should_cancel():
            raise AgentCancelledError(partial_response)

    def _on_answer_token(token: str) -> None:
        nonlocal partial_response
        partial_response += token
        pending_tokens.append(token)

    def _flush_tokens() -> Iterator[dict]:
        nonlocal pending_tokens
        while pending_tokens:
            token = pending_tokens.pop(0)
            yield {"type": "token", "content": token}
            _check_cancelled()

    def _step_payload(step_num: int, **kwargs) -> dict:
        return {
            "step": step_num,
            "thought": kwargs.get("thought", ""),
            "action": kwargs.get("action"),
            "observation": kwargs.get("observation"),
            "final_answer": kwargs.get("final_answer"),
        }

    for step_num in range(1, settings.max_agent_steps + 1):
        _check_cancelled()
        logger.info("[Agent] ===== ReAct 第 %d 轮（流式）=====", step_num)

        planner_result = plan_stream(
            memory,
            on_answer_token=_on_answer_token,
            should_cancel=should_cancel,
        )

        yield from _flush_tokens()
        _check_cancelled()

        logger.info("[Thought]\n%s", planner_result.thought)

        if planner_result.assistant_message:
            memory.append_assistant_message(planner_result.assistant_message)

        if planner_result.is_final:
            final_answer = planner_result.final_answer or partial_response
            if not final_answer:
                raise ValueError("LLM returned empty Final Answer")

            logger.info("[Final Answer]\n%s", final_answer)

            step_data = _step_payload(
                step_num,
                thought=planner_result.thought,
                final_answer=final_answer,
            )
            memory.add_trace_step(**step_data)

            yield {"type": "step", "step": step_data}
            yield {
                "type": "done",
                "response": final_answer,
                "steps": _trace_to_dicts(memory.trace),
            }
            logger.info("[Agent] 流式 ReAct 循环结束, 共 %d 步", step_num)
            return

        if planner_result.action is None:
            raise ValueError("Planner returned neither Action nor Final Answer")

        action = planner_result.action
        logger.info("[Action]\n%s", action.display())

        step_data = _step_payload(
            step_num,
            thought=planner_result.thought,
            action=action.display(),
        )
        memory.add_trace_step(**step_data)
        yield {"type": "step", "step": step_data}

        _check_cancelled()
        observation = execute(action)
        logger.info("[Observation]\n%s", observation)

        if action.tool_call_id:
            memory.append_tool_result(action.tool_call_id, observation)
        else:
            memory.messages.append(
                {
                    "role": "user",
                    "content": f"Observation: {observation}",
                }
            )

        memory.trace[-1].observation = observation
        yield {
            "type": "step",
            "step": {**step_data, "observation": observation},
        }

        partial_response = ""
        logger.info("[Agent] 第 %d 轮完成, 进入下一轮", step_num)

    raise ValueError(
        f"ReAct Agent exceeded maximum steps ({settings.max_agent_steps}) "
        "without a Final Answer"
    )


def _trace_to_dicts(trace: list) -> list[dict]:
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
