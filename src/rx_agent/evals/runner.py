from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..config import Settings
from ..core.loop import Agent
from ..events import EventBus
from ..llm.base import LLMClient
from ..llm.mock import ScriptedLLM, tool_call
from ..permissions.approvals import StaticApprover
from ..sandbox.select import create_sandbox
from ..workspace.paths import Workspace
from .tasks import TASKS, EvalTask


def _fmt(cmd: str) -> str:
    return cmd.replace("{py}", sys.executable)


def materialize(task: EvalTask, root: Path) -> None:
    for rel, text in task.files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def run_checks(task: EvalTask, root: Path) -> list[dict[str, Any]]:
    for rel, text in task.hidden_files.items():
        (root / rel).write_text(text)
    results = []
    for check in task.checks:
        kind, ok, detail = check["type"], False, ""
        try:
            if kind in ("command", "stdout"):
                proc = subprocess.run(_fmt(check["cmd"]), shell=True, cwd=root, capture_output=True, text=True, timeout=60)
                if kind == "command":
                    ok = proc.returncode == check.get("expect_exit", 0)
                else:
                    ok = proc.returncode == 0 and proc.stdout.strip() == check["equals"]
                detail = (proc.stdout + proc.stderr).strip()[-300:]
            elif kind == "not_contains":
                ok = check["text"] not in (root / check["path"]).read_text()
            elif kind == "contains":
                ok = check["text"] in (root / check["path"]).read_text()
            elif kind == "exists":
                ok = (root / check["path"]).exists()
            elif kind == "unchanged":
                ok = (root / check["path"]).read_text() == task.files[check["path"]]
        except (OSError, subprocess.TimeoutExpired) as exc:
            detail = str(exc)
        results.append({"check": kind, "ok": ok, "detail": detail if not ok else ""})
    for rel in task.hidden_files:
        (root / rel).unlink(missing_ok=True)
    return results


def oracle_llm(task: EvalTask) -> ScriptedLLM:
    """A scripted 'perfect' agent: read, write the reference solution, verify, report."""
    steps: list[Any] = []
    for n, (rel, text) in enumerate(task.solution.items()):
        if rel in task.files:
            steps.append(tool_call("read_file", f"r{n}", path=rel))
        steps.append(tool_call("write_file", f"w{n}", path=rel, content=text))
    if task.verify:
        steps.append(tool_call("run_command", "v", command=_fmt(task.verify)))
    steps.append("Applied the reference solution and verified it.")
    return ScriptedLLM(steps)


def validate_tasks(tasks: list[EvalTask] = TASKS) -> list[str]:
    """Every task must FAIL on the starting files and PASS with the reference solution."""
    problems = []
    for task in tasks:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materialize(task, root)
            if all(r["ok"] for r in run_checks(task, root)):
                problems.append(f"{task.id}: checks already pass before any change (task is trivial)")
            for rel, text in task.solution.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            failed = [r for r in run_checks(task, root) if not r["ok"]]
            if failed:
                problems.append(f"{task.id}: reference solution fails checks: {failed}")
    return problems


async def run_task(task: EvalTask, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"rx-eval-{task.id}-") as tmp:
        root = Path(tmp).resolve()
        materialize(task, root)
        s = replace(settings, mode="auto", snapshots=False, data_dir=root.parent / f"{root.name}-data")
        bus, tool_calls = EventBus(), []
        bus.subscribe(lambda e: tool_calls.append(e["tool"]) if e["type"] == "tool_started" else None)
        agent = Agent(llm=llm, settings=s, workspace=Workspace(root), events=bus,
                      approver=StaticApprover(True), sandbox=create_sandbox(s, root))
        started = time.time()
        try:
            result = await asyncio.wait_for(agent.run(agent.new_session(), task.prompt, "auto"), 600)
            status, error = result.status, result.error
            usage, iterations = result.usage, result.iterations
        except Exception as exc:  # noqa: BLE001
            status, error, usage, iterations = "crashed", f"{type(exc).__name__}: {exc}", {"total_tokens": 0}, 0
        checks = run_checks(task, root)
        shutil.rmtree(root.parent / f"{root.name}-data", ignore_errors=True)
        return {"id": task.id, "passed": all(c["ok"] for c in checks), "status": status, "error": error,
                "iterations": iterations, "tokens": usage.get("total_tokens", 0), "tool_calls": len(tool_calls),
                "seconds": round(time.time() - started, 1), "checks": checks}


async def run_suite(tasks: list[EvalTask], settings: Settings, oracle: bool = False,
                    llm_factory=None) -> dict[str, Any]:
    from ..llm.registry import create_llm

    rows = []
    for task in tasks:
        llm = oracle_llm(task) if oracle else (llm_factory or create_llm)(settings)
        rows.append(await run_task(task, llm, settings))
    passed = sum(r["passed"] for r in rows)
    return {"model": "oracle" if oracle else settings.model, "total": len(rows), "passed": passed,
            "pass_rate": round(passed / len(rows), 3) if rows else 0.0,
            "tokens": sum(r["tokens"] for r in rows), "seconds": round(sum(r["seconds"] for r in rows), 1), "tasks": rows}


def format_report(report: dict[str, Any]) -> str:
    lines = [f"model: {report['model']}", f"{'task':<30} {'result':<7} {'steps':>5} {'tools':>5} {'tokens':>8} {'sec':>6}"]
    for r in report["tasks"]:
        lines.append(f"{r['id']:<30} {'PASS' if r['passed'] else 'FAIL':<7} {r['iterations']:>5} {r['tool_calls']:>5} {r['tokens']:>8} {r['seconds']:>6}")
        if not r["passed"]:
            for c in r["checks"]:
                if not c["ok"]:
                    lines.append(f"    ✗ {c['check']}: {c['detail'][:160]}")
            if r["error"]:
                lines.append(f"    error: {r['error'][:160]}")
    lines.append(f"\n{report['passed']}/{report['total']} passed ({report['pass_rate']:.0%}), "
                 f"{report['tokens']} tokens, {report['seconds']}s")
    return "\n".join(lines)
