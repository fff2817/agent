"""
LLM 输出解析器 — 把 LLM 原始响应拆成 ReAct 结构化数据。

支持两种 Action 来源（按优先级）:
  1. 原生 tool_calls（OpenAI Function Calling 格式，推荐）
  2. 文本中的 Action: 行（部分模型的 fallback）

输出统一为 PlannerResult，供 loop.py 使用。
"""

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Action:
    """
    一次工具调用（ReAct 的 Action 环节）。

    属性:
        tool_name:     工具名称，如 "calculator"
        arguments:     参数 JSON 字符串，如 '{"expression": "123 * 456"}'
        tool_call_id:  API 返回的调用 ID，回传 Observation 时必须匹配
    """

    tool_name: str
    arguments: str
    tool_call_id: str | None = None

    def display(self) -> str:
        """
        格式化为易读的 Action 字符串，用于日志输出。

        示例: calculator({"expression": "123 * 456"})
        """
        try:
            args_obj = json.loads(self.arguments)
            # 简化 calculator 的显示：calculator(123 * 456)
            if self.tool_name == "calculator" and "expression" in args_obj:
                return f'{self.tool_name}({args_obj["expression"]})'
        except json.JSONDecodeError:
            pass
        return f"{self.tool_name}({self.arguments})"


@dataclass
class PlannerResult:
    """
    Planner 一轮的解析结果。

    两种互斥路径:
      - is_final=True  →  包含 final_answer，action 为空
      - is_final=False →  包含 action，需要 executor 执行
    """

    thought: str
    action: Action | None = None
    is_final: bool = False
    final_answer: str = ""
    assistant_message: dict | None = None


def _extract_thought(content: str | None) -> str:
    """
    从 LLM 文本中提取 Thought 段落。

    匹配 "Thought: ..." 格式；若无标记则返回全文（去掉 Final Answer 部分）。
    """
    if not content or not content.strip():
        return "（模型未输出显式 Thought，直接发起行动）"

    text = content.strip()

    # 匹配 Thought: ... 直到 Action: / Final Answer: 或结尾
    thought_match = re.search(
        r"Thought:\s*(.+?)(?=\n(?:Action:|Final Answer:)\s|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if thought_match:
        return thought_match.group(1).strip()

    # 若含 Final Answer，Thought 取其前面的部分
    if re.search(r"Final Answer:", text, re.IGNORECASE):
        parts = re.split(r"Final Answer:", text, maxsplit=1, flags=re.IGNORECASE)
        before = parts[0].strip()
        # 去掉可能残留的 "Thought:" 前缀
        before = re.sub(r"^Thought:\s*", "", before, flags=re.IGNORECASE).strip()
        return before or "（准备给出最终回答）"

    return text


def _extract_final_answer(content: str | None) -> str:
    """
    从 LLM 文本中提取 Final Answer 段落。
    """
    if not content:
        return ""

    match = re.search(r"Final Answer:\s*(.+)", content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 无 Final Answer 标记时，整段 content 即为最终回答
    return content.strip()


def _parse_text_action(content: str) -> Action | None:
    """
    Fallback：从文本中解析 Action 行。

    匹配: Action: calculator({"expression": "123 * 456"})
    或:   Action: calculator(123 * 456)
    """
    if not content:
        return None

    match = re.search(
        r"Action:\s*(\w+)\((.+?)\)\s*$",
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None

    tool_name = match.group(1)
    raw_args = match.group(2).strip()

    # 若已是 JSON 对象
    if raw_args.startswith("{"):
        return Action(tool_name=tool_name, arguments=raw_args)

    # 否则包装为 calculator expression
    if tool_name == "calculator":
        return Action(
            tool_name=tool_name,
            arguments=json.dumps({"expression": raw_args}, ensure_ascii=False),
        )

    return Action(tool_name=tool_name, arguments=json.dumps({"input": raw_args}))


def _assistant_message_to_dict(message) -> dict:
    """
    把 OpenAI SDK 的 ChatCompletionMessage 转为 dict，用于写入 memory。
    """
    msg_dict: dict = {
        "role": "assistant",
        "content": message.content,
    }

    if message.tool_calls:
        msg_dict["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]

    return msg_dict


def parse_llm_response(message) -> PlannerResult:
    """
    解析 LLM 响应，提取 Thought / Action / Final Answer。

    参数:
        message: openai SDK 的 ChatCompletionMessage 对象

    返回:
        PlannerResult — loop.py 据此决定执行工具还是返回最终答案
    """
    content = message.content
    thought = _extract_thought(content)
    assistant_message = _assistant_message_to_dict(message)

    logger.info("[Parser] 提取 Thought: %s", thought[:200])

    # --- 路径 A: 原生 tool_calls（Action）---
    if message.tool_calls:
        tc = message.tool_calls[0]
        action = Action(
            tool_name=tc.function.name,
            arguments=tc.function.arguments,
            tool_call_id=tc.id,
        )
        logger.info("[Parser] 提取 Action (tool_call): %s", action.display())
        return PlannerResult(
            thought=thought,
            action=action,
            is_final=False,
            assistant_message=assistant_message,
        )

    # --- 路径 B: 文本中的 Action（fallback）---
    text_action = _parse_text_action(content or "")
    if text_action:
        logger.info("[Parser] 提取 Action (文本): %s", text_action.display())
        return PlannerResult(
            thought=thought,
            action=text_action,
            is_final=False,
            assistant_message=assistant_message,
        )

    # --- 路径 C: Final Answer（无工具调用，循环结束）---
    final_answer = _extract_final_answer(content)
    logger.info("[Parser] 提取 Final Answer: %s", final_answer[:200])
    return PlannerResult(
        thought=thought,
        action=None,
        is_final=True,
        final_answer=final_answer,
        assistant_message=assistant_message,
    )
