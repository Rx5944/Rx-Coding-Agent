from __future__ import annotations

import re
from typing import Callable

_NO = ("!", "^")


def glob_to_regex(pat: str) -> str:
    """Translate a glob (with **, ?, [..], {a,b}) into a regex body (no anchors)."""
    i, out = 0, []
    while i < len(pat):
        c = pat[i]
        if c == "*":
            if pat.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
            elif pat.startswith("**", i):
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            start = i + 2 if pat[i + 1 : i + 2] in _NO else i + 1
            j = pat.find("]", start + 1)
            if j == -1:
                out.append(re.escape(c))
                i += 1
            else:
                body = pat[i + 1 : j]
                if body[:1] in _NO:
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = j + 1
        elif c == "{":
            j = pat.find("}", i)
            if j == -1:
                out.append(re.escape(c))
                i += 1
            else:
                alts = pat[i + 1 : j].split(",")
                out.append("(?:" + "|".join(glob_to_regex(a) for a in alts) + ")")
                i = j + 1
        elif c == "\\" and i + 1 < len(pat):
            out.append(re.escape(pat[i + 1]))
            i += 2
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def compile_glob(pattern: str) -> Callable[[str], bool]:
    """Patterns without '/' match a basename at any depth; others match the relative path."""
    pat = pattern.strip()
    if pat.startswith("./"):
        pat = pat[2:]
    if "/" not in pat.strip("/"):
        rx = re.compile(r"(?:^|/)" + glob_to_regex(pat.strip("/")) + r"$")
    else:
        rx = re.compile(r"^" + glob_to_regex(pat.strip("/")) + r"$")
    return lambda rel: rx.search(rel) is not None
