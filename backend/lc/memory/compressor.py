"""
上下文压缩 — 最近 N 轮原文保留 + 更早对话摘要（可选 LLM）。

失败时回退到 trim_messages / 窗口截断，保证 Agent 始终能拿到合法 history。
"""

from __future__ import annotations

import logging

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    get_buffer_string,
    trim_messages,
)

from core.config import get_settings
from lc.llm.chat import chat_completion

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = (
    "你是对话摘要助手。请将以下多轮对话压缩为简洁的中文要点，"
    "保留用户偏好、已确认事实、未完成意图与关键约束。"
    "不要编造；输出一段连续摘要，不要列表编号装饰。"
)


class ContextCompressor:
    """将完整 BaseMessage 历史压缩为适合注入 Prompt 的短历史。"""

    def compress(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if not messages:
            return []

        settings = get_settings()
        keep_recent = max(1, settings.max_session_turns)
        # 每轮 = Human + AI，故消息条数约为 2 * turns
        keep_messages = keep_recent * 2

        if len(messages) <= keep_messages:
            return list(messages)

        older = messages[:-keep_messages]
        recent = messages[-keep_messages:]

        summary_text = ""
        if settings.session_summary_enabled:
            summary_text = self._summarize(older)

        compressed: list[BaseMessage] = []
        if summary_text:
            compressed.append(
                HumanMessage(
                    content=(
                        "【早期对话摘要】（系统压缩，非用户新输入）\n"
                        f"{summary_text}\n"
                        "请结合该摘要与后续原文继续对话。"
                    )
                )
            )
            # 保证摘要后仍以 assistant/user 交替合理：补一条占位确认
            compressed.append(
                AIMessage(content="好的，我已了解之前的对话要点，请继续。")
            )
        else:
            # 摘要关闭或失败：丢掉 older，仅保留 recent（行为接近旧 FIFO）
            logger.info(
                "[Compressor] 无摘要，丢弃最早 %d 条，保留最近 %d 条",
                len(older),
                len(recent),
            )

        compressed.extend(recent)
        return self._token_trim(compressed)

    def _summarize(self, messages: list[BaseMessage]) -> str:
        if not messages:
            return ""

        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("[Compressor] 无 API Key，跳过 LLM 摘要")
            return ""

        transcript = get_buffer_string(messages)
        # 防止摘要请求本身过长
        if len(transcript) > 8000:
            transcript = transcript[:8000] + "\n…(截断)"

        try:
            response = chat_completion(
                [
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {
                        "role": "user",
                        "content": f"请摘要以下对话：\n\n{transcript}",
                    },
                ],
                tools=None,
            )
            text = (response.content or "").strip()
            if text:
                logger.info("[Compressor] 摘要完成, len=%d", len(text))
            return text
        except Exception:
            logger.exception("[Compressor] LLM 摘要失败，将回退为窗口截断")
            return ""

    def _token_trim(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        settings = get_settings()
        try:
            trimmed = trim_messages(
                messages,
                max_tokens=settings.session_compress_max_tokens,
                token_counter="approximate",
                strategy="last",
                start_on="human",
                include_system=True,
                allow_partial=False,
            )
            return list(trimmed)
        except Exception:
            logger.exception("[Compressor] trim_messages 失败，返回原列表")
            return messages


def messages_to_openai_dicts(messages: list[BaseMessage]) -> list[dict]:
    """BaseMessage → OpenAI role/content dict（跳过摘要用的临时 system 以外的特殊类型）。"""
    from langchain_core.messages import convert_to_openai_messages

    return list(convert_to_openai_messages(messages))
