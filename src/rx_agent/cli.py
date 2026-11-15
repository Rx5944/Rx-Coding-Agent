from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import sys
from pathlib import Path

from . import __version__
from .config import MODES, Settings, load_env_files
from .core.loop import Agent
from .core.session import SessionStore
from .errors import ConfigError, RXError
from .events import EventBus
from .llm.registry import create_llm
from .permissions.approvals import StaticApprover
from .render import CliApprover, ConsoleRenderer, make_style
from .sandbox.select import create_sandbox
from .verify import Verifier
from .workspace.paths import Workspace

COMMANDS = {"run", "chat", "serve", "sessions", "undo", "eval", "doctor", "version"}


def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-w", "--workspace", default=".", help="project directory (default: current directory)")
    p.add_argument("--mode", choices=MODES, help="plan | ask | auto_edit | auto (default: ask)")
    p.add_argument("--model", help="model name (overrides RX_MODEL)")
    p.add_argument("--provider", help="openrouter | nvidia | openai | ollama | openai-compatible")
    p.add_argument("--sandbox", choices=["auto", "bwrap", "docker", "local"], help="command isolation backend")
    p.add_argument("--verbose", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rx", description="RX coding agent")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run one task and exit")
    r.add_argument("task", nargs="+")
    add_common(r)
    g = r.add_mutually_exclusive_group()
    g.add_argument("--resume", metavar="ID", help="continue a saved session")
    g.add_argument("--continue", dest="cont", action="store_true", help="continue the latest session here")
    r.add_argument("--json", action="store_true", help="print the final result as JSON (for scripts/CI)")
    c = sub.add_parser("chat", help="interactive multi-turn session")
    add_common(c)
    c.add_argument("--resume", metavar="ID")
    c.add_argument("--continue", dest="cont", action="store_true")
    s = sub.add_parser("serve", help="start the HTTP/WebSocket server + web UI")
    add_common(s)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--workspace-root", action="append", default=[], help="directories clients may open (repeatable)")
    s.add_argument("--max-mode", choices=MODES, default="ask", help="highest autonomy any client may request")
    ss = sub.add_parser("sessions", help="list saved sessions")
    ss.add_argument("-w", "--workspace", default=None)
    u = sub.add_parser("undo", help="restore the workspace to a restore point")
    u.add_argument("-w", "--workspace", default=".")
    u.add_argument("--list", action="store_true", help="list restore points")
    u.add_argument("--to", metavar="ID", help="restore point id (default: latest)")
    e = sub.add_parser("eval", help="run the evaluation suite")
    add_common(e)
    e.add_argument("--task", action="append", help="run only these task ids")
    e.add_argument("--oracle", action="store_true", help="use reference solutions instead of a model (harness self-test)")
    e.add_argument("--out", help="write a JSON report here")
    d = sub.add_parser("doctor", help="check configuration, sandbox and tools")
    d.add_argument("--ping", action="store_true", help="send two tiny requests to verify the key, model and tool-calling")
    sub.add_parser("version")
    return p


def load_settings(args) -> Settings:
    load_env_files()
    settings = Settings.from_env()
    for attr, key in (("mode", "mode"), ("model", "model"), ("provider", "provider"), ("sandbox", "sandbox")):
        value = getattr(args, attr, None)
        if value:
            setattr(settings, key, value)
    if getattr(args, "provider", None):
        fresh = Settings.from_env({**os.environ, "RX_PROVIDER": args.provider})
        settings.base_url, settings.api_key = fresh.base_url, fresh.api_key
    return settings


def make_agent(settings: Settings, workspace: Path, interactive: bool, verbose: bool):
    bus = EventBus()
    bus.subscribe(ConsoleRenderer(verbose=verbose))
    ws = Workspace(workspace)
    approver = CliApprover() if interactive else StaticApprover(False)
    agent = Agent(llm=create_llm(settings), settings=settings, workspace=ws, events=bus, approver=approver,
                  store=SessionStore(settings.data_dir))
    return agent


async def run_with_sigint(agent: Agent, session, text: str, mode: str | None):
    """Ctrl-C cancels the current run (killing running commands) instead of killing the program."""
    task = asyncio.ensure_future(agent.run(session, text, mode))
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, task.cancel)
    except (NotImplementedError, RuntimeError):
        pass
    try:
        return await task
    except asyncio.CancelledError:
        return None
    finally:
        try:
            loop.remove_signal_handler(signal.SIGINT)
        except (NotImplementedError, RuntimeError):
            pass


