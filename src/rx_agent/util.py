from __future__ import annotations

import difflib
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def truncate_middle(text: str, max_chars: int, marker: str = "\n[... {n} characters omitted ...]\n") -> str:
    """Keep the head and tail of long text (tails matter: failures print at the end)."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    note = marker.format(n=omitted)
    keep = max(0, max_chars - len(note))
    head = keep * 2 // 3
    tail = keep - head
    return text[:head] + note + (text[-tail:] if tail else "")


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~3.5 chars/token for code-heavy text)."""
    return max(1, int(len(text) / 3.5))


def estimate_message_tokens(message: dict[str, Any]) -> int:
    total = 4
    content = message.get("content")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif content:
        total += estimate_tokens(json.dumps(content, ensure_ascii=False))
    for call in message.get("tool_calls") or []:
        total += estimate_tokens(json.dumps(call, ensure_ascii=False))
    return total


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via temp file + rename so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = None
    if path.exists():
        mode = path.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix=".rx-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def unified_diff(old: str, new: str, label: str, context: int = 3) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
        n=context,
    )
    out = "".join(line if line.endswith("\n") else line + "\n" for line in diff)
    return out


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{n}B"


def now() -> float:
    return time.time()


def short_json(value: Any, limit: int = 200) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"
