from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..errors import SandboxUnavailable
from .base import Sandbox
from .bwrap import BwrapSandbox, bwrap_available
from .docker import DockerSandbox, docker_available
from .local import LocalSandbox


def create_sandbox(settings: Settings, root: Path) -> Sandbox:
    choice = settings.sandbox
    if choice not in {"auto", "bwrap", "docker", "local"}:
        raise SandboxUnavailable(f"Unknown sandbox {choice!r}. Use auto, bwrap, docker or local.")
    if choice in {"auto", "bwrap"}:
        if bwrap_available():
            return BwrapSandbox(settings, root)
        if choice == "bwrap":
            raise SandboxUnavailable("bubblewrap (bwrap) is not installed or user namespaces are disabled.")
    if choice in {"auto", "docker"}:
        if docker_available():
            return DockerSandbox(settings, root)
        if choice == "docker":
            raise SandboxUnavailable("Docker is not installed or the daemon is not reachable.")
    return LocalSandbox(settings, root)
