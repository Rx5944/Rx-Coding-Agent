# RX Coding Agent

> **New here?** Run `python scripts/tour.py` (5 min, no API key), then read [docs/LEARNING.md](docs/LEARNING.md) (guided code tour) and work through [docs/CONCEPTS.md](docs/CONCEPTS.md) (34 concepts, each with a runnable demo).

An autonomous coding agent for your terminal, browser and VS Code. It reads your repo, edits code, runs your tests,
shows every step, and asks before doing anything risky. The core is **pure Python standard library** (no SDK, no
framework); FastAPI is only needed if you want the web UI/server.

```bash
pip install -e .                 # core + CLI
pip install -e ".[server]"       # + web UI / HTTP / WebSocket server

cp .env.example .env             # add your API key
rx doctor --ping                 # checks key, git, sandbox, test commands; --ping also tests the model + tool calling
rx "fix the failing test in tests/test_api.py"      # one-shot
rx chat                                              # multi-turn, Ctrl-C cancels a run
rx serve                                             # web UI at the URL it prints
rx eval --oracle                                     # self-test the harness (no API key needed)
```

## What it does well

| | |
|---|---|
| **Understands big repos** | `repo_map` (budgeted symbol map), `find_symbol`, `grep` (ripgrep if installed), `glob`; all `.gitignore`-aware; the index refreshes incrementally so it is never stale. |
| **Edits safely** | Read-before-edit and stale-file detection, exact-match `edit_file`, atomic `multi_edit`, `apply_patch` (unified diffs, miscounted hunks repaired), CRLF preserved, instant syntax check after edits, every change shown as a diff. |
| **Verifies its work** | Auto-detects your test/lint commands (or reads them from `RX.md`), records pass/fail from real exit codes, and nudges the model to verify before it is allowed to say "done". |
| **Never loses your work** | A restore point (shadow git repo, your own repo is untouched) before every run: `rx undo`. |
| **Stays in control** | Async loop with true cancellation: Esc / Ctrl-C kills the model request *and* the whole process tree of running commands. Loop guard stops death spirals. |
| **Controls cost** | Old file bodies and tool output are compressed out of the history every step (they're on disk; ~50% fewer prompt tokens on file-heavy runs), per-run token and time budgets, and the model is told to batch actions into fewer steps. The UI shows prompt vs output tokens and how long a run spent waiting for *you*. |
| **Handles long sessions** | Output truncation that keeps the *tail* of logs, tool-output pruning, then LLM summarisation near the context limit (transcript validity preserved). |
| **Resilient** | Streaming, retry with backoff + `Retry-After`, tolerant parsing of malformed tool-call JSON, sessions saved after every run (`--continue`, `--resume ID`). |

## Permission modes

| mode | edits | commands | use for |
|---|---|---|---|
| `plan` | denied (tools hidden) | read-only only | exploring, designing a change |
| `ask` *(default)* | ask (with diff preview) | safe ones auto, others ask | everyday use |
| `auto_edit` | allowed | safe + test runners auto, others ask | trusted edits, supervised commands |
| `auto` | allowed | allowed **only inside a real sandbox** | unattended runs (needs bubblewrap or Docker) |

Always, in every mode: catastrophic commands (`rm -rf /`, `sudo`, `curl | sh`, writes outside the workspace) are
**denied**; "sensitive" ones (`git push`, `git reset --hard`, `ssh`, `docker`, `rm -rf $VAR`, secret files like `.env`)
**always ask** and can never be pre-approved. See [docs/SECURITY.md](docs/SECURITY.md) for the full, honest model.

## Sandboxing

`RX_SANDBOX=auto` picks the strongest available backend:

1. **bubblewrap** (Linux): read-only system, writable workspace only, no `$HOME`, no network, private PID/IPC namespaces.
2. **Docker**: throwaway container, no network, dropped capabilities, memory/CPU/PID limits.
3. **local**: scrubbed environment (your API keys never reach commands), CPU/file limits, process-group kill, timeouts.
   **This is not isolation.** In this mode `auto` still asks before running non-trivial commands.

Network is off in sandboxes by default; set `RX_SANDBOX_NETWORK=1` for `pip install` / `npm install`.

## Server, web UI, VS Code

`rx serve` prints `http://127.0.0.1:8000/ui#token=…`. The server requires a token, rejects foreign `Origin`/`Host`
headers (cross-site WebSocket hijacking, DNS rebinding), only opens directories under `--workspace-root`, and clamps
every client to `--max-mode` (default `ask`). Approvals are a real async round-trip: the UI shows the diff and
Approve / Always / Deny buttons.

The VS Code extension (`vscode-extension/`) hosts that same UI in a panel: `npm install && npm run compile`, press F5,
run **RX: Start Local Server**, then **RX: Set Server Token** and **RX: Open Agent**. Protocol: [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Project instructions: `RX.md`

Drop an `RX.md` (or `AGENTS.md`) in your repo root. It is injected into the system prompt; lines like
``- test: `make check` `` override command auto-detection.

## Evals

`rx eval` runs 8 tasks (bug fixes, feature implementation, multi-file refactors, "don't edit the tests") against your
configured model with hidden checks, and prints pass rate, steps, tokens and time. `rx eval --oracle` replays reference
solutions through the real loop, which proves the harness works and that every task is solvable and non-trivial.
Run it before and after every prompt/tool change: that is how you tell whether you improved anything.

## Layout

```
src/rx_agent/
  core/         loop (async), session, context (compaction), prompts, guard, state
  llm/          streaming OpenAI-compatible client, retry, scripted mock
  tools/        read/list/glob/grep/repo_map/find_symbol, edit/multi_edit/apply_patch/write, shell, git, todo
  permissions/  command analyzer, policy (modes), async approvals
  sandbox/      local, bubblewrap, docker (+ auto-select)
  workspace/    safe paths, ignore rules, walker, symbol extraction, incremental index
  server/       security helpers, transport-agnostic handler, FastAPI wiring
  evals/        tasks (with reference solutions) + runner
  web/          the UI (plain HTML/CSS/JS, no build step)
  snapshots.py  restore points      verify.py  test-command detection
vscode-extension/   thin shell around the web UI
tests/              110+ tests (stdlib unittest; pytest also works)
```

More: [docs/LEARNING.md](docs/LEARNING.md) (guided path, exercises, debugging) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/SECURITY.md](docs/SECURITY.md) · [CHANGELOG.md](CHANGELOG.md)

## Known limitations

- Quality is bounded by the model. Free/small models call tools unreliably; use `rx eval` to measure yours.
- Symbol extraction is AST-based for Python and regex-based for other languages (no tree-sitter yet).
- Only the root `.gitignore` is honoured (nested ones are not).
- Windows: the local sandbox works, but bubblewrap does not exist there and process-tree handling is weaker (use WSL or Docker).
- Not included yet: subagents, MCP client, web fetch tool, hooks.
# Rx-Coding-Agent
