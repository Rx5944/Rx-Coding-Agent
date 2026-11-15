from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from .ignore import IgnoreMatcher


def iter_files(
    root: Path,
    matcher: IgnoreMatcher,
    *,
    start: Path | None = None,
    max_files: int = 50_000,
    include_ignored: bool = False,
) -> Iterator[Path]:
    """Walk with directory pruning *before* descent (the old code scanned all of .venv first)."""
    base = start or root
    count = 0
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        if not include_ignored:
            dirnames[:] = sorted(
                d for d in dirnames if not matcher.is_ignored(f"{rel_dir}/{d}".lstrip("/"), True)
            )
        else:
            dirnames.sort()
        for name in sorted(filenames):
            rel = f"{rel_dir}/{name}".lstrip("/")
            if not include_ignored and matcher.is_ignored(rel, False):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                try:
                    if not path.resolve().is_relative_to(root):
                        continue
                except OSError:
                    continue
            yield path
            count += 1
            if count >= max_files:
                return
