from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .local import LIMIT_SCRIPT, LocalSandbox

SYSTEM_RO = ["/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/etc", "/opt"]


def bwrap_available() -> bool:
    exe = shutil.which("bwrap")
    if not exe:
        return False
    try:
        probe = subprocess.run([exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "true"],
                               capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


class BwrapSandbox(LocalSandbox):
    """Linux namespaces via bubblewrap: read-only system, writable workspace only, no $HOME, no network
    unless enabled, private PID/IPC/UTS namespaces, dies with the agent."""

    kind = "bwrap"
    isolated = True

    def build_args(self, command: str, cwd: Path, env: dict[str, str], timeout: int) -> list[str]:
        args = ["bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--clearenv"]
        if not self.settings.sandbox_network:
            args.append("--unshare-net")
        for path in SYSTEM_RO:
            if os.path.exists(path):
                args += ["--ro-bind", path, path]
        extra = list(self.settings.ro_paths)
        venv = env.get("VIRTUAL_ENV")
        if venv:
            extra.append(venv)
        for path in extra:
            if os.path.exists(path):
                args += ["--ro-bind", path, path]
        home = str(self.home)
        args += ["--bind", home, home, "--bind", str(self.root), str(self.root), "--chdir", str(cwd)]
        env = {**env, "RX_COMMAND": command, "RX_CPU_LIMIT": str(max(60, timeout * 2)), "TMPDIR": "/tmp"}
        for key, value in env.items():
            args += ["--setenv", key, value]
        return [*args, "--", "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh", "-c", LIMIT_SCRIPT]

    def _argv(self, command: str, cwd: Path, env: dict[str, str], timeout: int) -> tuple[list[str], dict[str, str], Any]:
        return self.build_args(command, cwd, env, timeout), {"PATH": env.get("PATH", "")}, None
