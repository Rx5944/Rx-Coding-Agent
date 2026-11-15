from __future__ import annotations

import asyncio
import difflib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ToolError
from ..util import atomic_write_bytes, unified_diff
from .base import Tool, ToolContext, ToolResult
from .fs import load_text, to_eol


def syntax_warning(rel: str, text: str) -> str:
    """Cheap post-edit sanity check; catches the most common agent mistake instantly."""
    try:
        if rel.endswith(".py"):
            compile(text, rel, "exec")
        elif rel.endswith(".json"):
            json.loads(text)
    except SyntaxError as exc:
        return f"\n⚠ {rel} now has a syntax error: {exc.msg} (line {exc.lineno}). Fix it before continuing."
    except ValueError as exc:
        return f"\n⚠ {rel} is no longer valid JSON: {exc}. Fix it before continuing."
    return ""


def _line_numbers(content: str, needle: str, limit: int = 5) -> list[int]:
    out, start = [], 0
    while len(out) < limit:
        i = content.find(needle, start)
        if i == -1:
            break
        out.append(content.count("\n", 0, i) + 1)
        start = i + max(1, len(needle))
    return out


def _closest_block(content: str, old: str) -> str | None:
    lines = content.split("\n")
    old_lines = old.split("\n")
    if len(lines) > 6000 or not old_lines:
        return None
    n = len(old_lines)
    best, best_i = 0.0, -1
    target = "\n".join(s.strip() for s in old_lines)
    for i in range(0, max(1, len(lines) - n + 1)):
        window = "\n".join(s.strip() for s in lines[i : i + n])
        ratio = difflib.SequenceMatcher(None, window, target).quick_ratio()
        if ratio > best:
            ratio = difflib.SequenceMatcher(None, window, target).ratio()
            if ratio > best:
                best, best_i = ratio, i
    if best_i < 0 or best < 0.6:
        return None
    chunk = "\n".join(f"{best_i + k + 1:>6}\t{line}" for k, line in enumerate(lines[best_i : best_i + n]))
    return f"Closest match (lines {best_i + 1}-{best_i + n}, {int(best * 100)}% similar):\n{chunk}"


def _match_ignoring_trailing_ws(content: str, old: str, new: str) -> str | None:
    if "\r" in content:
        return None
    lines = content.split("\n")
    old_lines = [s.rstrip() for s in old.split("\n")]
    n = len(old_lines)
    hits = [i for i in range(len(lines) - n + 1) if [s.rstrip() for s in lines[i : i + n]] == old_lines]
    if len(hits) != 1:
        return None
    i = hits[0]
    return "\n".join(lines[:i] + new.split("\n") + lines[i + n :])


def apply_edit(content: str, old: str, new: str, replace_all: bool = False) -> tuple[str, int]:
    if old == "":
        raise ToolError("old_text must not be empty. To create or fully replace a file, use write_file.")
    if old == new:
        raise ToolError("old_text and new_text are identical; nothing would change.")
    count = content.count(old)
    if count == 0:
        fallback = _match_ignoring_trailing_ws(content, old, new)
        if fallback is not None:
            return fallback, 1
        hint = _closest_block(content, old)
        raise ToolError(
            "old_text was not found in the file. It must match exactly, including whitespace and indentation."
            + (f"\n{hint}" if hint else "\nRe-read the file with read_file and copy the text exactly.")
        )
    if count > 1 and not replace_all:
        lines = _line_numbers(content, old)
        raise ToolError(
            f"old_text matches {count} places (lines {lines}). Include more surrounding lines to make it unique, "
            "or set replace_all=true to change every occurrence."
        )
    if replace_all:
        return content.replace(old, new), count
    return content.replace(old, new, 1), 1


@dataclass
class EditPlan:
    path: Path
    rel: str
    old: str
    new: str
    count: int


def _commit(ctx: ToolContext, plan: EditPlan) -> ToolResult:
    data = plan.new.encode("utf-8")
    atomic_write_bytes(plan.path, data)
    ctx.tracker.record(plan.rel, data)
    diff = unified_diff(plan.old, plan.new, plan.rel)
    noun = "replacement" if plan.count == 1 else "replacements"
    body = f"Edited {plan.rel} ({plan.count} {noun}).\n{diff[:4000]}" + syntax_warning(plan.rel, plan.new)
    return ToolResult.success(body, paths=[plan.rel], diff=diff[:20000])


