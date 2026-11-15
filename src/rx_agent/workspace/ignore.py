from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .globbing import glob_to_regex

DEFAULT_IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".idea", ".next", ".rx", ".cache", ".gradle",
}


@dataclass
class _Rule:
    regex: re.Pattern[str]
    negate: bool
    dir_only: bool


class IgnoreMatcher:
    """gitignore-style matching for the root .gitignore and .rxignore (nested files not supported)."""

    def __init__(self, root: Path, extra: tuple[str, ...] = ()):
        self.root = root
        self.rules: list[_Rule] = []
        for name in (".gitignore", ".rxignore"):
            try:
                lines = (root / name).read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line in lines:
                self._add(line)
        for line in extra:
            self._add(line)

    def _add(self, line: str) -> None:
        line = line.rstrip("\n").rstrip()
        if not line or line.startswith("#"):
            return
        negate = line.startswith("!")
        if negate:
            line = line[1:]
        dir_only = line.endswith("/")
        line = line.rstrip("/")
        if not line:
            return
        anchored = "/" in line
        line = line.lstrip("/")
        body = glob_to_regex(line)
        regex = re.compile(("^" if anchored else r"(?:^|/)") + body + "$")
        self.rules.append(_Rule(regex, negate, dir_only))

    def is_ignored(self, rel: str, is_dir: bool) -> bool:
        name = rel.rsplit("/", 1)[-1]
        if is_dir and name in DEFAULT_IGNORED_DIRS:
            return True
        ignored = False
        for rule in self.rules:
            if rule.dir_only and not is_dir:
                continue
            if rule.regex.search(rel):
                ignored = not rule.negate
        return ignored

    def is_ignored_path(self, rel: str) -> bool:
        """True if the path or any ancestor directory is ignored."""
        parts = rel.split("/")
        for i in range(1, len(parts)):
            if self.is_ignored("/".join(parts[:i]), True):
                return True
        return self.is_ignored(rel, False)
