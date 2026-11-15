"""Static analysis of shell commands. Replaces the old binary allowlist, which let
`python -c`, `find -delete`, `cat ../x` and `git -C . reset --hard` straight through."""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class Risk(IntEnum):
    SAFE = 0        # read-only, inside the workspace
    NORMAL = 1      # changes things / runs code; fine with approval
    SENSITIVE = 2   # external or hard-to-undo effects; ALWAYS asks, never auto-approved
    DANGEROUS = 3   # always denied


@dataclass
class CommandAnalysis:
    risk: Risk = Risk.SAFE
    reasons: list[str] = field(default_factory=list)
    programs: list[str] = field(default_factory=list)
    compound: bool = False
    opaque: bool = False
    writes: bool = False
    key: str | None = None  # stable key for "always allow this kind of command"

    def raise_to(self, risk: Risk, reason: str) -> None:
        """Record a finding. reasons[0] is always the reason for the highest risk seen, so it explains the verdict."""
        escalated = risk > self.risk
        if escalated:
            self.risk = risk
        if reason and reason not in self.reasons:
            self.reasons.insert(0, reason) if escalated else self.reasons.append(reason)

    def merge(self, other: CommandAnalysis) -> None:
        escalated = other.risk > self.risk
        if escalated:
            self.risk = other.risk
        fresh = [r for r in other.reasons if r not in self.reasons]
        self.reasons = fresh + self.reasons if escalated else self.reasons + fresh
        self.programs += other.programs
        self.opaque |= other.opaque
        self.writes |= other.writes


SAFE_PROGS = {
    "ls", "pwd", "cat", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "sort", "uniq", "echo", "printf",
    "which", "whereis", "type", "tree", "diff", "cmp", "stat", "file", "du", "df", "date", "basename", "dirname",
    "realpath", "readlink", "true", "false", "test", "[", "cut", "tr", "tac", "nl", "column", "expr", "seq", "id",
    "whoami", "uname", "hostname", "printenv", "sleep", "jq", "md5sum", "sha1sum", "sha256sum", "cksum", "od",
    "hexdump", "xxd", "strings", "cd", "pushd", "popd", ":", "fold", "paste", "comm", "join", "nproc", "env",
}
DANGEROUS_PROGS = {
    "sudo", "su", "doas", "mkfs", "fdisk", "parted", "shutdown", "reboot", "halt", "poweroff", "mount", "umount",
    "insmod", "rmmod", "iptables", "useradd", "userdel", "usermod", "passwd", "chroot", "setcap", "visudo",
}
SENSITIVE_PROGS = {
    "ssh", "scp", "sftp", "rsync", "nc", "ncat", "netcat", "telnet", "ftp", "docker", "podman", "kubectl", "helm",
    "terraform", "aws", "gcloud", "az", "systemctl", "service", "crontab", "launchctl", "killall", "pkill", "kill",
    "sendmail", "mail",
}
MUTATING = {"rm", "mv", "cp", "mkdir", "rmdir", "touch", "tee", "ln", "chmod", "chown", "chgrp", "truncate",
            "install", "dd", "unlink", "shred", "patch", "rename"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh"}
PIPE_TARGETS = SHELLS | {"python", "python3", "perl", "ruby", "node"}
NETWORK_FETCHERS = {"curl", "wget", "fetch", "nc", "ncat"}
WRAPPERS = {"command", "nohup", "time", "exec", "builtin", "env", "nice", "timeout", "xargs", "stdbuf", "ionice"}
SUBCOMMAND_TOOLS = {"git", "npm", "yarn", "pnpm", "pip", "pip3", "cargo", "go", "make", "docker", "poetry", "uv", "python", "python3"}
SAFE_GIT = {"status", "diff", "log", "show", "rev-parse", "ls-files", "blame", "describe", "shortlog", "grep",
            "ls-tree", "cat-file", "rev-list", "name-rev", "show-ref", "diff-tree", "merge-base", "version", "help"}
READ_OK_PREFIXES = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/opt", "/dev/null", "/dev/stdout", "/dev/stderr",
                    "/dev/zero", "/dev/urandom")
WRITE_OK_PREFIXES = ("/tmp", "/var/tmp", "/dev/null", "/dev/stdout", "/dev/stderr")