def pick_session(agent: Agent, args):
    store = agent.store
    if getattr(args, "resume", None):
        s = store.load(args.resume)
        if s is None:
            raise RXError(f"No session {args.resume!r}")
        return s
    if getattr(args, "cont", False):
        s = store.latest(str(agent.workspace.root))
        if s:
            return s
    return agent.new_session()


def cmd_run(args) -> int:
    settings = load_settings(args)
    agent = make_agent(settings, Path(args.workspace), sys.stdin.isatty(), args.verbose)
    session = pick_session(agent, args)
    result = asyncio.run(run_with_sigint(agent, session, " ".join(args.task), args.mode))
    if args.json and result:
        print(json.dumps(result.to_dict(), indent=2))
    if result is None:
        return 130
    return 0 if result.status == "completed" else 1


def cmd_chat(args) -> int:
    settings = load_settings(args)
    agent = make_agent(settings, Path(args.workspace), True, args.verbose)
    session = pick_session(agent, args)
    mode = args.mode or settings.mode
    s = make_style()
    print(s.bold(f"RX {__version__}") + s.dim(f"  workspace={agent.workspace.root}  model={settings.model}  mode={mode}  sandbox={agent.sandbox.kind}"))
    print(s.dim("Type a task. /help for commands. Ctrl-C cancels a running task."))

    async def loop() -> None:
        nonlocal session, mode
        while True:
            try:
                line = (await asyncio.to_thread(input, s.cyan("\n› "))).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                continue
            if line.startswith("/"):
                cmd, _, rest = line.partition(" ")
                if cmd in ("/exit", "/quit"):
                    return
                if cmd == "/help":
                    print("/mode <plan|ask|auto_edit|auto>  /undo  /new  /todos  /session  /exit")
                elif cmd == "/mode" and rest in MODES:
                    mode = rest
                    print(f"mode = {mode}")
                elif cmd == "/undo":
                    out = await agent.undo()
                    print(out if not out.get("ok") else f"restored {len(out['restored'])} file(s), removed {len(out['deleted'])}")
                elif cmd == "/new":
                    session = agent.new_session()
                    agent.reset_file_tracking()
                    print("new session")
                elif cmd == "/todos":
                    for t in session.todos:
                        print(f"[{t['status']}] {t['content']}")
                elif cmd == "/session":
                    print(session.id)
                else:
                    print("unknown command; /help")
                continue
            await run_with_sigint(agent, session, line, mode)

    asyncio.run(loop())
    return 0


