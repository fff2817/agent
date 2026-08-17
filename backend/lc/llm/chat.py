"""
LLM 通信层 — 统一经 LangChain ChatOpenAI 调用（OpenAI 兼容 API / 智谱等）。

对外接口保持不变，供 agent / rag / memory / eval / 视觉解析复用:
  - get_chat_model()
  - chat_completion() / chat_completion_stream() / stream_text_completion()
  - get_openai_client()  （兼容旧调用；新代码请用 get_chat_model）
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from openai import OpenAI

from core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 兼容层：下游 parser / planner 仍按 OpenAI SDK 消息形态读取属性
# ---------------------------------------------------------------------------


@dataclass
class _FunctionCompat:
    name: str
    arguments: str


@dataclass
class _ToolCallCompat:
    id: str
    function: _FunctionCompat
    type: str = "function"


@dataclass
class ChatMessageCompat:
    """与 openai ChatCompletionMessage 属性对齐的轻量对象。"""

    content: str | None
    tool_calls: list[_ToolCallCompat] | None = None


@dataclass
class _FunctionDeltaCompat:
    name: str | None = None
    arguments: str | None = None


@dataclass
class _ToolCallDeltaCompat:
    index: int
    id: str | None = None
    function: _FunctionDeltaCompat | None = None
    type: str = "function"


@dataclass
class _DeltaCompat:
    content: str | None = None
    tool_calls: list[_ToolCallDeltaCompat] | None = None


@dataclass
class _ChoiceCompat:
    delta: _DeltaCompat
    finish_reason: str | None = None


@dataclass
class StreamChunkCompat:
    """与 openai stream chunk 属性对齐，供 plan_stream 使用。"""

    choices: list[_ChoiceCompat] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ChatModel 工厂
# ---------------------------------------------------------------------------


def get_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0.7,
) -> ChatOpenAI:
    """
    返回配置好的 LangChain ChatOpenAI（唯一推荐的模型入口）。

    参数:
        model:       覆盖默认 settings.openai_model（如视觉模型）
        temperature: 采样温度
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    kwargs: dict[str, Any] = {
        "api_key": settings.openai_api_key,
        "model": model or settings.openai_model,
        "temperature": temperature,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return ChatOpenAI(**kwargs)


def _build_client() -> OpenAI:
    """底层 OpenAI SDK 客户端（仅兼容 get_openai_client / 非 Chat 场景）。"""
    settings = get_settings()
    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**client_kwargs)


def get_openai_client() -> OpenAI:
    """返回 OpenAI 兼容客户端。聊天请改用 get_chat_model()。"""
    return _build_client()


# ---------------------------------------------------------------------------
# Message 转换
# ---------------------------------------------------------------------------


