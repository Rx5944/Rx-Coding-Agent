"""The agent loop: async, cancellable, streaming, permission-aware, self-verifying."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..errors import LLMError
from ..events import EventBus
from ..llm.base import LLMClient, LLMResponse, ToolCall
from ..permissions.approvals import Approver, ApprovalRequest, StaticApprover
from ..permissions.policy import Action, PermissionPolicy
from ..sandbox import create_sandbox
from ..sandbox.base import Sandbox
from ..snapshots import Snapshots
from ..tools import ToolRegistry, default_registry
from ..tools.base import Tool, ToolContext, ToolResult
from ..tools.tracker import FileTracker
from ..tools.validate import validate_args
from ..util import estimate_tokens, truncate_middle
from ..verify import Verifier, read_project_instructions
from ..workspace.index import CodeIndex
from ..workspace.paths import Workspace
from .context import ContextManager, tools_tokens
from .guard import LoopGuard
from .prompts import build_system_prompt
from .session import Session, SessionStore
from .state import RunResult, RunState

log = logging.getLogger("rx.loop")
DOC_SUFFIXES = (".md", ".txt", ".rst")
PUBLIC_META = {"path", "paths", "diff", "exit_code", "timed_out", "duration", "command", "created", "count",
               "is_verification", "sandbox"}


def parse_tool_arguments(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Tolerant JSON parsing: fixes code fences and trailing commas that weak models emit."""
    text = (raw or "").strip()
    if not text:
        return {}, None
    unfenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    for candidate in (text, unfenced, re.sub(r",\s*([}\]])", r"\1", unfenced)):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value, None
        return None, "arguments must be a JSON object"
    return None, "arguments were not valid JSON"


