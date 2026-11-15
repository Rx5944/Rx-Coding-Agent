from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .ignore import IgnoreMatcher
from .symbols import SUPPORTED_EXTENSIONS, Symbol, extract
from .walk import iter_files

MAX_PARSE_BYTES = 1_000_000


@dataclass
class FileEntry:
    path: str
    mtime_ns: int
    size: int
    imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    parsed: bool = False


@dataclass
class Hit:
    path: str
    kind: str
    name: str
    line: int | None
    parent: str | None = None


class CodeIndex:
    """Incremental symbol index. Each query stats files and re-parses only what changed,
    so results are never stale after the agent edits code (the v0 indexer cached forever)."""

    def __init__(self, root: Path, max_files: int = 20_000):
        self.root = root
        self.max_files = max_files
        self.entries: dict[str, FileEntry] = {}

    def refresh(self) -> int:
        matcher = IgnoreMatcher(self.root)
        seen: set[str] = set()
        reparsed = 0
        for path in iter_files(self.root, matcher, max_files=self.max_files):
            rel = path.relative_to(self.root).as_posix()
            seen.add(rel)
            try:
                st = path.stat()
            except OSError:
                continue
            old = self.entries.get(rel)
            if old and old.mtime_ns == st.st_mtime_ns and old.size == st.st_size:
                continue
            entry = FileEntry(rel, st.st_mtime_ns, st.st_size)
            ext = path.suffix.lower()
            if ext in SUPPORTED_EXTENSIONS and st.st_size <= MAX_PARSE_BYTES:
                try:
                    source = path.read_text(encoding="utf-8")
                    entry.imports, entry.symbols = extract(source, ext)
                    entry.parsed = True
                except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
                    pass
            self.entries[rel] = entry
            reparsed += 1
        for gone in set(self.entries) - seen:
            del self.entries[gone]
        return reparsed

    def find(self, query: str, kinds: set[str] | None = None, limit: int = 50) -> list[Hit]:
        self.refresh()
        q = query.lower().strip()
        scored: list[tuple[float, Hit]] = []
        for entry in self.entries.values():
            if q in entry.path.lower() and not kinds:
                scored.append((0.5 + (1 if os.path.basename(entry.path).lower() == q else 0), Hit(entry.path, "file", entry.path, None)))
            for sym in entry.symbols:
                if kinds and sym.kind not in kinds:
                    continue
                name = sym.name.lower()
                if name == q:
                    score = 3.0
                elif name.startswith(q):
                    score = 2.0
                elif q in name:
                    score = 1.0
                else:
                    continue
                scored.append((score, Hit(entry.path, sym.kind, sym.name, sym.line, sym.parent)))
        scored.sort(key=lambda item: (-item[0], item[1].path, item[1].line or 0))
        return [hit for _, hit in scored[:limit]]

    def repo_map(self, subdir: str = ".", max_chars: int = 6000) -> str:
        self.refresh()
        prefix = "" if subdir in (".", "") else subdir.strip("/") + "/"
        files = sorted((e for p, e in self.entries.items() if p.startswith(prefix)), key=lambda e: e.path)
        if not files:
            return "(no files)"
        lines: list[str] = []
        used = 0
        shown = 0
        for entry in files:
            block = [entry.path]
            classes: dict[str, list[str]] = {}
            top: list[str] = []
            for sym in entry.symbols:
                if sym.kind == "class" and sym.parent is None:
                    classes.setdefault(sym.name, [])
                elif sym.kind == "method" and sym.parent in classes:
                    classes[sym.parent].append(sym.name)
                elif sym.parent is None:
                    top.append(sym.name)
            for cls, methods in classes.items():
                shown_methods = ", ".join(methods[:12]) + (" …" if len(methods) > 12 else "")
                block.append(f"  class {cls}" + (f": {shown_methods}" if methods else ""))
            if top:
                block.append("  " + ", ".join(top[:20]) + (" …" if len(top) > 20 else ""))
            text = "\n".join(block)
            if used + len(text) + 1 > max_chars:
                break
            lines.append(text)
            used += len(text) + 1
            shown += 1
        out = "\n".join(lines)
        if shown < len(files):
            out += f"\n… {len(files) - shown} more files not shown. Call repo_map with a subdirectory `path` to drill in."
        return out
