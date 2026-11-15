from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..llm.base import Usage


@dataclass
class RunState:
    task: str
    started: float = field(default_factory=time.time)
    iterations: int = 0
    status: str = "running"  # completed | cancelled | error | stuck | gave_up | iteration_limit | budget_exceeded
    final_response: str = ""
    error: str | None = None
    modified: set[str] = field(default_factory=set)
    read: set[str] = field(default_factory=set)
    tools_executed: int = 0
    verification: list[dict[str, Any]] = field(default_factory=list)
    dirty: bool = False  # files changed since the last passing verification
    verify_nudges: int = 0
    verify_fail_streak: int = 0
    empty_responses: int = 0
    guard_stop: bool = False
    approval_wait: float = 0.0
    snapshot_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    pending_results: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    status: str
    final_response: str
    iterations: int
    usage: dict[str, int]
    files_modified: list[str]
    files_read: list[str]
    tools_executed: int
    verification: dict[str, Any]
    snapshot_id: str | None
    session_id: str
    duration: float
    approval_wait: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
