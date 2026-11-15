from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..util import atomic_write_text

SESSION_VERSION = 1


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


@dataclass
class Session:
    workspace: str
    id: str = field(default_factory=new_session_id)
    messages: list[dict[str, Any]] = field(default_factory=list)
    todos: list[dict[str, str]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    title: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    version: int = SESSION_VERSION


class SessionStore:
    """One JSON file per session under <data_dir>/sessions, written atomically after every run."""

    def __init__(self, data_dir: Path):
        self.dir = data_dir / "sessions"

    def _path(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.dir / f"{safe}.json"

    def save(self, session: Session) -> None:
        session.updated = time.time()
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self._path(session.id), json.dumps(asdict(session), ensure_ascii=False))

    def load(self, session_id: str) -> Session | None:
        try:
            data = json.loads(self._path(session_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        known = {k: v for k, v in data.items() if k in Session.__dataclass_fields__}
        return Session(**known)

    def list(self, workspace: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if not self.dir.exists():
            return []
        rows = []
        for path in self.dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if workspace and data.get("workspace") != workspace:
                continue
            rows.append({"id": data.get("id"), "title": data.get("title", ""), "workspace": data.get("workspace"),
                         "updated": data.get("updated", 0), "messages": len(data.get("messages", []))})
        rows.sort(key=lambda r: r["updated"], reverse=True)
        return rows[:limit]

    def latest(self, workspace: str) -> Session | None:
        rows = self.list(workspace, limit=1)
        return self.load(rows[0]["id"]) if rows else None

    def delete(self, session_id: str) -> bool:
        try:
            os.unlink(self._path(session_id))
            return True
        except OSError:
            return False
