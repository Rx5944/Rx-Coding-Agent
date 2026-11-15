from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .local import LIMIT_SCRIPT, LocalSandbox

HOST_ONLY_ENV = {"PATH", "VIRTUAL_ENV", "HOME", "TMPDIR", "SYSTEMROOT", "COMSPEC", "PATHEXT"}


def docker_available() -> bool:
    exe = shutil.which("docker")
    if not exe:
        return False
    try:
        return subprocess.run([exe, "info"], capture_output=True, timeout=8).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class DockerSandbox(LocalSandbox):
    """Each command runs in a throwaway container: no network by default, dropped capabilities,
    memory/CPU/PID limits, only the workspace mounted (at /workspace)."""

    kind = "docker"
    isolated = True

    def build_args(self, command: str, cwd: Path, env: dict[str, str], timeout: int, name: str) -> list[str]:
        try:
            rel = cwd.resolve().relative_to(self.root).as_posix()
        except ValueError:
            rel = "."
        workdir = "/workspace" if rel == "." else f"/workspace/{rel}"
        args = ["docker", "run", "--rm", "--name", name,
                "--network", "bridge" if self.settings.sandbox_network else "none",
                "--memory", "2g", "--cpus", "2", "--pids-limit", "512",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--tmpfs", "/tmp", "-v", f"{self.root}:/workspace:rw", "-w", workdir, "-e", "HOME=/tmp"]
        if hasattr(os, "getuid"):
            args += ["--user", f"{os.getuid()}:{os.getgid()}"]
        container_env = {k: v for k, v in env.items() if k not in HOST_ONLY_ENV}
        container_env.update(RX_COMMAND=command, RX_CPU_LIMIT=str(max(60, timeout * 2)))
        for key, value in container_env.items():
            args += ["-e", f"{key}={value}"]
        return [*args, self.settings.docker_image, "bash", "-c", LIMIT_SCRIPT]

    def _argv(self, command: str, cwd: Path, env: dict[str, str], timeout: int) -> tuple[list[str], dict[str, str], Any]:
        name = f"rx-{uuid.uuid4().hex[:12]}"
        return self.build_args(command, cwd, env, timeout, name), {"PATH": env.get("PATH", "")}, name

    async def _cleanup(self, handle: Any) -> None:
        if not handle:
            return
        proc = await asyncio.create_subprocess_exec(
            "docker", "kill", handle, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.wait(), 10)
        except asyncio.TimeoutError:
            pass
