"""Deterministic LLM used by tests and the eval harness self-check."""
from __future__ import annotations

import json
from typing import Any

from .base import LLMClient, LLMResponse, ToolCall, Usage


def tool_call(name: str, call_id: str | None = None, **arguments: Any) -> ToolCall:
    return ToolCall(call_id or f"call_{name}", name, json.dumps(arguments))


class ScriptedLLM(LLMClient):
    """Plays back a list of steps. A step is an LLMResponse, a ToolCall, a list of ToolCalls,
    a string (final text), or a callable(messages) -> one of those."""

    def __init__(self, steps: list[Any], model: str = "scripted") -> None:
        self.model = model
        self.steps = list(steps)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages, tools=None, *, on_text=None, on_retry=None) -> LLMResponse:
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.steps:
            return LLMResponse(content="(script exhausted)")
        step = self.steps.pop(0)
        if callable(step):
            step = step(messages)
        if isinstance(step, str):
            step = LLMResponse(content=step)
        elif isinstance(step, list):
            step = LLMResponse(tool_calls=step)
        elif isinstance(step, ToolCall):
            step = LLMResponse(tool_calls=[step])
        if on_text and step.content:
            on_text(step.content)
        if not step.usage.total_tokens:
            step.usage = Usage(100, 20, 120)
        return step
