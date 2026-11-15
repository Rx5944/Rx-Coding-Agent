from __future__ import annotations

import asyncio
import os
import shutil
import signal
import time
from pathlib import Path
from typing import Any

from ..config import Settings
from .base import ExecResult, OutputBuffer, OutputCallback, Sandbox, build_env, kill_group, pump

LIMIT_SCRIPT = (
    'ulimit -c 0 2>/dev/null; ulimit -f 4194304 2>/dev/null; '
    'ulimit -t "$RX_CPU_LIMIT" 2>/dev/null; __rx_cmd="$RX_COMMAND"; unset RX_COMMAND RX_CPU_LIMIT; eval "$__rx_cmd"'
)


class LocalSandbox(Sandbox):
    """Runs commands as the current user with a scrubbed env, CPU/file-size limits, a private process
    group and hard timeouts. This is NOT a security boundary: the permission engine + approvals are the
    defence here. Use BwrapSandbox or DockerSandbox for real isolation."""

    kind = "local"
    isolated = False

    def __init__(self, settings: Settings, workspace_root: Path) -> None:
        self.settings = settings
        self.root = workspace_root
        self.home = settings.data_dir / "home"
        self.home.mkdir(parents=True, exist_ok=True)

    # Subclasses override to wrap the command. Returns (argv, env, cleanup_handle).
    def _argv(self, command: str, cwd: Path, env: dict[str, str], timeout: int) -> tuple[list[str], dict[str, str], Any]:
        env = {**env, "RX_COMMAND": command, "RX_CPU_LIMIT": str(max(60, timeout * 2))}
        if os.name == "nt":
            return [os.environ.get("COMSPEC", "cmd.exe"), "/c", command], env, None
        shell = "/bin/bash" if Path("/bin/bash").exists() else (shutil.which("bash") or "/bin/sh")
        return [shell, "-c", LIMIT_SCRIPT], env, None

    async def _cleanup(self, handle: Any) -> None:
        return None

    async def run(self, command: str, *, cwd: Path, timeout: int, on_output: OutputCallback | None = None) -> ExecResult:
        env = build_env(self.settings, self.home)
        argv, env, handle = self._argv(command, cwd, env, timeout)
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=str(cwd), env=env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name != "nt"),
        )
        out, err = OutputBuffer(), OutputBuffer()
        readers = [
            asyncio.create_task(pump(proc.stdout, out, "stdout", on_output)),
            asyncio.create_task(pump(proc.stderr, err, "stderr", on_output)),
        ]
        timed_out = False
        try:
            try:
                await asyncio.wait_for(proc.wait(), timeout)
            except asyncio.TimeoutError:
                timed_out = True
                await kill_group(proc)
                await self._cleanup(handle)
            # Leftover background children would keep the pipes open; reap them.
            if os.name != "nt":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            try:
                await asyncio.wait_for(asyncio.gather(*readers), 3)
            except asyncio.TimeoutError:
                for task in readers:
                    task.cancel()
        except asyncio.CancelledError:
            await kill_group(proc)
            await self._cleanup(handle)
            for task in readers:
                task.cancel()
            raise
        return ExecResult(
            exit_code=None if timed_out else proc.returncode,
            stdout=out.text(), stderr=err.text(), timed_out=timed_out,
            duration=time.monotonic() - started, sandbox=self.kind,
        )
