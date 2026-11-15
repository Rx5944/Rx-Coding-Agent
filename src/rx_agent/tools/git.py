from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

from ..errors import ToolError
from .base import Tool, ToolContext, ToolResult


def run_git(ctx: ToolContext, argv: list[str], timeout: int = 20) -> str:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(ctx.settings.data_dir),
        "GIT_PAGER": "cat",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }
    try:
        proc = subprocess.run(["git", *argv], cwd=ctx.workspace.root, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ToolError("git is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError("git timed out.") from exc
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip()
        if "not a git repository" in msg:
            raise ToolError("This workspace is not a git repository.")
        raise ToolError(f"git {argv[0]} failed: {msg[:1000]}")
    return proc.stdout


class GitStatus(Tool):
    name = "git_status"
    category = "read"
    concurrency_safe = True
    description = "Show the working-tree status (short format) and current branch."
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        out = await asyncio.to_thread(run_git, ctx, ["status", "--short", "--branch"])
        return ToolResult.success(out.strip() or "clean")


class GitDiff(Tool):
    name = "git_diff"
    category = "read"
    concurrency_safe = True
    description = "Show uncommitted changes (unstaged by default; staged=true for the index)."
    parameters = {
        "type": "object",
        "properties": {
            "staged": {"type": "boolean"},
            "path": {"type": "string", "description": "Limit to one path."},
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        argv = ["diff", "--no-color"]
        if args.get("staged"):
            argv.append("--cached")
        if args.get("path"):
            argv += ["--", ctx.workspace.rel(ctx.workspace.resolve(args["path"]))]
        out = await asyncio.to_thread(run_git, ctx, argv)
        return ToolResult.success(out.strip() or "no changes")


class GitLog(Tool):
    name = "git_log"
    category = "read"
    concurrency_safe = True
    description = "Show recent commits (one line each)."
    parameters = {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 50}}}

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        out = await asyncio.to_thread(run_git, ctx, ["log", f"-{args.get('count', 10)}", "--oneline", "--decorate"])
        return ToolResult.success(out.strip() or "no commits")