def _event_args(args: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in args.items():
        out[k] = truncate_middle(v, 2000) if isinstance(v, str) else v
    return out


@dataclass
class Prepared:
    call: ToolCall
    tool: Tool | None
    args: dict[str, Any]
    error: str | None = None


class Agent:
    def __init__(
        self,
        *,
        llm: LLMClient,
        settings: Settings,
        workspace: Workspace,
        events: EventBus | None = None,
        approver: Approver | None = None,
        registry: ToolRegistry | None = None,
        sandbox: Sandbox | None = None,
        store: SessionStore | None = None,
        snapshots: Snapshots | None = None,
    ) -> None:
        self.llm = llm
        self.settings = settings
        self.workspace = workspace
        self.events = events or EventBus()
        self.approver: Approver = approver or StaticApprover(False)
        self.registry = registry or default_registry()
        self.sandbox = sandbox or create_sandbox(settings, workspace.root)
        self.store = store
        self.snapshots = snapshots if snapshots is not None else (
            Snapshots(workspace.root, settings.data_dir) if settings.snapshots else None)
        self.tracker = FileTracker()
        self.index = CodeIndex(workspace.root)
        self.verifier = Verifier(workspace.root)
        self.policy = PermissionPolicy(mode=settings.mode, sandboxed=self.sandbox.isolated,
                                       allow_unsandboxed_auto=settings.allow_unsandboxed_auto)
        self.context = ContextManager(settings, self.events)

    # ------------------------------------------------------------------ public
    def new_session(self) -> Session:
        return Session(workspace=str(self.workspace.root))

    def reset_file_tracking(self) -> None:
        """Call after undo: the model must re-read files before editing again."""
        self.tracker = FileTracker()

    async def run(self, session: Session, user_message: str, mode: str | None = None) -> RunResult:
        mode = mode or self.settings.mode
        self.policy.mode = mode
        state = RunState(task=user_message)
        guard = LoopGuard()
        session.messages.append({"role": "user", "content": user_message})
        if not session.title:
            session.title = user_message.strip().splitlines()[0][:80] if user_message.strip() else "session"
        self.events.emit("task_started", task=user_message, session_id=session.id, mode=mode)
        if mode != "plan":
            state.snapshot_id = await self._snapshot(session, user_message)
        try:
            await self._loop(session, state, guard, mode)
        except asyncio.CancelledError:
            state.status = "cancelled"
            self._repair(session, state)
            result = self._result(session, state)
            self._persist(session)
            self.events.emit("task_cancelled", result=result.to_dict())
            raise
        except LLMError as exc:
            state.status, state.error = "error", str(exc)
            self._repair(session, state)
            result = self._result(session, state)
            self._persist(session)
            self.events.emit("task_failed", error=str(exc), result=result.to_dict())
            return result
        except Exception as exc:  # noqa: BLE001
            log.exception("agent run crashed")
            state.status, state.error = "error", f"Internal error: {type(exc).__name__}: {exc}"
            self._repair(session, state)
            result = self._result(session, state)
            self._persist(session)
            self.events.emit("task_failed", error=state.error, result=result.to_dict())
            return result
        result = self._result(session, state)
        self._persist(session)
        self.events.emit("task_completed", result=result.to_dict())
        return result

    # ------------------------------------------------------------------- loop
    def _system_prompt(self, mode: str) -> str:
        name, text = read_project_instructions(self.workspace.root)
        return build_system_prompt(
            workspace_name=self.workspace.root.name, mode=mode, sandbox_kind=self.sandbox.kind,
            network=self.settings.sandbox_network or not self.sandbox.isolated,
            instructions_name=name, instructions=text, commands=self.verifier.detect(),
        )

    def _tool_context(self, session: Session) -> ToolContext:
        return ToolContext(workspace=self.workspace, tracker=self.tracker, settings=self.settings, events=self.events,
                           index=self.index, sandbox=self.sandbox, verifier=self.verifier, session=session)

    async def _loop(self, session: Session, state: RunState, guard: LoopGuard, mode: str) -> None:
        base_ctx = self._tool_context(session)
        for _ in range(self.settings.max_iterations):
            budget_reason = self._over_budget(state)
            if budget_reason:
                await self._finish_with_summary(session, state, budget_reason, "budget_exceeded")
                return
            state.iterations += 1
            self.events.emit("iteration_started", iteration=state.iterations)
            self.context.age_prune(session.messages, self.settings.prune_keep_turns)
            system = self._system_prompt(mode)
            tools = self.registry.schemas(mode)
            fixed = estimate_tokens(system) + tools_tokens(tools)
            await self.context.maybe_compact(session, self.llm, fixed)
            messages = [{"role": "system", "content": system}, *session.messages]
            estimated = self.context.estimate(session.messages, fixed)
            resp = await self._call_llm(messages, tools, state, session, estimated)

            assistant: dict[str, Any] = {"role": "assistant", "content": resp.content or ""}
            truncated = resp.finish_reason == "length"
            prepared = [self._prepare(c, truncated) for c in resp.tool_calls]
            if prepared:
                assistant["tool_calls"] = [
                    {"id": p.call.id, "type": "function",
                     "function": {"name": p.call.name,
                                  "arguments": json.dumps(p.args)}}
                    for p in prepared]
            session.messages.append(assistant)
            if resp.content:
                self.events.emit("assistant_message", text=resp.content)

            if not prepared:
                if await self._maybe_continue(session, state, resp, mode):
                    continue
                state.status, state.final_response = "completed", resp.content
                return

            await self._execute(session, state, guard, base_ctx, prepared)
            if state.guard_stop:
                await self._finish_with_summary(
                    session, state, "You keep repeating the same action with the same result.", "stuck")
                return
            if state.verify_fail_streak >= self.settings.max_verify_failures:
                await self._finish_with_summary(
                    session, state, f"Verification has failed {state.verify_fail_streak} times in a row.", "gave_up")
                return
        await self._finish_with_summary(session, state, "You reached the step limit for this run.", "iteration_limit")

    def _over_budget(self, state: RunState) -> str | None:
        """Token / active-time budgets. Time spent waiting for the human is not counted against the agent."""
        cfg = self.settings
        if cfg.max_run_tokens and state.usage.total_tokens >= cfg.max_run_tokens:
            return (f"This run used {state.usage.total_tokens:,} tokens, reaching its budget of {cfg.max_run_tokens:,} "
                    "(raise RX_MAX_RUN_TOKENS to allow more).")
        active = time.time() - state.started - state.approval_wait
        if cfg.max_run_seconds and active >= cfg.max_run_seconds:
            return f"This run has been active for {active:.0f}s, reaching its time budget of {cfg.max_run_seconds}s."
        return None

    async def _maybe_continue(self, session: Session, state: RunState, resp: LLMResponse, mode: str) -> bool:
        """Decide whether a tool-less reply is really the end. Returns True to keep looping."""
        if not resp.content.strip():
            state.empty_responses += 1
            if state.empty_responses <= 2:
                session.messages.append({"role": "user", "content": "<system-reminder>Your last reply was empty. "
                                         "Continue the task with a tool call, or give your final report.</system-reminder>"})
                return True
            return False
        code_changed = any(not p.endswith(DOC_SUFFIXES) for p in state.modified)
        if (mode != "plan" and state.dirty and code_changed and state.verify_nudges < self.settings.max_verify_nudges):
            state.verify_nudges += 1
            cmds = self.verifier.detect()
            hint = (" Detected commands: " + ", ".join(f"`{v}`" for v in cmds.values()) + ".") if cmds else ""
            files = ", ".join(sorted(state.modified)[:8])
            session.messages.append({"role": "user", "content": (
                f"<system-reminder>You modified files ({files}) but have not run any verification since. Run the "
                f"relevant tests/checks (or execute the code) and fix failures before finishing.{hint} If verification "
                "is genuinely impossible here, say so explicitly in your final report.</system-reminder>")})
            return True
        return False

    async def _call_llm(self, messages, tools, state: RunState, session: Session, estimated: int) -> LLMResponse:
        resp = await self.llm.complete(
            messages, tools or None,
            on_text=lambda t: self.events.emit("assistant_delta", text=t),
            on_retry=lambda **kw: self.events.emit("llm_retry", **kw),
        )
        state.usage.add(resp.usage)
        for key, value in resp.usage.to_dict().items():
            session.usage[key] = session.usage.get(key, 0) + value
        self.context.observe(resp.usage.prompt_tokens, estimated)
        self.events.emit("usage", prompt_tokens=resp.usage.prompt_tokens,
                         completion_tokens=resp.usage.completion_tokens, total=resp.usage.total_tokens)
        return resp

    async def _finish_with_summary(self, session: Session, state: RunState, reason: str, status: str) -> None:
        session.messages.append({"role": "user", "content": (
            f"<system-reminder>{reason} Stop using tools. Write your final report now: what is done, what is not, "
            "the current state of the code, and what you would try next.</system-reminder>")})
        system = self._system_prompt("plan")
        resp = await self._call_llm([{"role": "system", "content": system}, *session.messages], None, state, session, 0)
        session.messages.append({"role": "assistant", "content": resp.content or ""})
        state.status, state.final_response = status, resp.content
        if resp.content:
            self.events.emit("assistant_message", text=resp.content)

    # ------------------------------------------------------------------ tools
    def _prepare(self, call: ToolCall, truncated: bool = False) -> Prepared:
        """Parse AND validate arguments up front. Nothing downstream (policy, approval preview, execution) ever
        sees unvalidated arguments, so a malformed call becomes a recoverable error message for the model."""
        tool = self.registry.get(call.name)
        args, err = parse_tool_arguments(call.arguments)
        if tool is None:
            return Prepared(call, None, args or {}, f"Unknown tool '{call.name}'. Available tools: {', '.join(self.registry.names())}")
        if err or args is None:
            hint = (" Your reply was CUT OFF by the model's output-token limit, so this call is incomplete. Send smaller "
                    "pieces: split big files into several files, or write them in several steps." if truncated else
                    " Send a single valid JSON object matching the tool's parameters.")
            return Prepared(call, tool, {}, f"Could not parse arguments for {call.name}: {err}.{hint}")
        clean, verr = validate_args(tool.parameters, args)
        if verr or clean is None:
            hint = (" (Your reply was cut off by the output-token limit; send smaller pieces.)" if truncated else "")
            return Prepared(call, tool, {}, f"Invalid arguments for {call.name}: {verr}.{hint}\n"
                            f"Expected parameters: {json.dumps(tool.parameters)}")
        return Prepared(call, tool, clean)

    async def _execute(self, session: Session, state: RunState, guard: LoopGuard, ctx: ToolContext,
                       prepared: list[Prepared]) -> None:
        batch: list[Prepared] = []

        async def flush() -> None:
            if not batch:
                return
            items = list(batch)
            batch.clear()
            outs = await asyncio.gather(*[self._run_tool(p, ctx.for_call(p.call.id), state, guard) for p in items],
                                        return_exceptions=True)
            for p, out in zip(items, outs):
                if isinstance(out, asyncio.CancelledError):
                    raise out
                state.pending_results[p.call.id] = self._internal_error(p, out) if isinstance(out, BaseException) else out

        for p in prepared:
            if p.error or p.tool is None:
                await flush()
                state.pending_results[p.call.id] = p.error or "Tool unavailable."
                self.events.emit("tool_denied", id=p.call.id, tool=p.call.name, reason=p.error)
                continue
            try:
                call_ctx = ctx.for_call(p.call.id)
                decision = self.policy.decide(p.tool, p.args, call_ctx)
                if decision.action == Action.ALLOW and p.tool.concurrency_safe:
                    batch.append(p)
                    continue
                await flush()
                denial = await self._authorize(p, decision, call_ctx, state)
                if denial:
                    state.pending_results[p.call.id] = denial
                    continue
                state.pending_results[p.call.id] = await self._run_tool(p, call_ctx, state, guard)
            except Exception as exc:  # noqa: BLE001 - one bad tool call must never end the whole run
                state.pending_results[p.call.id] = self._internal_error(p, exc)
        await flush()
        for p in prepared:  # results are appended in the model's original call order
            session.messages.append({"role": "tool", "tool_call_id": p.call.id,
                                     "content": state.pending_results.pop(p.call.id)})

    def _internal_error(self, p: Prepared, exc: BaseException) -> str:
        log.error("tool call %s crashed", p.call.name, exc_info=exc)
        self.events.emit("warning", message=f"{p.call.name} hit an internal error ({type(exc).__name__}: {exc}); the agent will continue.")
        return (f"Internal error while handling {p.call.name}: {type(exc).__name__}: {exc}. "
                "This call was not performed. Check your arguments and try again or take a different approach.")

    async def _authorize(self, p: Prepared, decision, ctx: ToolContext, state: RunState) -> str | None:
        assert p.tool is not None
        if decision.action == Action.DENY:
            self.events.emit("tool_denied", id=p.call.id, tool=p.tool.name, reason=decision.reason)
            return f"Action blocked: {decision.reason} Choose a different approach."
        if decision.action == Action.ALLOW:
            return None
        try:
            preview = await p.tool.preview(ctx, p.args) or decision.command
        except Exception as exc:  # noqa: BLE001 - a preview is a nicety; never let it kill the run
            log.warning("preview for %s failed: %s", p.tool.name, exc)
            preview = decision.command
        req = ApprovalRequest(tool=p.tool.name, summary=p.tool.summary(p.args), reason=decision.reason,
                              risk=decision.risk, arguments=_event_args(p.args), preview=preview,
                              can_remember=bool(decision.remember_key))
        self.events.emit("approval_required", id=req.id, tool=req.tool, summary=req.summary, reason=req.reason,
                         risk=req.risk, preview=req.preview, can_remember=req.can_remember,
                         timeout=getattr(self.approver, "timeout", None))
        waited = time.monotonic()
        try:
            resp = await self.approver.request(req)
        finally:
            state.approval_wait += time.monotonic() - waited
        self.events.emit("approval_resolved", id=req.id, approved=resp.approved)
        if not resp.approved:
            self.events.emit("tool_denied", id=p.call.id, tool=p.tool.name, reason=resp.message or "denied by user")
            note = f" Their note: {resp.message}" if resp.message else ""
            return ("The user denied this action." + note +
                    " Do not retry the same action; take a different approach or explain what you need.")
        if resp.remember and decision.remember_key:
            self.policy.remember(decision.remember_key)
        return None

    async def _run_tool(self, p: Prepared, ctx: ToolContext, state: RunState, guard: LoopGuard) -> str:
        assert p.tool is not None
        tool = p.tool
        self.events.emit("tool_started", id=p.call.id, tool=tool.name, summary=tool.summary(p.args),
                         arguments=_event_args(p.args))
        result: ToolResult = await self.registry.execute(ctx, tool, p.args)
        state.tools_executed += 1
        if tool.category == "edit" and result.ok:
            state.modified.update(result.meta.get("paths", []))
            state.dirty = True
        elif tool.name == "read_file" and result.ok and result.meta.get("path"):
            state.read.add(result.meta["path"])
        if tool.category == "exec" and result.meta.get("is_verification"):
            entry = {"command": result.meta.get("command"), "ok": result.ok, "exit_code": result.meta.get("exit_code")}
            state.verification.append(entry)
            self.events.emit("verification", **entry)
            if result.ok:
                state.dirty, state.verify_fail_streak = False, 0
            else:
                state.verify_fail_streak += 1
        verdict = guard.record(tool.name, p.args, result.content)
        content = result.content
        if verdict != "ok":
            content += "\n[rx: you have made this exact call repeatedly with the same outcome. Change your approach.]"
        state.guard_stop |= verdict == "stop"
        meta = {k: (truncate_middle(v, 8000) if isinstance(v, str) else v) for k, v in result.meta.items() if k in PUBLIC_META}
        self.events.emit("tool_finished", id=p.call.id, tool=tool.name, ok=result.ok,
                         content=truncate_middle(content, 8000), meta=meta)
        return content

    # ---------------------------------------------------------------- helpers
    async def _snapshot(self, session: Session, label: str) -> str | None:
        if self.snapshots is None:
            return None
        try:
            sid = await asyncio.to_thread(self.snapshots.create, f"before: {label.strip().splitlines()[0][:100]}")
        except Exception as exc:  # noqa: BLE001
            self.events.emit("warning", message=f"Could not create a restore point: {exc}")
            return None
        session.snapshots.append({"id": sid, "label": label[:100], "ts": time.time()})
        self.events.emit("snapshot_created", snapshot_id=sid, label=label[:100])
        return sid

    def _repair(self, session: Session, state: RunState) -> None:
        """Make the transcript valid again after a cancel/crash: every tool_call needs a tool result."""
        idx = next((i for i in range(len(session.messages) - 1, -1, -1)
                    if session.messages[i].get("role") == "assistant" and session.messages[i].get("tool_calls")), None)
        if idx is None:
            return
        answered = {m.get("tool_call_id") for m in session.messages[idx + 1:] if m.get("role") == "tool"}
        for call in session.messages[idx]["tool_calls"]:
            if call["id"] not in answered:
                content = state.pending_results.pop(call["id"], None) or "[cancelled before this tool call finished]"
                session.messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})

    def _persist(self, session: Session) -> None:
        if self.store is not None:
            try:
                self.store.save(session)
            except OSError as exc:
                self.events.emit("warning", message=f"Could not save session: {exc}")

    def _result(self, session: Session, state: RunState) -> RunResult:
        ran = bool(state.verification)
        return RunResult(
            status=state.status, final_response=state.final_response, iterations=state.iterations,
            usage=state.usage.to_dict(), files_modified=sorted(state.modified),
            files_read=sorted(state.read | set(self.tracker.files_read())), tools_executed=state.tools_executed,
            verification={"ran": ran, "passed": (state.verification[-1]["ok"] if ran else None),
                          "dirty_since_last_pass": state.dirty, "commands": state.verification[-10:]},
            snapshot_id=state.snapshot_id, session_id=session.id, duration=round(time.time() - state.started, 2),
            approval_wait=round(state.approval_wait, 2), error=state.error,
        )

    async def undo(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """Restore the workspace to a restore point (default: the most recent)."""
        if self.snapshots is None:
            return {"ok": False, "error": "Snapshots are disabled."}
        if snapshot_id is None:
            listing = await asyncio.to_thread(self.snapshots.list, 1)
            if not listing:
                return {"ok": False, "error": "No restore points exist for this workspace."}
            snapshot_id = listing[0]["id"]
        try:
            outcome = await asyncio.to_thread(self.snapshots.restore, snapshot_id)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        self.reset_file_tracking()
        return {"ok": True, "snapshot_id": snapshot_id, **outcome}
