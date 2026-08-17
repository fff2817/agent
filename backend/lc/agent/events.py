"""SSE / 流式事件契约（与 api.chat 对齐）。"""

from __future__ import annotations

from typing import Any, TypedDict


class TokenEvent(TypedDict):
    type: str  # "token"
    content: str


class StepEvent(TypedDict):
    type: str  # "step"
    step: dict[str, Any]


class DoneEvent(TypedDict, total=False):
    type: str  # "done"
    response: str
    steps: list[dict[str, Any]]


def token_event(content: str) -> dict[str, Any]:
    return {"type": "token", "content": content}


def step_event(step: dict[str, Any]) -> dict[str, Any]:
    return {"type": "step", "step": step}


def done_event(response: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "done", "response": response, "steps": steps}
