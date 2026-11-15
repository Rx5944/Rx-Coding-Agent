"""Restore points in a *shadow* git repo. The user's own repository is never touched."""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

from .errors import RXError


class SnapshotError(RXError):
    pass


EXCLUDES = ["node_modules/", ".venv/", "venv/", "__pycache__/", "*.pyc", ".mypy_cache/", ".pytest_cache/",
            ".ruff_cache/", ".next/", "target/", "dist/", "build/", ".rx/"]


class Snapshots:
    def __init__(self, root: Path, data_dir: Path):
        self.root = root.resolve()
        key = hashlib.sha1(str(self.root).encode()).hexdigest()[:16]
        self.git_dir = data_dir / "snapshots" / key

    # -------------------------------------------------------------- plumbing
    def _git(self, *args: str, check: bool = True, timeout: int = 120, text: bool = True) -> subprocess.CompletedProcess:
        env = {
            "PATH": os.environ.get("PATH", ""), "GIT_DIR": str(self.git_dir), "GIT_WORK_TREE": str(self.root),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C",
        }
        cmd = ["git", "-c", "user.name=rx", "-c", "user.email=rx@localhost", "-c", "core.quotepath=off",
               "-c", "gc.auto=0", *args]
        try:
            proc = subprocess.run(cmd, env=env, cwd=self.root, capture_output=True, text=text, timeout=timeout)
        except FileNotFoundError as exc:
            raise SnapshotError("git is required for snapshots") from exc
        except subprocess.TimeoutExpired as exc:
            raise SnapshotError(f"git {args[0]} timed out") from exc
        if check and proc.returncode != 0:
            err = proc.stderr if text else proc.stderr.decode("utf-8", "replace")
            raise SnapshotError(f"git {args[0]} failed: {err.strip()[:500]}")
        return proc

    def ensure(self) -> None:
        if (self.git_dir / "HEAD").exists():
            return
        self.git_dir.parent.mkdir(parents=True, exist_ok=True)
        self._git("init", "-q")
        info = self.git_dir / "info"
        info.mkdir(exist_ok=True)
        (info / "exclude").write_text("\n".join(EXCLUDES) + "\n")

    # ------------------------------------------------------------------- api
    def create(self, label: str) -> str:
        self.ensure()
        self._git("add", "-A")
        message = f"{label[:200]}\n\nts={int(time.time())}"
        self._git("commit", "-q", "--allow-empty", "-m", message)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def list(self, limit: int = 20) -> list[dict]:
        if not (self.git_dir / "HEAD").exists():
            return []
        proc = self._git("log", f"-{limit}", "--format=%H%x1f%s%x1f%ct", check=False)
        if proc.returncode != 0:
            return []
        out = []
        for line in proc.stdout.splitlines():
            sha, _, rest = line.partition("\x1f")
            subject, _, ts = rest.partition("\x1f")
            out.append({"id": sha, "label": subject, "ts": int(ts or 0)})
        return out

    def changed_since(self, snapshot_id: str) -> list[str]:
        self.ensure()
        self._git("add", "-A")
        raw = self._git("diff", "--cached", "--name-status", "--no-renames", "-z", snapshot_id).stdout
        parts = raw.split("\0")
        return [parts[i + 1] for i in range(0, len(parts) - 1, 2)]

    def restore(self, snapshot_id: str) -> dict[str, list[str]]:
        """Return the workspace to the snapshot: revert changed files, restore deleted ones, delete new ones."""
        self.ensure()
        self._git("rev-parse", "--verify", snapshot_id + "^{commit}")
        self._git("add", "-A")
        raw = self._git("diff", "--cached", "--name-status", "--no-renames", "-z", snapshot_id).stdout
        parts = raw.split("\0")
        restored, deleted = [], []
        for i in range(0, len(parts) - 1, 2):
            status, rel = parts[i], parts[i + 1]
            target = (self.root / rel).resolve()
            if not target.is_relative_to(self.root):
                continue
            if status == "A":
                try:
                    target.unlink()
                    deleted.append(rel)
                except FileNotFoundError:
                    pass
            else:
                self._git("checkout", snapshot_id, "--", rel)
                restored.append(rel)
        return {"restored": restored, "deleted": deleted}