RAW_DANGEROUS = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*\s+(-[a-zA-Z]+\s+)*(/|~|\$HOME|/\*|~/\*)(\s|$)"), "recursive delete of / or ~"),
    (re.compile(r":\(\)\s*\{"), "fork bomb"),
    (re.compile(r"\bdd\b[^|;&]*\bof=/dev/"), "writes directly to a device"),
    (re.compile(r">\s*/dev/(sd|nvme|hd|disk)"), "writes directly to a disk"),
    (re.compile(r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z|da)?sh\b"), "pipes a download into a shell"),
    (re.compile(r"\bchmod\s+-R\s+[0-7]{3,4}\s+/(\s|$)"), "recursive chmod on /"),
]
ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
REDIRECT_CHARS = set("<>&")
SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", ";;"}


def verification_key(words: list[str]) -> str:
    prog = os.path.basename(words[0])
    if prog in SUBCOMMAND_TOOLS and len(words) > 1 and not words[1].startswith("-"):
        return f"{prog} {words[1]}"
    if prog in {"python", "python3"} and len(words) > 2 and words[1] == "-m":
        return f"{prog} -m {words[2]}"
    return prog


def _split_lines(command: str) -> list[str]:
    lines, buf, quote, escape = [], [], None, False
    for ch in command:
        if escape:
            buf.append(ch)
            escape = False
        elif ch == "\\" and quote != "'":
            buf.append(ch)
            escape = True
        elif quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            buf.append(ch)
            quote = ch
        elif ch == "\n":
            lines.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    lines.append("".join(buf))
    return [ln for ln in lines if ln.strip()]


def _substitutions(command: str) -> list[str]:
    """Inner commands of $(...) and `...` outside single quotes."""
    out, i, quote = [], 0, None
    while i < len(command):
        ch = command[i]
        if quote == "'":
            if ch == "'":
                quote = None
        elif ch == "'" and quote is None:
            quote = "'"
        elif ch == '"':
            quote = None if quote == '"' else '"'
        elif command.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(command) and depth:
                depth += (command[j] == "(") - (command[j] == ")")
                j += 1
            out.append(command[i + 2 : j - 1])
            i = j
            continue
        elif ch == "`":
            j = command.find("`", i + 1)
            if j != -1:
                out.append(command[i + 1 : j])
                i = j
        i += 1
    return out


