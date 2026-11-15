from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..tools.base import Tool, ToolContext
from .commands import Risk, analyze_command

MODE_RANK = {"plan": 0, "ask": 1, "auto_edit": 2, "auto": 3}


def clamp_mode(requested: str, maximum: str) -> str:
    """Never exceed the server-side autonomy ceiling (a client cannot talk itself into 'auto')."""
    return requested if MODE_RANK[requested] <= MODE_RANK[maximum] else maximum


class Action(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class Decision:
    action: Action
    reason: str = ""
    risk: str = "normal"
    remember_key: str | None = None  # None => the user can't pre-approve this kind of action
    command: str | None = None


@dataclass
class PermissionPolicy:
    mode: str = "ask"
    sandboxed: bool = False
    allow_unsandboxed_auto: bool = False
    allowed_keys: set[str] = field(default_factory=set)

    def remember(self, key: str | None) -> None:
        if key:
            self.allowed_keys.add(key)

    def decide(self, tool: Tool, args: dict[str, Any], ctx: ToolContext) -> Decision:
        if tool.category in ("read", "meta"):
            return Decision(Action.ALLOW, risk="safe")
        if tool.category == "edit":
            return self._edit(tool, args, ctx)
        if tool.category == "exec":
            return self._exec(tool, args, ctx)
        return Decision(Action.ASK, f"unknown tool category {tool.category}")

    # ------------------------------------------------------------------ edits
    def _edit(self, tool: Tool, args: dict[str, Any], ctx: ToolContext) -> Decision:
        if self.mode == "plan":
            return Decision(Action.DENY, "Plan mode is read-only. Describe the change instead of making it.")
        secret = False
        for raw in tool.paths(args):
            try:
                rel = ctx.workspace.rel(ctx.workspace.resolve(raw))
            except Exception:  # noqa: BLE001 - the tool itself will report the path problem
                continue
            kind = ctx.workspace.sensitivity(rel)
            if kind == "git":
                return Decision(Action.DENY, f"{rel} is git internals; editing it is not allowed.", "dangerous")
            secret |= kind == "secret"
        if secret:
            return Decision(Action.ASK, "This file may contain secrets.", "sensitive")
        if self.mode in ("auto_edit", "auto") or "edit:*" in self.allowed_keys:
            return Decision(Action.ALLOW, risk="normal")
        return Decision(Action.ASK, "Modify files in the workspace.", "normal", remember_key="edit:*")

    # ------------------------------------------------------------------- exec
    def _exec(self, tool: Tool, args: dict[str, Any], ctx: ToolContext) -> Decision:
        command = tool.command(ctx, args) if hasattr(tool, "command") else None
        if not command:
            return Decision(Action.ALLOW, risk="safe")  # the tool reports its own error
        cwd = ctx.workspace.root
        if args.get("cwd"):
            try:
                cwd = ctx.workspace.resolve(args["cwd"])
            except Exception:  # noqa: BLE001
                pass
        a = analyze_command(command, ctx.workspace.root, cwd)
        reason = "; ".join(a.reasons) or "runs a command"
        if a.risk == Risk.DANGEROUS:
            return Decision(Action.DENY, f"Blocked: {reason}.", "dangerous", command=command)
        if a.risk == Risk.SAFE:
            return Decision(Action.ALLOW, risk="safe", command=command)
        if self.mode == "plan":
            return Decision(Action.DENY, f"Plan mode only allows read-only commands ({reason}).", command=command)
        if a.risk == Risk.SENSITIVE:
            return Decision(Action.ASK, reason, "sensitive", command=command)
        key = f"exec:{a.key}" if a.key else None
        if key and key in self.allowed_keys:
            return Decision(Action.ALLOW, risk="normal", command=command)
        trusted_runner = tool.name == "run_tests" and self.mode in ("auto_edit", "auto")
        if trusted_runner or (self.mode == "auto" and (self.sandboxed or self.allow_unsandboxed_auto)):
            return Decision(Action.ALLOW, risk="normal", command=command)
        if self.mode == "auto":
            reason += " (no sandbox available, so auto mode still asks; install bubblewrap/Docker or set RX_ALLOW_UNSANDBOXED_AUTO=1)"
        return Decision(Action.ASK, reason, "normal", remember_key=key, command=command)
