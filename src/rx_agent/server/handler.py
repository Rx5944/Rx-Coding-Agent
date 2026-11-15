"""Transport-agnostic WebSocket session handler.

Fixes the v0 server's flaws: auth + origin checks, server-side autonomy ceiling, workspace allowlist,
async approvals (no input() on server stdin), real cancellation, and a reader that keeps reading while a
run is in progress (so `cancel` and `approval_response` can actually arrive).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .. import __version__
from ..config import MODES, Settings
from ..core.loop import Agent
from ..core.session import Session, SessionStore
from ..errors import RXError
from ..events import EventBus
from ..llm.base import LLMClient
from ..llm.registry import create_llm
from ..permissions.approvals import BrokerApprover
from ..permissions.policy import clamp_mode
from ..workspace.paths import Workspace
from .security import resolve_workspace, token_ok

log = logging.getLogger("rx.server")
AUTH_TIMEOUT = 10.0


class Connection(Protocol):
    async def send(self, obj: dict[str, Any]) -> None: ...
    async def receive(self) -> dict[str, Any] | None: ...


@dataclass
class ServerConfig:
    token: str
    roots: list[Path]
    settings: Settings
    max_mode: str = "ask"
    host: str = "127.0.0.1"
    port: int = 8000
    extra_hosts: set[str] = field(default_factory=set)
    extra_origins: set[str] = field(default_factory=set)
    llm_factory: Callable[[Settings], LLMClient] = create_llm
    sandbox_factory: Callable[..., Any] | None = None


class ConnectionHandler:
    def __init__(self, config: ServerConfig, store: SessionStore | None = None):
        self.cfg = config
        self.store = store or SessionStore(config.settings.data_dir)
        self.events = EventBus()
        self.broker = BrokerApprover()
        self.out: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.events.subscribe(self.out.put_nowait)
        self.agents: dict[Path, Agent] = {}
        self.run_task: asyncio.Task | None = None
        self._last_session: dict[Path, str] = {}

    # --------------------------------------------------------------- plumbing
    def _send(self, obj: dict[str, Any]) -> None:
        self.out.put_nowait(obj)

    def _error(self, code: str, message: str, **extra: Any) -> None:
        self._send({"type": "error", "code": code, "message": message, **extra})

    async def _writer(self, conn: Connection) -> None:
        try:
            while True:
                obj = await self.out.get()
                try:
                    await conn.send(obj)
                finally:
                    self.out.task_done()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - connection died; the reader loop will notice
            log.debug("writer stopped", exc_info=True)

    def _agent_for(self, workspace: Path) -> Agent:
        agent = self.agents.get(workspace)
        if agent is None:
            kwargs: dict[str, Any] = {}
            if self.cfg.sandbox_factory:
                kwargs["sandbox"] = self.cfg.sandbox_factory(self.cfg.settings, workspace)
            agent = Agent(llm=self.cfg.llm_factory(self.cfg.settings), settings=self.cfg.settings,
                          workspace=Workspace(workspace), events=self.events, approver=self.broker,
                          store=self.store, **kwargs)
            self.agents[workspace] = agent
        return agent

    # ------------------------------------------------------------------ serve
    async def serve(self, conn: Connection) -> None:
        writer = asyncio.create_task(self._writer(conn))
        try:
            try:
                first = await asyncio.wait_for(conn.receive(), AUTH_TIMEOUT)
            except asyncio.TimeoutError:
                self._error("unauthorized", "Authentication timed out.")
                return
            if not first or first.get("type") != "auth" or not token_ok(first.get("token"), self.cfg.token):
                self._error("unauthorized", "Invalid or missing token. Send {type:'auth', token} first.")
                return
            self._send({"type": "ready", "version": __version__, "max_mode": self.cfg.max_mode,
                        "modes": [m for m in MODES if clamp_mode(m, self.cfg.max_mode) == m],
                        "roots": [str(r) for r in self.cfg.roots], "model": self.cfg.settings.model,
                        "limits": {"max_run_tokens": self.cfg.settings.max_run_tokens,
                                   "max_run_seconds": self.cfg.settings.max_run_seconds}})
            while True:
                msg = await conn.receive()
                if msg is None:
                    break
                await self._dispatch(msg)
        finally:
            await self._shutdown(writer)

    async def _shutdown(self, writer: asyncio.Task) -> None:
        if self.run_task and not self.run_task.done():
            self.run_task.cancel()
            await asyncio.gather(self.run_task, return_exceptions=True)
        self.broker.cancel_all()
        try:
            await asyncio.wait_for(self.out.join(), 2)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            pass
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)

    # --------------------------------------------------------------- dispatch
    async def _dispatch(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        try:
            if kind == "run":
                self._start_run(msg)
            elif kind == "cancel":
                if self.run_task and not self.run_task.done():
                    self.run_task.cancel()
            elif kind == "approval_response":
                found = self.broker.resolve(str(msg.get("id")), bool(msg.get("approved")),
                                            bool(msg.get("remember")), msg.get("message"))
                if not found:
                    self._error("unknown_approval", "No pending approval with that id.")
            elif kind == "undo":
                await self._undo(msg)
            elif kind == "sessions":
                ws = resolve_workspace(msg.get("workspace"), self.cfg.roots)
                self._send({"type": "sessions", "sessions": self.store.list(str(ws))})
            elif kind == "snapshots":
                ws = resolve_workspace(msg.get("workspace"), self.cfg.roots)
                agent = self._agent_for(ws)
                items = await asyncio.to_thread(agent.snapshots.list) if agent.snapshots else []
                self._send({"type": "snapshots", "snapshots": items})
            elif kind == "ping":
                self._send({"type": "pong"})
            else:
                self._error("bad_request", f"Unknown message type: {kind!r}")
        except RXError as exc:
            self._error("bad_request", str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("dispatch failed")
            self._error("internal", f"{type(exc).__name__}: {exc}")

    def _start_run(self, msg: dict[str, Any]) -> None:
        if self.run_task and not self.run_task.done():
            self._error("busy", "A run is already in progress. Cancel it first.")
            return
        task_text = str(msg.get("task") or "").strip()
        if not task_text:
            self._error("bad_request", "task is required.")
            return
        workspace = resolve_workspace(msg.get("workspace"), self.cfg.roots)
        requested = str(msg.get("mode") or self.cfg.settings.mode).replace("-", "_")
        if requested not in MODES:
            self._error("bad_request", f"mode must be one of {', '.join(MODES)}")
            return
        mode = clamp_mode(requested, self.cfg.max_mode)
        if mode != requested:
            self.events.emit("warning", message=f"Mode '{requested}' is above this server's limit; using '{mode}'.")
        agent = self._agent_for(workspace)
        session: Session | None = None
        if msg.get("session_id"):
            session = self.store.load(str(msg["session_id"]))
            if session is None or session.workspace != str(workspace):
                self._error("bad_request", "Unknown session for this workspace.")
                return
        session = session or agent.new_session()
        if self._last_session.get(workspace) != session.id:
            agent.reset_file_tracking()  # new/other transcript => model must re-read before editing
        self._last_session[workspace] = session.id
        self.run_task = asyncio.create_task(self._run(agent, session, task_text, mode))

    async def _run(self, agent: Agent, session: Session, task: str, mode: str) -> None:
        try:
            result = await agent.run(session, task, mode)
            if result.status == "error":
                log.warning("run failed (session %s, model %s): %s", session.id, self.cfg.settings.model, result.error)
            self._send({"type": "run_finished", "result": result.to_dict()})
        except asyncio.CancelledError:
            self._send({"type": "run_finished", "result": {"status": "cancelled", "session_id": session.id}})
        except Exception as exc:  # noqa: BLE001
            log.exception("run crashed")
            self._error("internal", f"{type(exc).__name__}: {exc}")

    async def _undo(self, msg: dict[str, Any]) -> None:
        if self.run_task and not self.run_task.done():
            self._error("busy", "Cannot undo while a run is in progress.")
            return
        ws = resolve_workspace(msg.get("workspace"), self.cfg.roots)
        outcome = await self._agent_for(ws).undo(msg.get("snapshot_id"))
        self._send({"type": "undo_result", **outcome})
