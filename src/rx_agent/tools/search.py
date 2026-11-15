from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..errors import ToolError
from ..workspace.globbing import compile_glob
from ..workspace.ignore import IgnoreMatcher
from ..workspace.index import CodeIndex
from ..workspace.walk import iter_files
from .base import Tool, ToolContext, ToolResult

MAX_FILE_BYTES = 1_000_000


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(4096)
    except OSError:
        return True


class Glob(Tool):
    name = "glob"
    category = "read"
    concurrency_safe = True
    description = (
        "Find files by glob pattern, newest first. A pattern without '/' (e.g. '*.py') matches names at any depth; "
        "with '/' it matches the path (e.g. 'src/**/*.ts'). Respects .gitignore."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Directory to search in (default '.')."},
        },
        "required": ["pattern"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"glob {args.get('pattern')}"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(self._glob, ctx, args)

    def _glob(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        base = ctx.workspace.resolve(args.get("path"))
        match = compile_glob(args["pattern"])
        matcher = IgnoreMatcher(ctx.workspace.root)
        hits: list[tuple[float, str]] = []
        for path in iter_files(ctx.workspace.root, matcher, start=base):
            rel_to_base = path.relative_to(base).as_posix()
            if match(rel_to_base):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = 0.0
                hits.append((mtime, ctx.workspace.rel(path)))
        if not hits:
            return ToolResult.success("No files matched.")
        hits.sort(key=lambda h: (-h[0], h[1]))
        shown = [rel for _, rel in hits[:200]]
        text = "\n".join(shown)
        if len(hits) > 200:
            text += f"\n[... {len(hits) - 200} more matches; narrow the pattern or path]"
        return ToolResult.success(text, count=len(hits))


class Grep(Tool):
    name = "grep"
    category = "read"
    concurrency_safe = True
    description = (
        "Search file contents with a regular expression (ripgrep when installed). Respects .gitignore. "
        "output_mode: 'content' (file:line:text), 'files' (paths only) or 'count'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex to search for."},
            "path": {"type": "string", "description": "File or directory (default '.')."},
            "glob": {"type": "string", "description": "Only search files matching this glob, e.g. '*.py'."},
            "case_insensitive": {"type": "boolean"},
            "context": {"type": "integer", "minimum": 0, "maximum": 5, "description": "Lines of context around matches."},
            "output_mode": {"type": "string", "enum": ["content", "files", "count"]},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
        "required": ["pattern"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"grep {args.get('pattern')}"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(self._grep, ctx, args)

    def _grep(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        try:
            rx = re.compile(args["pattern"], re.I if args.get("case_insensitive") else 0)
        except re.error as exc:
            raise ToolError(f"Invalid regular expression: {exc}. Escape special characters with a backslash.") from exc
        base = ctx.workspace.resolve(args.get("path"))
        if not base.exists():
            raise ToolError(f"Path does not exist: {ctx.workspace.rel(base)}")
        mode = args.get("output_mode", "content")
        limit = args.get("max_results", 200)
        context = args.get("context", 0)
        if shutil.which("rg") and mode == "content" and not context:
            result = self._ripgrep(ctx, args, base, limit)
            if result is not None:
                return result
        return self._python_grep(ctx, args, rx, base, mode, limit, context)

    def _ripgrep(self, ctx: ToolContext, args: dict[str, Any], base: Path, limit: int) -> ToolResult | None:
        cmd = ["rg", "--no-heading", "--line-number", "--color", "never", "--max-columns", "300",
               "--hidden", "-g", "!.git", "-e", args["pattern"]]
        if args.get("case_insensitive"):
            cmd.append("-i")
        if args.get("glob"):
            cmd += ["-g", args["glob"]]
        cmd.append(str(base))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=ctx.workspace.root)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode not in (0, 1):
            return None
        lines = [ln.replace(str(ctx.workspace.root) + os.sep, "", 1) for ln in proc.stdout.splitlines()]
        if not lines:
            return ToolResult.success("No matches.")
        text = "\n".join(lines[:limit])
        if len(lines) > limit:
            text += f"\n[... {len(lines) - limit} more matches; narrow the search]"
        return ToolResult.success(text, count=len(lines))

    def _python_grep(self, ctx, args, rx: re.Pattern[str], base: Path, mode: str, limit: int, context: int) -> ToolResult:
        matcher = IgnoreMatcher(ctx.workspace.root)
        file_filter = compile_glob(args["glob"]) if args.get("glob") else None
        files = [base] if base.is_file() else iter_files(ctx.workspace.root, matcher, start=base)
        out: list[str] = []
        file_hits: list[str] = []
        counts: list[str] = []
        total = 0
        for path in files:
            if file_filter and not file_filter(path.relative_to(ctx.workspace.root).as_posix()):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES or _is_binary(path):
                    continue
                lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            except OSError:
                continue
            rel = ctx.workspace.rel(path)
            matched = [i for i, line in enumerate(lines) if rx.search(line)]
            if not matched:
                continue
            file_hits.append(rel)
            counts.append(f"{rel}:{len(matched)}")
            total += len(matched)
            if mode == "content":
                shown: set[int] = set()
                for i in matched:
                    for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                        if j in shown:
                            continue
                        shown.add(j)
                        sep = ":" if j in matched else "-"
                        out.append(f"{rel}{sep}{j + 1}{sep}{lines[j][:300]}")
                if len(out) >= limit:
                    break
        if not file_hits:
            return ToolResult.success("No matches.")
        if mode == "files":
            lines_out = file_hits
        elif mode == "count":
            lines_out = counts
        else:
            lines_out = out
        text = "\n".join(lines_out[:limit])
        if len(lines_out) > limit or (mode == "content" and len(out) >= limit):
            text += "\n[... results truncated; narrow the search with path or glob]"
        return ToolResult.success(text, count=total)


class RepoMap(Tool):
    name = "repo_map"
    category = "read"
    concurrency_safe = True
    description = (
        "Compact map of the repository: files with their classes and functions (budgeted, so it scales to large "
        "repos). Pass a subdirectory as `path` to zoom in."
    )
    parameters = {"type": "object", "properties": {"path": {"type": "string", "description": "Subdirectory (default '.')."}}}

    def summary(self, args: dict[str, Any]) -> str:
        return f"repo_map {args.get('path', '.')}"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        base = ctx.workspace.resolve(args.get("path"))
        rel = ctx.workspace.rel(base)
        text = await asyncio.to_thread(ctx.index.repo_map, "." if rel == "." else rel)
        return ToolResult.success(text)


class FindSymbol(Tool):
    name = "find_symbol"
    category = "read"
    concurrency_safe = True
    description = "Find where a function, class or method is defined (Python, JS/TS, Go, Rust, Java, Ruby, C-family)."
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Symbol name or part of it."}},
        "required": ["name"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"find_symbol {args.get('name')}"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        index: CodeIndex = ctx.index
        hits = await asyncio.to_thread(index.find, args["name"], {"class", "function", "method", "async_function", "type"})
        if not hits:
            return ToolResult.success("No matching symbols. Try grep for a text search.")
        rows = [f"{h.path}:{h.line}  {h.kind} {h.parent + '.' if h.parent else ''}{h.name}" for h in hits]
        return ToolResult.success("\n".join(rows))
