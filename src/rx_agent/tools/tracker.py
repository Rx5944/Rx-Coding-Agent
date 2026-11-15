from __future__ import annotations

from ..errors import ToolError
from ..util import sha1_bytes


class FileTracker:
    """Enforces 'read before you edit' and detects files that changed under the model's feet."""

    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}

    def record(self, rel: str, data: bytes) -> None:
        self._hashes[rel] = sha1_bytes(data)

    def forget(self, rel: str) -> None:
        self._hashes.pop(rel, None)

    def was_read(self, rel: str) -> bool:
        return rel in self._hashes

    def files_read(self) -> list[str]:
        return sorted(self._hashes)

    def check_fresh(self, rel: str, current: bytes) -> None:
        known = self._hashes.get(rel)
        if known is None:
            raise ToolError(
                f"You have not read {rel} in this session. Call read_file on it first so edits are based on its real contents."
            )
        if known != sha1_bytes(current):
            raise ToolError(
                f"{rel} changed on disk since you last read it (by the user, a command, or another tool). "
                "Re-read it with read_file and redo the edit."
            )
