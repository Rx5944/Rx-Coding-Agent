"""FastAPI wiring. All real logic lives in handler.py/security.py (unit-tested without FastAPI)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from .. import __version__
from ..config import MODES
from ..core.loop import Agent
from ..core.session import SessionStore
from ..events import EventBus
from ..permissions.approvals import StaticApprover
from ..permissions.policy import clamp_mode
from ..workspace.paths import Workspace
from .handler import ConnectionHandler, ServerConfig
from .security import host_allowed, origin_allowed, resolve_workspace, token_ok

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self' ws://127.0.0.1:* ws://localhost:* wss:; frame-ancestors 'self' vscode-webview:; base-uri 'none'")


class FastAPIConnection:
    def __init__(self, ws: WebSocket):
        self.ws = ws

    async def send(self, obj: dict[str, Any]) -> None:
        await self.ws.send_text(json.dumps(obj, default=str))

    async def receive(self) -> dict[str, Any] | None:
        try:
            text = await self.ws.receive_text()
        except WebSocketDisconnect:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"type": "_invalid"}
        return data if isinstance(data, dict) else {"type": "_invalid"}


def create_app(config: ServerConfig) -> FastAPI:
    app = FastAPI(title="RX Coding Agent", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    store = SessionStore(config.settings.data_dir)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if not host_allowed(request.headers.get("host"), config.port, config.extra_hosts):
            return JSONResponse({"error": "host not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer ") or not token_ok(header[7:].strip(), config.token):
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/")
    async def root() -> Response:
        return Response(status_code=307, headers={"Location": "/ui"})

    def static(name: str, mime: str) -> Response:
        return Response((WEB_DIR / name).read_bytes(), media_type=mime, headers={"Content-Security-Policy": CSP})

    @app.get("/ui")
    async def ui() -> Response:
        return static("index.html", "text/html; charset=utf-8")

    @app.get("/ui/app.js")
    async def ui_js() -> Response:
        return static("app.js", "text/javascript; charset=utf-8")

    @app.get("/ui/style.css")
    async def ui_css() -> Response:
        return static("style.css", "text/css; charset=utf-8")

    @app.get("/v1/info")
    async def info(request: Request) -> dict[str, Any]:
        require_token(request)
        return {"version": __version__, "model": config.settings.model, "max_mode": config.max_mode,
                "roots": [str(r) for r in config.roots]}

    @app.get("/v1/sessions")
    async def sessions(request: Request, workspace: str | None = None) -> dict[str, Any]:
        require_token(request)
        ws = resolve_workspace(workspace, config.roots)
        return {"sessions": store.list(str(ws))}

    @app.post("/v1/run")
    async def run_once(request: Request) -> dict[str, Any]:
        """Non-interactive run: anything that would need approval is denied (nobody is there to answer)."""
        require_token(request)
        body = await request.json()
        task = str(body.get("task") or "").strip()
        if not task:
            raise HTTPException(400, "task is required")
        try:
            workspace = resolve_workspace(body.get("workspace"), config.roots)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
        requested = str(body.get("mode") or "plan").replace("-", "_")
        if requested not in MODES:
            raise HTTPException(400, f"mode must be one of {', '.join(MODES)}")
        mode = clamp_mode(requested, config.max_mode)
        kwargs = {"sandbox": config.sandbox_factory(config.settings, workspace)} if config.sandbox_factory else {}
        agent = Agent(llm=config.llm_factory(config.settings), settings=config.settings, workspace=Workspace(workspace),
                      events=EventBus(), approver=StaticApprover(False), store=store, **kwargs)
        session = store.load(body["session_id"]) if body.get("session_id") else None
        result = await agent.run(session or agent.new_session(), task, mode)
        return result.to_dict()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        if not host_allowed(websocket.headers.get("host"), config.port, config.extra_hosts) or not origin_allowed(
                websocket.headers.get("origin"), config.port, config.extra_hosts, config.extra_origins):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        handler = ConnectionHandler(config, store)
        try:
            await handler.serve(FastAPIConnection(websocket))
        finally:
            try:
                await websocket.close()
            except Exception:  # noqa: BLE001
                pass

    return app
