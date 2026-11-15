from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass
class Symbol:
    name: str
    kind: str
    line: int
    end_line: int | None = None
    parent: str | None = None


def extract_python(source: str) -> tuple[list[str], list[Symbol]]:
    tree = ast.parse(source)
    imports: list[str] = []
    symbols: list[Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(f"{node.module}.{a.name}" if node.module else a.name for a in node.names)

    def visit(node: ast.AST, parent: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if parent else ("async_function" if isinstance(child, ast.AsyncFunctionDef) else "function")
                symbols.append(Symbol(child.name, kind, child.lineno, getattr(child, "end_lineno", None), parent))
                visit(child, child.name)
            elif isinstance(child, ast.ClassDef):
                symbols.append(Symbol(child.name, "class", child.lineno, getattr(child, "end_lineno", None), parent))
                visit(child, child.name)
            else:
                visit(child, parent)

    visit(tree, None)
    return imports, symbols


_JS = [
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+(\w+)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?(?:interface|type|enum)\s+(\w+)"), "type"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"), "function"),
]
_GO = [
    (re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)"), "function"),
    (re.compile(r"^type\s+(\w+)\s+(?:struct|interface)"), "class"),
]
_RUST = [
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)"), "function"),
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+(\w+)"), "class"),
]
_JVM = [
    (re.compile(r"^\s*(?:public|private|protected|internal|abstract|final|static|sealed|data|open|\s)*(?:class|interface|enum|object|record)\s+(\w+)"), "class"),
]
_RUBY = [
    (re.compile(r"^\s*def\s+(?:self\.)?(\w+[?!]?)"), "function"),
    (re.compile(r"^\s*(?:class|module)\s+(\w+)"), "class"),
]
_C = [
    (re.compile(r"^\s*(?:class|struct|enum)\s+(\w+)"), "class"),
]

REGEX_LANGS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    **dict.fromkeys((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"), _JS),
    ".go": _GO, ".rs": _RUST,
    **dict.fromkeys((".java", ".kt", ".cs", ".scala"), _JVM),
    ".rb": _RUBY,
    **dict.fromkeys((".c", ".h", ".cpp", ".hpp", ".cc"), _C),
}
SUPPORTED_EXTENSIONS = {".py", *REGEX_LANGS}


def extract_regex(source: str, ext: str) -> list[Symbol]:
    patterns = REGEX_LANGS.get(ext, [])
    out: list[Symbol] = []
    for number, line in enumerate(source.split("\n"), start=1):
        if len(line) > 300:
            continue
        for rx, kind in patterns:
            m = rx.match(line)
            if m:
                out.append(Symbol(m.group(1), kind, number))
                break
    return out


def extract(source: str, ext: str) -> tuple[list[str], list[Symbol]]:
    if ext == ".py":
        return extract_python(source)
    return [], extract_regex(source, ext)
