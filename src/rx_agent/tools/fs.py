from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ToolError
from ..util import atomic_write_bytes, human_size, unified_diff
from ..workspace.ignore import IgnoreMatcher
from .base import Tool, ToolContext, ToolResult

MAX_READ_BYTES = 5_000_000
MAX_LINE_CHARS = 2000
MAX_READ_CHARS = 60_000
MAX_WRITE_BYTES = 2_000_000


def load_text(ctx: ToolContext, rel_path: str, *, must_be_fresh: bool) -> tuple[Path, str, bytes]:
    """Read a file for editing: enforces existence, UTF-8, read-before-edit and freshness."""
    path = ctx.workspace.resolve(rel_path)
    rel = ctx.workspace.rel(path)
    if not path.exists():
        raise ToolError(f"File does not exist: {rel}")
    if not path.is_file():
        raise ToolError(f"Not a regular file: {rel}")
    data = path.read_bytes()
    if must_be_fresh:
        ctx.tracker.check_fresh(rel, data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"{rel} is not valid UTF-8, so it cannot be edited safely.") from exc
    return path, text, data


def to_eol(text: str, eol: str) -> str:
    if eol == "\r\n":
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text


class ReadFile(Tool):
    name = "read_file"
    category = "read"
    concurrency_safe = True
    description = (
        "Read a text file. Returns lines prefixed with their line numbers (line<TAB>text). "
        "For big files use offset/limit. You must read a file before editing it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the workspace."},
            "offset": {"type": "integer", "minimum": 1, "description": "1-based first line to return (default 1)."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "description": "Max lines (default 2000)."},
        },
        "required": ["path"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"read {args.get('path')}"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(self._read, ctx, args)

    def _read(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        path = ctx.workspace.resolve(args["path"])
        rel = ctx.workspace.rel(path)
        if not path.exists():
            raise ToolError(f"File does not exist: {rel}. Use glob or list_dir to find the right path.")
        if path.is_dir():
            raise ToolError(f"{rel} is a directory. Use list_dir.")
        size = path.stat().st_size
        if size > MAX_READ_BYTES:
            raise ToolError(f"{rel} is {human_size(size)}, too large to read. Use grep to locate what you need.")
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            raise ToolError(f"{rel} looks like a binary file ({human_size(size)}); not shown.")
        ctx.tracker.record(rel, data)
        text = data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if not lines:
            return ToolResult.success(f"({rel} is empty)", path=rel)
        offset = args.get("offset", 1)
        limit = args.get("limit", 2000)
        if offset > len(lines):
            raise ToolError(f"{rel} has only {len(lines)} lines; offset {offset} is past the end.")
        out: list[str] = []
        used = 0
        end = min(len(lines), offset - 1 + limit)
        stopped_at = end
        for i in range(offset - 1, end):
            line = lines[i].rstrip("\r")
            if len(line) > MAX_LINE_CHARS:
                line = line[:MAX_LINE_CHARS] + " …[line truncated]"
            row = f"{i + 1:>6}\t{line}"
            used += len(row) + 1
            if used > MAX_READ_CHARS:
                stopped_at = i
                break
            out.append(row)
        text_out = "\n".join(out)
        if stopped_at < len(lines):
            text_out += f"\n[... {len(lines) - stopped_at} more lines. Continue with offset={stopped_at + 1}]"
        return ToolResult.success(text_out, path=rel, lines=len(lines))


@dataclass
class WritePlan:
    path: Path
    rel: str
    old: str | None
    new: str


class WriteFile(Tool):
    name = "write_file"
    category = "edit"
    description = (
        "Create a new file or fully replace an existing one. Missing parent folders are created automatically (no mkdir "
        "needed). For existing files you must read_file first; prefer edit_file for targeted changes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the workspace."},
            "content": {"type": "string", "description": "The complete new file content."},
        },
        "required": ["path", "content"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"write {args.get('path')}"

    def paths(self, args: dict[str, Any]) -> list[str]:
        return [args.get("path", "")]

    def plan(self, ctx: ToolContext, args: dict[str, Any]) -> WritePlan:
        path = ctx.workspace.resolve(args["path"])
        rel = ctx.workspace.rel(path)
        content: str = args["content"]
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ToolError("Content is larger than 2MB; split it into several files.")
        if path.is_dir():
            raise ToolError(f"{rel} is a directory.")
        old = None
        if path.exists():
            _, old, _ = load_text(ctx, rel, must_be_fresh=True)
            if "\r\n" in old:
                content = to_eol(content, "\r\n")
        return WritePlan(path, rel, old, content)

    async def preview(self, ctx: ToolContext, args: dict[str, Any]) -> str | None:
        try:
            plan = await asyncio.to_thread(self.plan, ctx, args)
        except (ToolError, KeyError) as exc:
            return f"(preview unavailable: {exc})"
        if plan.old is None:
            lines = plan.new.count("\n") + 1
            return f"New file {plan.rel} ({lines} lines)\n" + "\n".join(plan.new.split("\n")[:60])
        return unified_diff(plan.old, plan.new, plan.rel)[:6000]

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        plan = await asyncio.to_thread(self.plan, ctx, args)
        data = plan.new.encode("utf-8")
        await asyncio.to_thread(atomic_write_bytes, plan.path, data)
        ctx.tracker.record(plan.rel, data)
        if plan.old is None:
            return ToolResult.success(f"Created {plan.rel} ({plan.new.count(chr(10)) + 1} lines).",
                                      paths=[plan.rel], created=True)
        diff = unified_diff(plan.old, plan.new, plan.rel)
        return ToolResult.success(f"Overwrote {plan.rel}.\n{diff[:4000]}", paths=[plan.rel], diff=diff[:20000])


class ListDir(Tool):
    name = "list_dir"
    category = "read"
    concurrency_safe = True
    description = "List a directory (directories end with '/'). Ignored folders like node_modules are hidden. depth up to 4."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory relative to the workspace (default '.')."},
            "depth": {"type": "integer", "minimum": 1, "maximum": 4, "description": "Levels to show (default 1)."},
        },
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"list {args.get('path', '.')}"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(self._list, ctx, args)

    def _list(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        base = ctx.workspace.resolve(args.get("path"))
        if not base.exists():
            raise ToolError(f"{ctx.workspace.rel(base)} does not exist yet. write_file creates missing parent folders "
                            "automatically, so just write your files there (no mkdir needed).")
        if not base.is_dir():
            raise ToolError(f"{ctx.workspace.rel(base)} is a file, not a directory. Use read_file.")
        matcher = IgnoreMatcher(ctx.workspace.root)
        depth = args.get("depth", 1)
        lines: list[str] = []
        limit = 300

        def walk(directory: Path, level: int) -> None:
            try:
                entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError:
                return
            for entry in entries:
                if len(lines) >= limit:
                    return
                rel = ctx.workspace.rel(entry)
                is_dir = entry.is_dir() and not entry.is_symlink()
                if matcher.is_ignored(rel, is_dir):
                    continue
                indent = "  " * level
                if is_dir:
                    lines.append(f"{indent}{entry.name}/")
                    if level + 1 < depth:
                        walk(entry, level + 1)
                else:
                    try:
                        size = human_size(entry.stat().st_size)
                    except OSError:
                        size = "?"
                    lines.append(f"{indent}{entry.name}  ({size})")

        walk(base, 0)
        if not lines:
            return ToolResult.success("(empty directory)")
        text = "\n".join(lines)
        if len(lines) >= limit:
            text += f"\n[... listing truncated at {limit} entries; list a subdirectory]"
        return ToolResult.success(text)
