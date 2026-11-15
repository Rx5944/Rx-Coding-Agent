from __future__ import annotations

import shlex
from typing import Any

from ..errors import ToolError
from ..util import truncate_middle
from ..verify import is_verification_command
from .base import Tool, ToolContext, ToolResult


def format_exec(command: str, res, limit: int) -> str:
    status = f"TIMED OUT after {res.duration:.0f}s (process tree killed)" if res.timed_out else f"exit code: {res.exit_code}"
    parts = [f"$ {command}", f"{status}  ({res.duration:.1f}s, sandbox={res.sandbox})"]
    half = max(2000, limit // 2)
    if res.stdout.strip():
        parts += ["--- stdout ---", truncate_middle(res.stdout.rstrip(), half)]
    if res.stderr.strip():
        parts += ["--- stderr ---", truncate_middle(res.stderr.rstrip(), half)]
    if not res.stdout.strip() and not res.stderr.strip():
        parts.append("(no output)")
    return "\n".join(parts)


async def execute(ctx: ToolContext, command: str, cwd_arg: str | None, timeout: int | None) -> ToolResult:
    if ctx.sandbox is None:
        raise ToolError("No sandbox is configured; commands cannot run.")
    cwd = ctx.workspace.resolve(cwd_arg) if cwd_arg else ctx.workspace.root
    if not cwd.is_dir():
        raise ToolError(f"cwd is not a directory: {cwd_arg}")
    call_id = ctx.call_id

    def on_output(stream: str, text: str) -> None:
        ctx.events.emit("command_output", id=call_id, stream=stream, text=text)

    limit = timeout or ctx.settings.command_timeout
    res = await ctx.sandbox.run(command, cwd=cwd, timeout=limit, on_output=on_output)
    verification = is_verification_command(command)
    return ToolResult(
        ok=res.ok,
        content=format_exec(command, res, ctx.settings.max_output_chars),
        meta={"exit_code": res.exit_code, "timed_out": res.timed_out, "duration": round(res.duration, 2),
              "command": command, "is_verification": verification, "sandbox": res.sandbox},
    )


class RunCommand(Tool):
    name = "run_command"
    category = "exec"
    description = (
        "Run a shell command in the workspace (bash). Output is captured; long output keeps the start and END. "
        "Commands are killed after the timeout. Prefer dedicated tools (read_file, grep, edit_file) for files."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command."},
            "cwd": {"type": "string", "description": "Subdirectory to run in (default: workspace root)."},
            "timeout": {"type": "integer", "minimum": 1, "maximum": 900, "description": "Seconds (default 120)."},
        },
        "required": ["command"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        cmd = args.get("command", "")
        return "$ " + (cmd if len(cmd) < 140 else cmd[:137] + "…")

    def command(self, ctx: ToolContext, args: dict[str, Any]) -> str | None:
        return args.get("command")

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await execute(ctx, args["command"], args.get("cwd"), args.get("timeout"))


class RunTests(Tool):
    name = "run_tests"
    category = "exec"
    description = (
        "Run the project's test suite using the auto-detected (or RX.md-declared) command. "
        "Optionally pass extra arguments such as a test path or '-k name'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "args": {"type": "string", "description": "Extra arguments, e.g. 'tests/test_api.py -k login'."},
            "kind": {"type": "string", "enum": ["test", "lint", "typecheck", "build"], "description": "Default: test."},
        },
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"run {args.get('kind', 'test')}s" + (f" {args['args']}" if args.get("args") else "")

    def command(self, ctx: ToolContext, args: dict[str, Any]) -> str | None:
        detected = ctx.verifier.detect() if ctx.verifier else {}
        base = detected.get(args.get("kind", "test"))
        if not base:
            return None
        extra = args.get("args", "")
        if extra:
            try:
                extra = shlex.join(shlex.split(extra))
            except ValueError as exc:
                raise ToolError(f"Could not parse args: {exc}") from exc
        return f"{base} {extra}".strip()

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        command = self.command(ctx, args)
        if not command:
            kind = args.get("kind", "test")
            raise ToolError(
                f"No {kind} command detected. Use run_command with the project's command, or declare it in RX.md "
                f"as '- {kind}: `<command>`'."
            )
        return await execute(ctx, command, None, None)
