"""Detect how a project is tested/linted, and recognise verification commands."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

VERIFY_PATTERNS = [re.compile(p) for p in (
    r"\bpytest\b", r"\bpython3?\s+-m\s+(pytest|unittest|mypy|ruff|flake8|pylint|compileall|py_compile)\b",
    r"\b(ruff|mypy|flake8|pylint|tox|nox|pyright)\b", r"\b(npm|yarn|pnpm)\s+(run\s+)?(test|lint|build|typecheck|check)\b",
    r"\b(jest|vitest|mocha|eslint|tsc|playwright)\b", r"\bgo\s+(test|vet|build)\b",
    r"\bcargo\s+(test|check|clippy|build)\b", r"\bmake\s+(test|check|lint)\b",
    r"\b(mvn|gradle|gradlew)\b.*\b(test|check|verify)\b", r"\bdotnet\s+(test|build)\b", r"\bphpunit\b",
    r"\brspec\b", r"\bpython3?\s+-c\b", r"\bnode\s+-e\b", r"\bpython3?\s+[\w./-]+\.py\b", r"\bnode\s+[\w./-]+\.(js|mjs|cjs)\b",
)]
INSTRUCTION_FILES = ("RX.md", "AGENTS.md", "CLAUDE.md")
DECLARED = re.compile(r"^\s*[-*]?\s*(test|lint|typecheck|build)(?:\s+command)?\s*[:=]\s*`?([^`\n]+?)`?\s*$", re.I | re.M)


INSTALLERS = re.compile(r"^\s*(sudo\s+)?(pip3?|npm|yarn|pnpm|apt(-get)?|brew|poetry|uv|cargo|gem)\s+(install|add|i|remove|uninstall)\b")


def is_verification_command(command: str) -> bool:
    """True for commands that check the code (tests, linters, type checkers, running a script)."""
    if INSTALLERS.match(command):
        return False
    return any(p.search(command) for p in VERIFY_PATTERNS)


def read_project_instructions(root: Path, limit: int = 8000) -> tuple[str | None, str]:
    for name in INSTRUCTION_FILES:
        path = root / name
        if path.is_file():
            try:
                return name, path.read_text(encoding="utf-8", errors="replace")[:limit]
            except OSError:
                continue
    return None, ""


class Verifier:
    def __init__(self, root: Path):
        self.root = root

    def _read(self, name: str) -> str:
        try:
            return (self.root / name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def detect(self) -> dict[str, str]:
        found: dict[str, str] = {}
        py = "python3" if shutil.which("python3") else "python"
        pyproject, req = self._read("pyproject.toml"), self._read("requirements.txt") + self._read("requirements-dev.txt")
        has_py_tests = any((self.root / d).is_dir() for d in ("tests", "test")) or any(self.root.glob("test_*.py"))
        if has_py_tests or (self.root / "pytest.ini").exists() or "[tool.pytest" in pyproject:
            uses_pytest = ((self.root / "pytest.ini").exists() or (self.root / "conftest.py").exists()
                           or "pytest" in pyproject + req + self._read("tox.ini") + self._read("setup.cfg")
                           or (self.root / "tests" / "conftest.py").exists())
            found["test"] = f"{py} -m pytest -q" if uses_pytest else f"{py} -m unittest discover -q"
        if "[tool.ruff" in pyproject or (self.root / "ruff.toml").exists():
            found["lint"] = "ruff check ."
        if "[tool.mypy" in pyproject or (self.root / "mypy.ini").exists():
            found["typecheck"] = "mypy ."
        pkg = self._read("package.json")
        if pkg:
            try:
                scripts = json.loads(pkg).get("scripts", {})
            except json.JSONDecodeError:
                scripts = {}
            runner = "pnpm" if (self.root / "pnpm-lock.yaml").exists() else "yarn" if (self.root / "yarn.lock").exists() else "npm"
            for key in ("test", "lint", "typecheck", "build"):
                if key in scripts and key not in found:
                    found[key] = f"{runner} test" if key == "test" else f"{runner} run {key}"
        if (self.root / "go.mod").exists():
            found.setdefault("test", "go test ./...")
            found.setdefault("lint", "go vet ./...")
        if (self.root / "Cargo.toml").exists():
            found.setdefault("test", "cargo test")
            found.setdefault("lint", "cargo clippy")
        if "test" not in found and re.search(r"^test:", self._read("Makefile"), re.M):
            found["test"] = "make test"
        _, instructions = read_project_instructions(self.root)
        for m in DECLARED.finditer(instructions):  # explicit declarations in RX.md win
            found[m.group(1).lower()] = m.group(2).strip()
        return found