class _Analyzer:
    def __init__(self, root: Path, cwd: Path, depth: int):
        self.root, self.cwd, self.depth = root, cwd, depth
        self.result = CommandAnalysis()

    # ---------------------------------------------------------------- paths
    def _looks_like_path(self, tok: str) -> bool:
        if tok in {"..", "."} or tok.startswith(("../", "~/")) or tok == "~" or "/../" in tok or tok.endswith("/.."):
            return tok != "."
        if tok.startswith("/"):
            return Path(tok).parent.exists()
        return False

    def _resolve(self, tok: str) -> Path:
        p = Path(tok).expanduser()
        return (p if p.is_absolute() else self.cwd / p).resolve()

    def _inside(self, p: Path) -> bool:
        return p == self.root or p.is_relative_to(self.root)

    def check_path(self, tok: str, *, write: bool) -> None:
        if "$" in tok or "`" in tok:
            self.result.raise_to(Risk.SENSITIVE if write else Risk.NORMAL, f"path uses a shell variable: {tok}")
            return
        if not self._looks_like_path(tok):
            return
        p = self._resolve(tok)
        if self._inside(p):
            return
        sp = str(p)
        if write:
            if sp.startswith(WRITE_OK_PREFIXES):
                return
            self.result.raise_to(Risk.DANGEROUS, f"writes outside the workspace: {tok}")
        elif not sp.startswith(READ_OK_PREFIXES):
            self.result.raise_to(Risk.NORMAL, f"reads outside the workspace: {tok}")

    # ------------------------------------------------------------- programs
    def _git(self, args: list[str]) -> None:
        i = 0
        while i < len(args):
            a = args[i]
            if a == "-c":
                kv = args[i + 1] if i + 1 < len(args) else ""
                self.result.raise_to(Risk.SENSITIVE if kv.lower().startswith(("core.", "alias.", "credential.", "diff.", "protocol.")) else Risk.NORMAL,
                                     f"git -c {kv} can change how git executes programs")
                i += 2
            elif a in {"-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}:
                if a == "-C" and i + 1 < len(args):
                    self.check_path(args[i + 1], write=False)
                i += 2
            elif a.startswith("-"):
                i += 1
            else:
                break
        sub = args[i] if i < len(args) else ""
        rest = args[i + 1 :]
        r = self.result
        if sub in SAFE_GIT:
            return
        if sub == "branch":
            if any(f in rest for f in ("-D", "-d", "--delete")):
                r.raise_to(Risk.SENSITIVE, "git branch delete")
            elif any(not a.startswith("-") for a in rest) or any(f in rest for f in ("-m", "-M", "-c", "-C")):
                r.raise_to(Risk.NORMAL, "git branch change")
            return
        if sub in {"tag", "remote", "reflog"} and (not rest or all(a in {"-l", "--list", "-v", "show"} for a in rest)):
            return
        if sub == "stash":
            if rest[:1] in (["list"], ["show"]):
                return
            r.raise_to(Risk.SENSITIVE if rest[:1] in (["drop"], ["clear"]) else Risk.NORMAL, "git stash")
            return
        if sub == "push":
            r.raise_to(Risk.SENSITIVE, "git push publishes to a remote")
        elif sub in {"clean", "restore", "rebase", "filter-branch", "filter-repo", "worktree", "gc", "prune"}:
            r.raise_to(Risk.SENSITIVE, f"git {sub} can discard work")
        elif sub == "reset" and any(f in rest for f in ("--hard", "--merge", "--keep")):
            r.raise_to(Risk.SENSITIVE, "git reset --hard discards work")
        elif sub == "checkout" and (any(f in rest for f in ("--", ".", "-f", "--force"))):
            r.raise_to(Risk.SENSITIVE, "git checkout can discard work")
        elif sub == "config" and "--global" in rest:
            r.raise_to(Risk.SENSITIVE, "changes global git config")
        else:
            r.raise_to(Risk.NORMAL, f"git {sub}")
            r.writes = True

    def _rm(self, args: list[str]) -> None:
        recursive = any(a.startswith("-") and not a.startswith("--") and ("r" in a or "R" in a) for a in args) or "--recursive" in args
        targets = [a for a in args if not a.startswith("-")]
        self.result.raise_to(Risk.NORMAL, "deletes files")
        self.result.writes = True
        for t in targets:
            if t in {"/", "~", "/*", "~/*"}:
                self.result.raise_to(Risk.DANGEROUS, f"rm {t}")
            elif "$" in t or "`" in t:
                self.result.raise_to(Risk.SENSITIVE, f"rm with unresolved variable {t}")
            elif t in {"*", ".*", ".", ".."} and recursive:
                self.result.raise_to(Risk.SENSITIVE if t in {"*", ".*"} else Risk.DANGEROUS, f"recursive delete of {t}")
            else:
                p = self._resolve(t)
                if not self._inside(p):
                    self.result.raise_to(Risk.DANGEROUS, f"deletes outside the workspace: {t}")
                elif p == self.root:
                    self.result.raise_to(Risk.DANGEROUS, "deletes the workspace root")

    def _find(self, args: list[str]) -> None:
        if any(a in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"} for a in args):
            self.result.raise_to(Risk.NORMAL, "find with actions (-exec/-delete)")
            self.result.writes = True

    def segment(self, words: list[str], piped_from: str | None) -> None:
        r = self.result
        while words and ASSIGN.match(words[0]):
            words = words[1:]
        while words and os.path.basename(words[0]) in WRAPPERS:
            words = words[1:]
            while words and (words[0].startswith("-") or ASSIGN.match(words[0]) or re.fullmatch(r"\d+[smhd]?", words[0])):
                words = words[1:]
        if not words:
            return
        prog = os.path.basename(words[0])
        args = words[1:]
        r.programs.append(prog)

        if prog in DANGEROUS_PROGS or prog.startswith("mkfs"):
            r.raise_to(Risk.DANGEROUS, f"{prog} is not allowed")
            return
        if prog in SHELLS:
            if "-c" in args and args.index("-c") + 1 < len(args):
                if self.depth < 3:
                    sub = analyze_command(args[args.index("-c") + 1], self.root, self.cwd, self.depth + 1)
                    r.merge(sub)
                r.raise_to(Risk.NORMAL, "runs a nested shell")
            elif piped_from:
                r.raise_to(Risk.DANGEROUS if piped_from in NETWORK_FETCHERS else Risk.SENSITIVE, "pipes data into a shell")
            else:
                r.raise_to(Risk.NORMAL, "runs a shell")
            return
        if prog in PIPE_TARGETS and piped_from in NETWORK_FETCHERS:
            r.raise_to(Risk.DANGEROUS, f"pipes a download into {prog}")
            return
        if prog in SENSITIVE_PROGS:
            r.raise_to(Risk.SENSITIVE, f"{prog} has effects outside the workspace")
        elif prog == "git":
            self._git(args)
        elif prog == "rm":
            self._rm(args)
        elif prog == "find":
            self._find(args)
        elif prog == "sed":
            script = " ".join(a for a in args if not a.startswith("-"))
            if any(a == "-i" or a.startswith("-i") or a == "--in-place" for a in args):
                r.raise_to(Risk.NORMAL, "sed -i edits files")
                r.writes = True
            elif re.search(r"(^|[;{}\s])[weWE]\s", script):
                r.raise_to(Risk.NORMAL, "sed script can write or execute")
        elif prog in SAFE_PROGS:
            pass
        elif prog in MUTATING:
            r.raise_to(Risk.NORMAL, f"{prog} modifies files")
            r.writes = True
            if prog in {"chmod", "chown", "chgrp"} and any(a in {"-R", "--recursive"} for a in args):
                r.raise_to(Risk.SENSITIVE, f"recursive {prog}")
        else:
            r.raise_to(Risk.NORMAL, f"runs {prog}")
        mutating = prog in MUTATING or prog in {"curl", "wget"}
        for a in args:
            if not a.startswith("-") or "=" in a:
                tok = a.split("=", 1)[1] if a.startswith("-") else a
                self.check_path(tok, write=mutating and prog != "curl")

    def line(self, line: str) -> None:
        r = self.result
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            tokens = list(lex)
        except ValueError:
            r.opaque = True
            r.raise_to(Risk.NORMAL, "could not parse the command; treating it as opaque")
            return
        words: list[str] = []
        piped_from: str | None = None
        last_prog: str | None = None
        i = 0

        def flush() -> None:
            nonlocal words, last_prog
            if words:
                self.segment(words, piped_from)
                last_prog = os.path.basename(next((w for w in words if not ASSIGN.match(w)), words[0]))
            words = []

        while i < len(tokens):
            tok = tokens[i]
            if tok in SEPARATORS:
                flush()
                if len(r.programs) > 0 or tok in {"&&", "||", ";", "|", "&"}:
                    r.compound = True
                piped_from = last_prog if tok in {"|", "|&"} else None
                i += 1
                continue
            if tok and set(tok) <= REDIRECT_CHARS:
                target = tokens[i + 1] if i + 1 < len(tokens) else ""
                if tok == "<<" or tok == "<<<" or tok == "<<-":
                    r.opaque = True
                    r.raise_to(Risk.NORMAL, "heredoc input")
                elif ">" in tok and not (tok.endswith("&") and (target.isdigit() or target == "-")):
                    if target not in {"/dev/null", "/dev/stdout", "/dev/stderr"}:
                        r.writes = True
                        r.raise_to(Risk.NORMAL, "redirects output to a file")
                        self.check_path(target, write=True)
                elif "<" in tok and not tok.endswith("&"):
                    self.check_path(target, write=False)
                i += 2
                continue
            if tok.isdigit() and i + 1 < len(tokens) and set(tokens[i + 1]) <= REDIRECT_CHARS and tokens[i + 1]:
                i += 1  # file-descriptor prefix like the 2 in `2>&1`
                continue
            words.append(tok)
            i += 1
        flush()


def analyze_command(command: str, root: Path, cwd: Path | None = None, _depth: int = 0) -> CommandAnalysis:
    root = root.resolve()
    cwd = (cwd or root).resolve()
    result = CommandAnalysis()
    for rx, reason in RAW_DANGEROUS:
        if rx.search(command):
            result.raise_to(Risk.DANGEROUS, reason)
    analyzer = _Analyzer(root, cwd, _depth)
    analyzer.result = result
    lines = _split_lines(command)
    if len(lines) > 1:
        result.compound = True
    for line in lines:
        analyzer.line(line)
    if _depth < 3:
        for inner in _substitutions(command):
            result.opaque = True
            sub = analyze_command(inner, root, cwd, _depth + 1)
            result.merge(sub)
            result.raise_to(Risk.NORMAL, "uses command substitution")
    if not result.programs and not result.reasons:
        result.raise_to(Risk.NORMAL, "empty or unrecognised command")
    if not result.compound and not result.opaque and result.programs:
        try:
            words = shlex.split(lines[0]) if lines else []
            words = [w for w in words if not ASSIGN.match(w)]
            result.key = verification_key(words) if words else None
        except ValueError:
            result.key = None
    return result
