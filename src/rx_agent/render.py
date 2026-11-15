"""Console renderer + interactive approver for the CLI."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from .permissions.approvals import ApprovalRequest, ApprovalResponse


class Style:
    def __init__(self, enabled: bool):
        self.on = enabled

    def _w(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def dim(self, s): return self._w("2", s)
    def bold(self, s): return self._w("1", s)
    def red(self, s): return self._w("31", s)
    def green(self, s): return self._w("32", s)
    def yellow(self, s): return self._w("33", s)
    def cyan(self, s): return self._w("36", s)


def make_style(stream=None) -> Style:
    stream = stream or sys.stdout
    return Style(bool(getattr(stream, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ)


def colorize_diff(text: str, style: Style, max_lines: int = 40) -> str:
    out = []
    lines = text.rstrip("\n").split("\n")
    for line in lines[:max_lines]:
        if line.startswith(("+++", "---")):
            out.append(style.bold(line))
        elif line.startswith("+"):
            out.append(style.green(line))
        elif line.startswith("-"):
            out.append(style.red(line))
        elif line.startswith("@@"):
            out.append(style.cyan(line))
        else:
            out.append(style.dim(line))
    if len(lines) > max_lines:
        out.append(style.dim(f"… {len(lines) - max_lines} more diff lines"))
    return "\n".join(out)


class ConsoleRenderer:
    def __init__(self, out=None, verbose: bool = False):
        self.out = out or sys.stdout
        self.s = make_style(self.out)
        self.verbose = verbose
        self.mid_line = False
        self.output_lines: dict[str, int] = {}

    def _p(self, text: str = "", end: str = "\n") -> None:
        self.out.write(text + end)
        self.out.flush()

    def _break(self) -> None:
        if self.mid_line:
            self._p()
            self.mid_line = False

    def __call__(self, e: dict[str, Any]) -> None:
        t = e["type"]
        if t == "assistant_delta":
            self._p(e["text"], end="")
            self.mid_line = not e["text"].endswith("\n")
        elif t == "tool_started":
            self._break()
            self._p(self.s.cyan("● ") + e["summary"])
        elif t == "command_output":
            n = self.output_lines.get(e["id"], 0)
            for line in e["text"].splitlines():
                n += 1
                if n <= 25:
                    self._p(self.s.dim("  │ " + line[:200]))
                elif n == 26:
                    self._p(self.s.dim("  │ … (output continues; the model sees all of it)"))
            self.output_lines[e["id"]] = n
        elif t == "tool_finished":
            if not e["ok"]:
                first = (e["content"].strip().splitlines() or [""])[0][:200]
                self._p(self.s.red("  ✗ ") + first)
            elif e["meta"].get("diff"):
                self._p(colorize_diff(e["meta"]["diff"], self.s))
            elif self.verbose:
                self._p(self.s.dim("  ✓ " + (e["content"].splitlines() or [""])[0][:160]))
        elif t == "tool_denied":
            self._p(self.s.yellow("  ⊘ blocked: ") + str(e.get("reason", ""))[:200])
        elif t == "verification":
            mark = self.s.green("✓ verification passed") if e["ok"] else self.s.red("✗ verification failed")
            self._p(f"  {mark}  {self.s.dim(str(e['command'])[:100])}")
        elif t == "todos_updated":
            for todo in e["todos"]:
                box = {"completed": "☑", "in_progress": "◐"}.get(todo["status"], "☐")
                self._p(self.s.dim(f"  {box} {todo['content']}"))
        elif t == "context_compacted":
            self._break()
            self._p(self.s.dim(f"  ↻ context compacted ({e['method']}): {e['before_tokens']} → {e['after_tokens']} tokens"))
        elif t == "llm_retry":
            self._break()
            self._p(self.s.yellow(f"  ⟳ model request failed ({e['error'][:80]}); retry {e['attempt']} in {e['delay']:.1f}s"))
        elif t == "warning":
            self._break()
            self._p(self.s.yellow("  ! " + e["message"]))
        elif t == "snapshot_created" and self.verbose:
            self._p(self.s.dim(f"  ⎙ restore point {e['snapshot_id'][:8]}"))
        elif t in ("task_completed", "task_cancelled", "task_failed"):
            self._break()
            self.summary(e["result"], e.get("error"))

    def summary(self, r: dict[str, Any], error: str | None = None) -> None:
        status = r["status"]
        color = self.s.green if status == "completed" else self.s.yellow if status in ("cancelled", "iteration_limit") else self.s.red
        parts = [color(status), f"{r['iterations']} steps", f"{r['usage']['total_tokens']} tokens", f"{r['duration']}s"]
        self._p("\n" + self.s.dim(" · ".join(p for p in parts)))
        if r["files_modified"]:
            self._p(self.s.dim("changed: ") + ", ".join(r["files_modified"]))
            v = r["verification"]
            if v["ran"]:
                self._p(self.s.dim("verified: ") + (self.s.green("passed") if v["passed"] else self.s.red("FAILED")))
            else:
                self._p(self.s.dim("verified: ") + self.s.yellow("not run"))
            if r.get("snapshot_id"):
                self._p(self.s.dim("undo with: rx undo"))
        if error:
            self._p(self.s.red("error: ") + error)


class CliApprover:
    """Interactive y/n/a prompt. Non-interactive stdin denies everything that needs approval."""

    def __init__(self, out=None):
        self.out = out or sys.stdout
        self.s = make_style(self.out)

    async def request(self, req: ApprovalRequest) -> ApprovalResponse:
        if not sys.stdin.isatty():
            return ApprovalResponse(False, message="Non-interactive session: approval is not available.")
        risk = {"sensitive": self.s.red, "dangerous": self.s.red}.get(req.risk, self.s.yellow)
        print("\n" + risk("┌ approval needed") + f"  {self.s.bold(req.summary)}", file=self.out)
        if req.reason:
            print(self.s.dim("│ " + req.reason), file=self.out)
        if req.preview:
            for line in colorize_diff(req.preview, self.s, 30).split("\n"):
                print("│ " + line, file=self.out)
        options = "[y]es  [n]o" + ("  [a]lways for this kind" if req.can_remember else "") + "  or type a note to deny"
        try:
            answer = (await asyncio.to_thread(input, f"└ {options}: ")).strip()
        except (EOFError, KeyboardInterrupt):
            return ApprovalResponse(False, message="No answer.")
        low = answer.lower()
        if low in ("y", "yes", ""):
            return ApprovalResponse(True)
        if low in ("a", "always") and req.can_remember:
            return ApprovalResponse(True, remember=True)
        if low in ("n", "no"):
            return ApprovalResponse(False)
        return ApprovalResponse(False, message=answer)
