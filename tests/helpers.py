from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from rx_agent.config import Settings
from rx_agent.core.loop import Agent
from rx_agent.events import EventBus
from rx_agent.permissions.approvals import StaticApprover
from rx_agent.sandbox.local import LocalSandbox
from rx_agent.tools.base import ToolContext
from rx_agent.tools.tracker import FileTracker
from rx_agent.verify import Verifier
from rx_agent.workspace.index import CodeIndex
from rx_agent.workspace.paths import Workspace


def run(coro):
    return asyncio.run(coro)


class TempCase(unittest.TestCase):
    """Gives every test an isolated workspace + data dir."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="rxtest-")).resolve()
        self.root = self._tmp / "ws"
        self.root.mkdir()
        self.data = self._tmp / "data"
        self.data.mkdir()
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def settings(self, **kw: Any) -> Settings:
        base = dict(data_dir=self.data, snapshots=False, mode="auto", sandbox="local")
        base.update(kw)
        return Settings(**base)

    def ctx(self, **kw: Any) -> ToolContext:
        settings = self.settings(**kw)
        ws = Workspace(self.root)
        return ToolContext(workspace=ws, tracker=FileTracker(), settings=settings, events=EventBus(),
                           index=CodeIndex(ws.root), sandbox=LocalSandbox(settings, ws.root), verifier=Verifier(ws.root))

    def agent(self, llm, *, approver=None, mode="auto", store=None, **kw: Any) -> tuple[Agent, list[dict]]:
        settings = self.settings(mode=mode, **kw)
        events: list[dict] = []
        bus = EventBus()
        bus.subscribe(events.append)
        ws = Workspace(self.root)
        agent = Agent(llm=llm, settings=settings, workspace=ws, events=bus,
                      approver=approver or StaticApprover(True), sandbox=LocalSandbox(settings, ws.root), store=store)
        return agent, events


def assert_valid_transcript(test: unittest.TestCase, messages: list[dict[str, Any]]) -> None:
    """Every tool message answers a preceding assistant tool_call, and every call is answered."""
    open_calls: set[str] = set()
    for m in messages:
        if m["role"] == "assistant":
            test.assertFalse(open_calls, f"unanswered tool calls before next assistant turn: {open_calls}")
            open_calls = {c["id"] for c in m.get("tool_calls") or []}
        elif m["role"] == "tool":
            test.assertIn(m["tool_call_id"], open_calls, "orphan tool message")
            open_calls.discard(m["tool_call_id"])
        elif m["role"] == "user":
            test.assertFalse(open_calls, f"user message while tool calls unanswered: {open_calls}")
    test.assertFalse(open_calls, f"unanswered tool calls at end: {open_calls}")
