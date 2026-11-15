from __future__ import annotations

import asyncio
import os
import signal
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import Settings

OutputCallback = Callable[[str, str], None]  # (stream, text)

PASS_ENV = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "VIRTUAL_ENV", "SYSTEMROOT", "COMSPEC", "PATHEXT", "TMPDIR"}


@dataclass
class ExecResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration: float
    sandbox: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class OutputBuffer:
    """Keeps the head and the tail of a stream. Failures print at the end, so tails matter."""

    def __init__(self, head_cap: int = 200_000, tail_cap: int = 200_000) -> None:
        self.head: list[str] = []
        self.head_len = 0
        self.head_cap = head_cap
        self.tail: deque[str] = deque()
        self.tail_len = 0
        self.tail_cap = tail_cap
        self.dropped = 0

    def add(self, text: str) -> None:
        if self.head_len < self.head_cap:
            room = self.head_cap - self.head_len
            self.head.append(text[:room])
            self.head_len += len(text[:room])
            text = text[room:]
        if not text:
            return
        self.tail.append(text)
        self.tail_len += len(text)
        while self.tail_len > self.tail_cap and self.tail:
            first = self.tail[0]
            excess = self.tail_len - self.tail_cap
            if len(first) <= excess:
                self.tail.popleft()
                self.tail_len -= len(first)
                self.dropped += len(first)
            else:
                self.tail[0] = first[excess:]
                self.tail_len -= excess
                self.dropped += excess

    def text(self) -> str:
        head, tail = "".join(self.head), "".join(self.tail)
        if self.dropped:
            return f"{head}\n[... {self.dropped} characters omitted ...]\n{tail}"
        return head + tail


def build_env(settings: Settings, home: Path) -> dict[str, str]:
    """Allow-list environment. API keys and tokens in the parent env never reach commands."""
    env = {k: v for k, v in os.environ.items() if k in PASS_ENV or k in settings.env_passthrough}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.update(
        HOME=str(home), TERM="dumb", CI="1", NO_COLOR="1", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1",
        GIT_PAGER="cat", PAGER="cat", GIT_TERMINAL_PROMPT="0", DEBIAN_FRONTEND="noninteractive",
    )
    return env


async def pump(stream: asyncio.StreamReader | None, buf: OutputBuffer, name: str, cb: OutputCallback | None) -> None:
    if stream is None:
        return
    decoder = __import__("codecs").getincrementaldecoder("utf-8")(errors="replace")
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        text = decoder.decode(chunk)
        if text:
            buf.add(text)
            if cb:
                cb(name, text)


async def kill_group(proc: asyncio.subprocess.Process, grace: float = 2.0) -> None:
    """Terminate the whole process group (children included), escalating to SIGKILL."""
    if proc.returncode is not None and os.name == "nt":
        return
    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        await asyncio.wait_for(proc.wait(), grace)
    except asyncio.TimeoutError:
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            await asyncio.wait_for(proc.wait(), grace)
        except asyncio.TimeoutError:
            pass


class Sandbox(ABC):
    kind: str = "abstract"
    isolated: bool = False

    @abstractmethod
    async def run(
        self, command: str, *, cwd: Path, timeout: int, on_output: OutputCallback | None = None
    ) -> ExecResult:
        """Run a shell command. Must kill the entire process tree on timeout or cancellation."""