class EditFile(Tool):
    name = "edit_file"
    category = "edit"
    description = (
        "Replace exact text in an existing file. old_text must match the file exactly (whitespace included) and be "
        "unique unless replace_all=true. Read the file first. Returns a diff."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the workspace."},
            "old_text": {"type": "string", "description": "Exact text to replace."},
            "new_text": {"type": "string", "description": "Replacement text."},
            "replace_all": {"type": "boolean", "description": "Replace every occurrence (default false)."},
        },
        "required": ["path", "old_text", "new_text"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"edit {args.get('path')}"

    def paths(self, args: dict[str, Any]) -> list[str]:
        return [args.get("path", "")]

    def plan(self, ctx: ToolContext, args: dict[str, Any]) -> EditPlan:
        path, text, _ = load_text(ctx, args["path"], must_be_fresh=True)
        rel = ctx.workspace.rel(path)
        eol = "\r\n" if "\r\n" in text else "\n"
        new_text, count = apply_edit(text, to_eol(args["old_text"], eol), to_eol(args["new_text"], eol),
                                     args.get("replace_all", False))
        return EditPlan(path, rel, text, new_text, count)

    async def preview(self, ctx: ToolContext, args: dict[str, Any]) -> str | None:
        try:
            plan = await asyncio.to_thread(self.plan, ctx, args)
        except ToolError as exc:
            return f"(preview unavailable: {exc})"
        return unified_diff(plan.old, plan.new, plan.rel)[:6000]

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        def work() -> ToolResult:
            return _commit(ctx, self.plan(ctx, args))

        return await asyncio.to_thread(work)


class MultiEdit(Tool):
    name = "multi_edit"
    category = "edit"
    description = (
        "Apply several edits to ONE file atomically, in order. If any edit fails, none are applied. "
        "Each edit has old_text, new_text and optional replace_all."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the workspace."},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                        "replace_all": {"type": "boolean"},
                    },
                    "required": ["old_text", "new_text"],
                },
            },
        },
        "required": ["path", "edits"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"edit {args.get('path')} ({len(args.get('edits', []))} changes)"

    def paths(self, args: dict[str, Any]) -> list[str]:
        return [args.get("path", "")]

    def plan(self, ctx: ToolContext, args: dict[str, Any]) -> EditPlan:
        if not args["edits"]:
            raise ToolError("edits must contain at least one edit.")
        path, text, _ = load_text(ctx, args["path"], must_be_fresh=True)
        rel = ctx.workspace.rel(path)
        eol = "\r\n" if "\r\n" in text else "\n"
        current, total = text, 0
        for number, edit in enumerate(args["edits"], start=1):
            try:
                current, count = apply_edit(current, to_eol(edit["old_text"], eol), to_eol(edit["new_text"], eol),
                                            edit.get("replace_all", False))
            except ToolError as exc:
                raise ToolError(f"Edit #{number} failed, so NO changes were applied: {exc}") from exc
            total += count
        return EditPlan(path, rel, text, current, total)

    async def preview(self, ctx: ToolContext, args: dict[str, Any]) -> str | None:
        try:
            plan = await asyncio.to_thread(self.plan, ctx, args)
        except ToolError as exc:
            return f"(preview unavailable: {exc})"
        return unified_diff(plan.old, plan.new, plan.rel)[:6000]

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(lambda: _commit(ctx, self.plan(ctx, args)))


_PATCH_PATH = re.compile(r"^(?:---|\+\+\+) (?P<p>[^\t\n]+)", re.M)


def patch_paths(patch: str) -> list[str]:
    found: list[str] = []
    for m in _PATCH_PATH.finditer(patch):
        raw = m.group("p").strip().strip('"')
        if raw == "/dev/null":
            continue
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        if raw and raw not in found:
            found.append(raw)
    return found


def clean_patch(patch: str) -> str:
    text = patch.strip("\n")
    text = re.sub(r"^```[a-zA-Z]*\n", "", text)
    text = re.sub(r"\n```$", "", text)
    return text + "\n"


_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


def normalize_patch(patch: str) -> str:
    """Recompute every hunk's line counts. LLMs routinely miscount; git (and --recount) then misparse
    multi-file patches, so we fix the headers ourselves."""
    lines = patch.rstrip("\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _HUNK.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        j, old, new, body = i + 1, 0, 0, []
        while j < len(lines):
            line = lines[j]
            if line.startswith(("@@ ", "diff --git ")) or (
                    line.startswith("--- ") and j + 1 < len(lines) and lines[j + 1].startswith("+++ ")):
                break
            if line.startswith("\\"):
                body.append(line)
            elif line.startswith("+"):
                new += 1
                body.append(line)
            elif line.startswith("-"):
                old += 1
                body.append(line)
            elif line.startswith(" ") or line == "":
                old += 1
                new += 1
                body.append(line or " ")
            else:
                break
            j += 1
        out.append(f"@@ -{m.group(1)},{old} +{m.group(2)},{new} @@{m.group(3)}")
        out.extend(body)
        i = j
    return "\n".join(out) + "\n"


class ApplyPatch(Tool):
    name = "apply_patch"
    category = "edit"
    description = (
        "Apply a unified diff (git format, paths like a/src/x.py and b/src/x.py) to one or more files; can create "
        "and delete files. Hunk counts are recomputed, so small miscounts are tolerated. Context lines must match."
    )
    parameters = {
        "type": "object",
        "properties": {"patch": {"type": "string", "description": "The unified diff text."}},
        "required": ["patch"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        files = patch_paths(args.get("patch", ""))
        return "patch " + (", ".join(files[:4]) + (" …" if len(files) > 4 else "") if files else "(no files)")

    def paths(self, args: dict[str, Any]) -> list[str]:
        return patch_paths(args.get("patch", ""))

    async def preview(self, ctx: ToolContext, args: dict[str, Any]) -> str | None:
        return clean_patch(args.get("patch", ""))[:6000]

    def _git(self, ctx: ToolContext, argv: list[str], patch: str) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": __import__("os").environ.get("PATH", ""),
            "GIT_CEILING_DIRECTORIES": str(ctx.workspace.root.parent),
            "LC_ALL": "C",
        }
        return subprocess.run(["git", "apply", "--whitespace=nowarn", *argv, "-"],
                              input=patch, text=True, capture_output=True, cwd=ctx.workspace.root,
                              env=env, timeout=30)

    def _apply(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        patch = normalize_patch(clean_patch(args["patch"]))
        files = patch_paths(patch)
        if not files:
            raise ToolError("No file paths found. Provide a unified diff with '--- a/path' and '+++ b/path' headers.")
        for raw in files:
            path = ctx.workspace.resolve(raw)
            if ctx.workspace.sensitivity(ctx.workspace.rel(path)) == "git":
                raise ToolError(f"Refusing to modify git internals: {raw}")
        try:
            check = self._git(ctx, ["--check"], patch)
        except FileNotFoundError as exc:
            raise ToolError("git is required for apply_patch but was not found.") from exc
        if check.returncode != 0:
            raise ToolError("Patch does not apply cleanly (nothing was changed):\n" + check.stderr.strip()[:2000] +
                            "\nRe-read the target files and regenerate the patch, or use edit_file.")
        stat = self._git(ctx, ["--numstat"], patch).stdout.strip()
        applied = self._git(ctx, [], patch)
        if applied.returncode != 0:
            raise ToolError("Patch failed while applying:\n" + applied.stderr.strip()[:2000])
        rels = []
        for raw in files:
            path = ctx.workspace.resolve(raw)
            rel = ctx.workspace.rel(path)
            rels.append(rel)
            if path.is_file():
                ctx.tracker.record(rel, path.read_bytes())
            else:
                ctx.tracker.forget(rel)
        warnings = ""
        for rel in rels:
            p = ctx.workspace.root / rel
            if p.is_file():
                try:
                    warnings += syntax_warning(rel, p.read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    pass
        return ToolResult.success(f"Patch applied to {len(rels)} file(s):\n{stat}{warnings}", paths=rels,
                                  diff=patch[:20000])

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(self._apply, ctx, args)
