"""Typed event stream shared by the CLI, server, web UI and VS Code extension."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

log = logging.getLogger("rx.events")

# Every event the agent can emit. docs/PROTOCOL.md is generated from this table
# and tests assert the loop never emits an unregistered type.
EVENTS: dict[str, str] = {
    "task_started": "A run began. {task, session_id, mode}",
    "snapshot_created": "A restore point was saved. {snapshot_id, label}",
    "iteration_started": "A model step began. {iteration}",
    "assistant_delta": "Streaming text from the model. {text}",
    "assistant_message": "Full assistant text for a step. {text}",
    "llm_retry": "A model request is being retried. {attempt, delay, error}",
    "usage": "Token usage after a model call. {prompt_tokens, completion_tokens, total}",
    "context_compacted": "Old context was summarized. {before_tokens, after_tokens, method}",
    "tool_started": "A tool call is starting. {id, tool, summary, arguments}",
    "command_output": "Live output from run_command. {id, stream, text}",
    "tool_finished": "A tool call finished. {id, tool, ok, content, meta}",
    "tool_denied": "A tool call was blocked by policy or the user. {id, tool, reason}",
    "approval_required": "Waiting for the user. {id, tool, summary, reason, risk, preview, can_remember, timeout}",
    "approval_resolved": "The user answered. {id, approved}",
    "todos_updated": "The model updated its task list. {todos}",
    "verification": "A verification command ran. {command, ok, exit_code}",
    "warning": "Non-fatal problem. {message}",
    "task_completed": "Run finished normally. {result}",
    "task_cancelled": "Run was cancelled. {result}",
    "task_failed": "Run failed. {error, result}",
}


class EventBus:
    """Synchronous fan-out. Subscribers must be fast and must not raise."""

    def __init__(self) -> None:
        self._subs: list[Callable[[dict[str, Any]], None]] = []
        self._seq = 0

    def subscribe(self, fn: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        self._subs.append(fn)

        def unsubscribe() -> None:
            if fn in self._subs:
                self._subs.remove(fn)

        return unsubscribe

    def emit(self, type_: str, **data: Any) -> dict[str, Any]:
        if type_ not in EVENTS:
            log.warning("unregistered event type %s", type_)
        self._seq += 1
        event = {"type": type_, "seq": self._seq, "ts": time.time(), **data}
        for fn in list(self._subs):
            try:
                fn(event)
            except Exception:  # a broken subscriber must never break the agent
                log.exception("event subscriber failed")
        return event
