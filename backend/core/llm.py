"""
LLM 通信层 — 负责和 OpenAI 兼容 API（智谱 GLM 等）交互。

职责:
  - 创建 API 客户端
  - 发送 chat completion 请求（支持 Tool Calling）
  - 返回原始 Message 对象，由 agent/loop.py 决定下一步
"""

import logging
from collections.abc import Callable, Iterator
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from core.config import get_settings

logger = logging.getLogger(__name__)


def _build_client() -> OpenAI:
    """
    根据 config 创建 OpenAI 兼容客户端。

    如果配置了 openai_base_url（如智谱 API 地址），
    会自动使用该地址，从而支持非 OpenAI 官方的服务。
    """
    settings = get_settings()
    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**client_kwargs)


def get_openai_client() -> OpenAI:
    """返回配置好的 OpenAI 兼容客户端（供视觉解析等复用）。"""
    return _build_client()


def chat_completion(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
) -> ChatCompletionMessage:
    """
    发送多轮对话请求，可选携带工具说明书。

    这是 Agent 循环中每一轮调用 LLM 的统一入口。

    参数:
        messages: OpenAI 格式的对话历史列表
        tools:    工具 schema 列表；为 None 时不传 tools 参数

    返回:
        LLM 回复的 Message 对象（含 content 和/或 tool_calls）

    异常:
        ValueError: API Key 未配置
    """
    settings = get_settings()

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    client = _build_client()

    request_kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.7,
    }

    if tools:
        request_kwargs["tools"] = tools
        logger.info("[LLM] 发送请求: model=%s, messages=%d 条, tools=%d 个",
                     settings.openai_model, len(messages), len(tools))
    else:
        logger.info("[LLM] 发送请求: model=%s, messages=%d 条, 无工具",
                     settings.openai_model, len(messages))

    response = client.chat.completions.create(**request_kwargs)

    message = response.choices[0].message
    finish_reason = response.choices[0].finish_reason

    logger.info(
        "[LLM] 收到响应: finish_reason=%s, tool_calls=%s, content_len=%d",
        finish_reason,
        len(message.tool_calls) if message.tool_calls else 0,
        len(message.content or ""),
    )

    if message.tool_calls:
        for tc in message.tool_calls:
            logger.info(
                "[LLM] 工具调用 JSON → name=%s, arguments=%s",
                tc.function.name,
                tc.function.arguments,
            )

    return message


def chat_completion_stream(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[Any]:
    """
    流式 chat completion — 逐 chunk 返回 OpenAI SDK 的 stream chunk。

    参数:
        messages:       OpenAI 格式对话历史
        tools:          可选工具 schema
        should_cancel:  返回 True 时中断流（用于「停止生成」）

    返回:
        OpenAI stream iterator 的每个 chunk
    """
    settings = get_settings()

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    client = _build_client()

    request_kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.7,
        "stream": True,
    }

    if tools:
        request_kwargs["tools"] = tools

    logger.info(
        "[LLM] 发送流式请求: model=%s, messages=%d 条",
        settings.openai_model,
        len(messages),
    )

    stream = client.chat.completions.create(**request_kwargs)

    for chunk in stream:
        if should_cancel and should_cancel():
            logger.info("[LLM] 流式请求被客户端取消")
            break
        yield chunk


def stream_text_completion(
    messages: list[dict],
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[str]:
    """
    流式生成纯文本回答 — 逐 token yield content 字符串。

    供 RAG / Memory 等无 Tool Calling 的链路使用；
    与 ReAct 的 plan_stream 不同，此处不做 Final Answer 过滤。
    """
    for chunk in chat_completion_stream(
        messages,
        tools=None,
        should_cancel=should_cancel,
    ):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
