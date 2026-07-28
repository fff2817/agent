"""
Agent 工作记忆 — 管理对话历史和 ReAct 步骤追踪。

职责:
  - 维护发给 LLM 的 messages 列表（多轮对话上下文）
  - 记录每一步 Thought / Action / Observation（trace）
  - 为前端侧边栏和调试日志提供结构化数据

后续接 RAG 时，可在此模块扩展：
  - retrieved_docs: 检索到的文档片段
  - add_retrieval_context(): 把 RAG 结果注入 messages
"""

from dataclasses import dataclass, field


@dataclass
class ReActStep:
    """
    单步 ReAct 记录 — 对应一轮 Thought → Action → Observation。

    如果该步是最终回答，则 final_answer 有值，action/observation 为空。
    """

    step: int
    thought: str
    action: str | None = None
    observation: str | None = None
    final_answer: str | None = None


@dataclass
class AgentMemory:
    """
    Agent 运行时状态容器。

    属性:
        user_message:  用户原始问题
        messages:      OpenAI 格式的对话历史（system + user + assistant + tool ...）
        trace:         结构化 ReAct 步骤列表，供日志和 API 返回
    """

    user_message: str
    messages: list[dict] = field(default_factory=list)
    trace: list[ReActStep] = field(default_factory=list)

    def append_assistant_message(self, message_dict: dict) -> None:
        """
        追加 assistant 消息到对话历史。

        当 LLM 返回 tool_calls 或 Final Answer 时调用，
        保证下一轮 LLM 能看到完整的上下文。
        """
        self.messages.append(message_dict)

    def append_tool_result(self, tool_call_id: str, content: str) -> None:
        """
        追加工具执行结果（Observation）到对话历史。

        role=tool 的消息会被 LLM 在下一轮读取，
        相当于 ReAct 中的 Observation 环节。
        """
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        )

    def add_trace_step(
        self,
        step: int,
        thought: str,
        *,
        action: str | None = None,
        observation: str | None = None,
        final_answer: str | None = None,
    ) -> ReActStep:
        """
        记录一步 ReAct trace，并追加到 trace 列表。

        返回:
            刚创建的 ReActStep 对象
        """
        react_step = ReActStep(
            step=step,
            thought=thought,
            action=action,
            observation=observation,
            final_answer=final_answer,
        )
        self.trace.append(react_step)
        return react_step
