from __future__ import annotations

from pathlib import Path

from ..errors import ToolError

SECRET_NAMES = {"id_rsa", "id_ed25519", "id_ecdsa", "credentials", ".npmrc", ".pypirc", ".netrc", ".git-credentials"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")
ENV_SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist")


class Workspace:
    """The only gateway from model-supplied strings to real filesystem paths."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"Workspace does not exist: {root}")
        if not self.root.is_dir():
            raise NotADirectoryError(f"Workspace is not a directory: {root}")

    def resolve(self, path: str | None, *, default: str = ".") -> Path:
        raw = (path or default).strip()
        if not raw:
            raise ToolError("Path cannot be empty.")
        candidate = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
        if candidate.is_absolute():
            # Be forgiving: models often echo the absolute workspace path back.
            target = candidate.resolve()
        else:
            target = (self.root / candidate).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise ToolError(f"Path is outside the workspace and cannot be accessed: {raw}")
        return target

    def rel(self, path: Path) -> str:
        try:
            value = path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()
        return value or "."

    @staticmethod
    def sensitivity(rel: str) -> str | None:
        """'git' (never writable) or 'secret' (always needs explicit approval) or None."""
        parts = Path(rel).parts
        if ".git" in parts:
            return "git"
        name = parts[-1].lower() if parts else ""
        if name == ".env" or (name.startswith(".env.") and not name.endswith(ENV_SAFE_SUFFIXES)):
            return "secret"
        if name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES):
            return "secret"
        return None