def _content_to_str(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif hasattr(block, "type") and getattr(block, "type", None) == "text":
                parts.append(str(getattr(block, "text", "") or ""))
        return "".join(parts) or None
    return str(content)


def _openai_tool_calls_to_lc(tool_calls: list[dict]) -> list[dict[str, Any]]:
    lc_calls: list[dict[str, Any]] = []
    for tc in tool_calls:
        raw_args = tc.get("function", {}).get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {"raw": raw_args}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {"raw": str(raw_args)}
        lc_calls.append(
            {
                "id": tc.get("id") or "",
                "name": tc.get("function", {}).get("name") or "",
                "args": args,
                "type": "tool_call",
            }
        )
    return lc_calls


def dict_messages_to_lc(messages: list[dict]) -> list[BaseMessage]:
    """OpenAI messages(dict) → LangChain BaseMessage 列表。"""
    converted: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            converted.append(SystemMessage(content=content or ""))
        elif role == "user":
            # 支持纯文本或多模态 content 列表（视觉）
            converted.append(HumanMessage(content=content if content is not None else ""))
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            text = content or ""
            if tool_calls:
                converted.append(
                    AIMessage(
                        content=text,
                        tool_calls=_openai_tool_calls_to_lc(tool_calls),
                    )
                )
            else:
                converted.append(AIMessage(content=text))
        elif role == "tool":
            converted.append(
                ToolMessage(
                    content=content or "",
                    tool_call_id=msg.get("tool_call_id") or "",
                )
            )
        else:
            raise ValueError(f"Unsupported message role: {role!r}")
    return converted


def ai_message_to_compat(message: AIMessage) -> ChatMessageCompat:
    """LangChain AIMessage → parser 可用的兼容 Message。"""
    content = _content_to_str(message.content)
    compat_calls: list[_ToolCallCompat] | None = None

    if message.tool_calls:
        compat_calls = []
        for tc in message.tool_calls:
            args = tc.get("args", {})
            if isinstance(args, str):
                arguments = args
            else:
                arguments = json.dumps(args, ensure_ascii=False)
            compat_calls.append(
                _ToolCallCompat(
                    id=str(tc.get("id") or ""),
                    function=_FunctionCompat(
                        name=str(tc.get("name") or ""),
                        arguments=arguments,
                    ),
                )
            )

    return ChatMessageCompat(content=content, tool_calls=compat_calls)


def _bind_tools(model: ChatOpenAI, tools: list[dict] | None) -> Any:
    if not tools:
        return model
    return model.bind_tools(tools)


# ---------------------------------------------------------------------------
# 对外：同步 / 流式 Chat（签名与旧版一致）
# ---------------------------------------------------------------------------


def chat_completion(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
) -> ChatMessageCompat:
    """
    发送多轮对话请求，可选携带工具说明书。

    返回兼容 OpenAI ChatCompletionMessage 属性的对象，供 parser 使用。
    """
    settings = get_settings()
    model = get_chat_model()
    runnable = _bind_tools(model, tools)
    lc_messages = dict_messages_to_lc(messages)

    if tools:
        logger.info(
            "[LLM] 发送请求: model=%s, messages=%d 条, tools=%d 个",
            settings.openai_model,
            len(messages),
            len(tools),
        )
    else:
        logger.info(
            "[LLM] 发送请求: model=%s, messages=%d 条, 无工具",
            settings.openai_model,
            len(messages),
        )

    response = runnable.invoke(lc_messages)
    if not isinstance(response, AIMessage):
        response = AIMessage(content=_content_to_str(getattr(response, "content", response)) or "")

    compat = ai_message_to_compat(response)
    logger.info(
        "[LLM] 收到响应: tool_calls=%s, content_len=%d",
        len(compat.tool_calls) if compat.tool_calls else 0,
        len(compat.content or ""),
    )
    if compat.tool_calls:
        for tc in compat.tool_calls:
            logger.info(
                "[LLM] 工具调用 JSON → name=%s, arguments=%s",
                tc.function.name,
                tc.function.arguments,
            )
    return compat


def _chunk_to_compat(chunk: AIMessageChunk) -> StreamChunkCompat:
    delta = _DeltaCompat(content=None, tool_calls=None)

    text = _content_to_str(chunk.content)
    if text:
        delta.content = text

    tool_call_chunks = getattr(chunk, "tool_call_chunks", None) or []
    if tool_call_chunks:
        deltas: list[_ToolCallDeltaCompat] = []
        for tcc in tool_call_chunks:
            if isinstance(tcc, dict):
                idx = int(tcc.get("index") or 0)
                name = tcc.get("name")
                args = tcc.get("args")
                tc_id = tcc.get("id")
            else:
                idx = int(getattr(tcc, "index", 0) or 0)
                name = getattr(tcc, "name", None)
                args = getattr(tcc, "args", None)
                tc_id = getattr(tcc, "id", None)

            fn = None
            if name or args:
                fn = _FunctionDeltaCompat(
                    name=name or None,
                    arguments=args if isinstance(args, str) else (args or None),
                )
                # LangChain 有时把增量 args 放在字符串里；非 str 时尽量序列化
                if fn.arguments is not None and not isinstance(fn.arguments, str):
                    fn.arguments = json.dumps(fn.arguments, ensure_ascii=False)

            deltas.append(
                _ToolCallDeltaCompat(
                    index=idx,
                    id=tc_id or None,
                    function=fn,
                )
            )
        delta.tool_calls = deltas

    return StreamChunkCompat(choices=[_ChoiceCompat(delta=delta)])


def chat_completion_stream(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[StreamChunkCompat]:
    """
    流式 chat completion — 逐 chunk 返回与 OpenAI stream 属性兼容的对象。
    """
    settings = get_settings()
    model = get_chat_model()
    runnable = _bind_tools(model, tools)
    lc_messages = dict_messages_to_lc(messages)

    logger.info(
        "[LLM] 发送流式请求: model=%s, messages=%d 条",
        settings.openai_model,
        len(messages),
    )

    for chunk in runnable.stream(lc_messages):
        if should_cancel and should_cancel():
            logger.info("[LLM] 流式请求被客户端取消")
            break
        if not isinstance(chunk, AIMessageChunk):
            # 部分版本可能直接给 AIMessage
            if isinstance(chunk, AIMessage):
                text = _content_to_str(chunk.content)
                yield StreamChunkCompat(
                    choices=[_ChoiceCompat(delta=_DeltaCompat(content=text))]
                )
            continue
        yield _chunk_to_compat(chunk)


def stream_text_completion(
    messages: list[dict],
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[str]:
    """
    流式生成纯文本回答 — 逐 token yield content 字符串。

    供 RAG / Memory 等无 Tool Calling 的链路使用。
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


def vision_completion(
    *,
    prompt: str,
    image_data_url: str,
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    """
    视觉模型调用（图片 → 文本），统一走 ChatOpenAI。
    """
    settings = get_settings()
    vision_model = (model or settings.openai_vision_model or settings.openai_model).strip()
    chat = get_chat_model(model=vision_model, temperature=temperature)
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    )
    response = chat.invoke([message])
    content = _content_to_str(getattr(response, "content", None))
    return (content or "").strip()
