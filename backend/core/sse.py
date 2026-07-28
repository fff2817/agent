"""
SSE 流式响应工具 — 供 /chat/stream、/rag/ask/stream、/memory/ask/stream 复用。

设计说明:
  - OpenAI SDK 为同步 API，FastAPI 路由为 async
  - 用「后台线程 + queue」桥接 sync producer → async generator
  - 统一 SSE 格式、响应头、客户端断开检测
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from collections.abc import AsyncIterator, Callable, Iterator

from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def format_sse_event(event: dict) -> str:
    """将 dict 格式化为 SSE 单行 data 事件。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def watch_client_disconnect(http_request: Request, cancelled: dict) -> None:
    """轮询检测客户端是否断开连接，用于触发 should_cancel。"""
    while not cancelled["value"]:
        if await http_request.is_disconnected():
            cancelled["value"] = True
            logger.info("[SSE] 客户端断开连接")
            return
        await asyncio.sleep(0.05)


def bridge_sync_iterator_to_sse(
    producer: Callable[[], Iterator[dict]],
    *,
    should_cancel: Callable[[], bool] | None = None,
    initial_events: list[dict] | None = None,
    on_value_error: Callable[[ValueError], dict] | None = None,
    on_exception: Callable[[], dict] | None = None,
) -> AsyncIterator[str]:
    """
    把同步 generator 桥接为 async SSE yield。

    producer 应 yield 事件 dict；结束时自然 return。
    若 producer 抛出 ValueError / Exception，转为 error 事件。
    """

    async def event_generator() -> AsyncIterator[str]:
        cancelled = {"value": False}
        event_queue: queue.Queue = queue.Queue()

        def _should_cancel() -> bool:
            return cancelled["value"] or (should_cancel() if should_cancel else False)

        def worker() -> None:
            try:
                for event in producer():
                    if _should_cancel():
                        break
                    event_queue.put(event)
                event_queue.put(None)
            except ValueError as exc:
                handler = on_value_error or (lambda e: {"type": "error", "detail": str(e)})
                event_queue.put(handler(exc))
            except Exception:
                logger.exception("[SSE] producer 执行失败")
                handler = on_exception or (
                    lambda: {
                        "type": "error",
                        "detail": "Failed to get a response from the language model. Please try again later.",
                    }
                )
                event_queue.put(handler())

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        for event in initial_events or []:
            yield format_sse_event(event)

        try:
            while True:
                try:
                    event = await asyncio.to_thread(event_queue.get, timeout=0.1)
                except queue.Empty:
                    if not thread.is_alive() and event_queue.empty():
                        break
                    continue

                if event is None:
                    break

                yield format_sse_event(event)

                if event.get("type") in {"cancelled", "error"}:
                    break
        finally:
            cancelled["value"] = True
            thread.join(timeout=2.0)

    return event_generator()


def create_sse_response(
    producer: Callable[[], Iterator[dict]],
    *,
    http_request: Request | None = None,
    should_cancel: Callable[[], bool] | None = None,
    initial_events: list[dict] | None = None,
) -> StreamingResponse:
    """
    创建标准 SSE StreamingResponse。

    若传入 http_request，会在 generator 外层额外监听断开（供 chat 等复杂场景）。
    """

    if http_request is not None:
        cancelled = {"value": False}

        async def wrapped_generator() -> AsyncIterator[str]:
            disconnect_task = asyncio.create_task(
                watch_client_disconnect(http_request, cancelled)
            )

            def combined_cancel() -> bool:
                return cancelled["value"] or (should_cancel() if should_cancel else False)

            gen = bridge_sync_iterator_to_sse(
                producer,
                should_cancel=combined_cancel,
                initial_events=initial_events,
            )

            try:
                async for chunk in gen:
                    yield chunk
            finally:
                cancelled["value"] = True
                disconnect_task.cancel()
                try:
                    await disconnect_task
                except asyncio.CancelledError:
                    pass

        return StreamingResponse(
            wrapped_generator(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return StreamingResponse(
        bridge_sync_iterator_to_sse(
            producer,
            should_cancel=should_cancel,
            initial_events=initial_events,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