def cmd_serve(args) -> int:
    try:
        import uvicorn  # noqa: F401
        from .server.app import create_app
    except ImportError:
        print("The server needs extra packages:  pip install 'rx-coding-agent[server]'", file=sys.stderr)
        return 2
    from .server.handler import ServerConfig
    from .server.security import load_or_create_token

    import logging

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings(args)
    roots = [Path(r).expanduser().resolve() for r in (args.workspace_root or [args.workspace])]
    token = load_or_create_token(settings.data_dir, os.environ.get("RX_SERVER_TOKEN"))
    extra_hosts = {h for h in os.environ.get("RX_ALLOWED_HOSTS", "").split(",") if h}
    config = ServerConfig(token=token, roots=roots, max_mode=args.max_mode, settings=settings, host=args.host,
                          port=args.port, extra_hosts=extra_hosts)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: binding to a non-loopback address exposes an agent that can run commands. "
              "Put it behind TLS + authentication and set RX_ALLOWED_HOSTS.", file=sys.stderr)
    print(f"RX server  max-mode={args.max_mode}  roots={', '.join(map(str, roots))}")
    print(f"Open:  http://{args.host}:{args.port}/ui#token={token}")
    import uvicorn
    uvicorn.run(create_app(config), host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_sessions(args) -> int:
    settings = Settings.from_env()
    ws = str(Path(args.workspace).resolve()) if args.workspace else None
    for row in SessionStore(settings.data_dir).list(ws):
        print(f"{row['id']}  {row['messages']:>4} msgs  {row['title'][:60]}  [{row['workspace']}]")
    return 0


def cmd_undo(args) -> int:
    from .snapshots import Snapshots

    settings = Settings.from_env()
    root = Path(args.workspace).resolve()
    snaps = Snapshots(root, settings.data_dir)
    if args.list:
        import datetime
        for s in snaps.list():
            print(f"{s['id'][:10]}  {datetime.datetime.fromtimestamp(s['ts']):%Y-%m-%d %H:%M:%S}  {s['label']}")
        return 0
    target = args.to or (snaps.list(1)[0]["id"] if snaps.list(1) else None)
    if not target:
        print("No restore points for this workspace.", file=sys.stderr)
        return 1
    full = next((s["id"] for s in snaps.list(200) if s["id"].startswith(target)), target)
    out = snaps.restore(full)
    print(f"restored {len(out['restored'])} file(s), removed {len(out['deleted'])} new file(s) (to {full[:10]})")
    return 0


def cmd_eval(args) -> int:
    from .evals.runner import format_report, run_suite
    from .evals.tasks import TASKS

    settings = load_settings(args)
    tasks = [t for t in TASKS if not args.task or t.id in args.task]
    if args.oracle:
        settings.mode = "auto"
    report = asyncio.run(run_suite(tasks, settings, oracle=args.oracle))
    print(format_report(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
    return 0 if report["passed"] == report["total"] else 1


def cmd_doctor(args) -> int:
    load_env_files()
    s = make_style()
    ok, bad = s.green("ok "), s.red("!! ")
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(bad + str(exc))
        return 1
    print(f"rx {__version__}  python {sys.version.split()[0]}")
    print(f"{ok}provider={settings.provider} model={settings.model} base_url={settings.base_url}")
    key = settings.api_key
    needs_key = settings.provider not in ("ollama", "openai-compatible")
    print(f"{ok if key or not needs_key else bad}api key: {'set (' + key[:4] + '…)' if key else ('not needed' if not needs_key else 'MISSING')}")
    for tool, hint in (("git", "required for undo, apply_patch and git tools"), ("rg", "optional: faster grep"),
                       ("bwrap", "optional: strong sandbox (Linux)"), ("docker", "optional: strong sandbox")):
        found = shutil.which(tool)
        print(f"{ok if found or tool in ('rg', 'bwrap', 'docker') else bad}{tool}: {found or 'not found'}  {s.dim('(' + hint + ')')}")
    try:
        sb = create_sandbox(settings, Path.cwd())
        note = "real isolation" if sb.isolated else "NO isolation: relies on permission prompts (install bubblewrap or Docker for auto mode)"
        print(f"{ok if sb.isolated else s.yellow('~~ ')}sandbox: {sb.kind}  {s.dim(note)}")
    except RXError as exc:
        print(bad + str(exc))
    detected = Verifier(Path.cwd()).detect()
    print(f"{ok}detected commands here: {detected or 'none'}")
    print(f"{ok}data dir: {settings.data_dir}")
    if getattr(args, "ping", False):
        return ping_model(settings, s)
    return 0


def ping_model(settings: Settings, s) -> int:
    """Live check of the exact thing that failed in the UI: key, credits, model name and tool-calling."""
    import time

    ok, bad = s.green("ok "), s.red("!! ")
    try:
        llm = create_llm(settings)
    except RXError as exc:
        print(bad + str(exc))
        return 1
    llm.retries = 1  # type: ignore[attr-defined]
    try:
        t0 = time.time()
        resp = asyncio.run(llm.complete([{"role": "user", "content": "Reply with the single word OK."}]))
        print(f"{ok}model answered in {time.time() - t0:.1f}s: {resp.content.strip()[:60]!r}  ({resp.usage.total_tokens} tokens)")
    except RXError as exc:
        print(bad + "request failed:\n   " + str(exc).replace("\n", "\n   "))
        return 1
    tool = {"type": "function", "function": {"name": "get_time", "description": "Returns the current time. Call it.",
                                             "parameters": {"type": "object", "properties": {}}}}
    try:
        resp = asyncio.run(llm.complete([{"role": "user", "content": "Call the get_time tool now."}], [tool]))
    except RXError as exc:
        print(bad + "tool-calling request failed:\n   " + str(exc).replace("\n", "\n   "))
        return 1
    if resp.tool_calls:
        print(f"{ok}tool calling works ({resp.tool_calls[0].name})")
        return 0
    print(s.yellow("~~ ") + "this model did NOT call the tool. The agent depends on tool calls: expect poor results. Try another model.")
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS:
        argv = ["run", *argv]  # `rx "fix the bug"` shortcut
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    handlers = {"run": cmd_run, "chat": cmd_chat, "serve": cmd_serve, "sessions": cmd_sessions, "undo": cmd_undo,
                "eval": cmd_eval, "doctor": cmd_doctor, "version": lambda a: print(__version__) or 0}
    try:
        return handlers[args.cmd](args)
    except (RXError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
