"""Pure security helpers for the server. Each is unit-tested because each one is a boundary."""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

from ..errors import ToolError


def load_or_create_token(data_dir: Path, env_token: str | None = None) -> str:
    """A stable random token (0600) so the web UI / extension keep working across restarts."""
    if env_token:
        return env_token
    path = data_dir / "server_token"
    try:
        token = path.read_text().strip()
        if len(token) >= 32:
            return token
    except OSError:
        pass
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(token)
    return token


def token_ok(supplied: object, expected: str) -> bool:
    return isinstance(supplied, str) and hmac.compare_digest(supplied.encode(), expected.encode())


def allowed_hosts(port: int, extra: set[str] | None = None) -> set[str]:
    base = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}", "127.0.0.1", "localhost"}
    return base | (extra or set())


def host_allowed(host_header: str | None, port: int, extra: set[str] | None = None) -> bool:
    """Blocks DNS-rebinding: a hostile site resolving evil.com to 127.0.0.1 still sends Host: evil.com."""
    return bool(host_header) and host_header.lower() in allowed_hosts(port, extra)


def origin_allowed(origin: str | None, port: int, extra_hosts: set[str] | None = None,
                   extra_origins: set[str] | None = None) -> bool:
    """Blocks cross-site WebSocket hijacking. Non-browser clients send no Origin and rely on the token."""
    if origin is None:
        return True
    allowed = {f"http://{h}" for h in allowed_hosts(port, extra_hosts)} | {f"https://{h}" for h in (extra_hosts or set())}
    return origin.lower() in allowed | (extra_origins or set())


def resolve_workspace(raw: str | None, roots: list[Path]) -> Path:
    """Clients may only open directories inside the server's configured roots."""
    candidate = Path(raw).expanduser() if raw else roots[0]
    try:
        path = candidate.resolve()
    except OSError as exc:
        raise ToolError(f"Invalid workspace: {exc}") from exc
    if not path.is_dir():
        raise ToolError(f"Workspace is not a directory: {raw}")
    if not any(path == r or path.is_relative_to(r) for r in roots):
        raise ToolError("Workspace is outside the directories this server is allowed to use "
                        f"({', '.join(str(r) for r in roots)}).")
    return path
