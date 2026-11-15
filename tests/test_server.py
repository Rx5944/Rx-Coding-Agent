from __future__ import annotations

import asyncio
import os
import stat
import time

from rx_agent.llm.mock import ScriptedLLM, tool_call
from rx_agent.sandbox.local import LocalSandbox
from rx_agent.server.handler import ConnectionHandler, ServerConfig
from rx_agent.server.security import (host_allowed, load_or_create_token, origin_allowed, resolve_workspace,
                                      token_ok)

from .helpers import TempCase, run

TOKEN = "t" * 40


class FakeConn:
    def __init__(self):
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self._q: asyncio.Queue = asyncio.Queue()

    async def send(self, obj):
        self.sent.append(obj)
        self._q.put_nowait(obj)

    async def receive(self):
        return await self.inbox.get()

    def push(self, obj):
        self.inbox.put_nowait(obj)

    async def wait_for(self, pred, timeout=10):
        deadline = time.time() + timeout
        for m in list(self.sent):
            if pred(m):
                return m
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise AssertionError(f"timed out; got {[m.get('type') for m in self.sent]}")
            m = await asyncio.wait_for(self._q.get(), left)
            if pred(m):
                return m


def of_type(t):
    return lambda m: m.get("type") == t


class SecurityHelperTests(TempCase):
    def test_origin_and_host_checks(self):
        self.assertTrue(origin_allowed(None, 8000))  # non-browser clients; token still required
        self.assertTrue(origin_allowed("http://127.0.0.1:8000", 8000))
        self.assertTrue(origin_allowed("http://localhost:8000", 8000))
        for evil in ("https://evil.com", "http://127.0.0.1:9999", "http://localhost.evil.com:8000", "null"):
            self.assertFalse(origin_allowed(evil, 8000), evil)
        self.assertTrue(host_allowed("127.0.0.1:8000", 8000))
        self.assertFalse(host_allowed("evil.com:8000", 8000))  # DNS rebinding
        self.assertFalse(host_allowed(None, 8000))
        self.assertTrue(host_allowed("rx.internal", 8000, {"rx.internal"}))

    def test_token_helpers(self):
        self.assertTrue(token_ok(TOKEN, TOKEN))
        self.assertFalse(token_ok("x", TOKEN))
        self.assertFalse(token_ok(None, TOKEN))
        self.assertFalse(token_ok(123, TOKEN))
        t1 = load_or_create_token(self.data)
        self.assertEqual(load_or_create_token(self.data), t1)
        self.assertGreaterEqual(len(t1), 32)
        self.assertEqual(stat.S_IMODE(os.stat(self.data / "server_token").st_mode), 0o600)
        self.assertEqual(load_or_create_token(self.data, "from-env"), "from-env")

    def test_workspace_allowlist(self):
        inner = self.root / "proj"
        inner.mkdir()
        self.assertEqual(resolve_workspace(str(inner), [self.root]), inner)
        self.assertEqual(resolve_workspace(None, [self.root]), self.root)
        for bad in ("/", "/etc", str(self._tmp), str(self.root / ".." / "data")):
            with self.assertRaises(Exception):
                resolve_workspace(bad, [self.root])


class HandlerTests(TempCase):
    def setUp(self):
        super().setUp()
        self.write("a.py", "x = 1\n")

    def start(self, llm, max_mode="ask", **kw):
        settings = self.settings(mode="ask")
        cfg = ServerConfig(token=TOKEN, roots=[self.root], settings=settings, max_mode=max_mode,
                           llm_factory=lambda s: llm, sandbox_factory=lambda s, ws: LocalSandbox(s, ws), **kw)
        handler = ConnectionHandler(cfg)
        conn = FakeConn()
        task = asyncio.create_task(handler.serve(conn))
        return handler, conn, task

    async def login(self, conn):
        conn.push({"type": "auth", "token": TOKEN})
        return await conn.wait_for(of_type("ready"))

    def test_rejects_bad_token_and_missing_auth(self):
        async def go():
            for first in ({"type": "auth", "token": "wrong"}, {"type": "run", "task": "x"}):
                handler, conn, task = self.start(ScriptedLLM([]))
                conn.push(first)
                err = await conn.wait_for(of_type("error"))
                self.assertEqual(err["code"], "unauthorized")
                await asyncio.wait_for(task, 5)
                self.assertNotIn("ready", [m["type"] for m in conn.sent])

        run(go())

    def test_ready_advertises_only_permitted_modes(self):
        async def go():
            handler, conn, task = self.start(ScriptedLLM([]), max_mode="auto_edit")
            ready = await self.login(conn)
            self.assertEqual(ready["modes"], ["plan", "ask", "auto_edit"])
            conn.push(None)
            await task

        run(go())

    def test_approval_round_trip_approve(self):
        llm = ScriptedLLM([tool_call("read_file", "c1", path="a.py"),
                           tool_call("edit_file", "c2", path="a.py", old_text="x = 1", new_text="x = 2"), "done"])

        async def go():
            handler, conn, task = self.start(llm)
            await self.login(conn)
            conn.push({"type": "run", "task": "bump x", "workspace": str(self.root), "mode": "ask"})
            req = await conn.wait_for(of_type("approval_required"))
            self.assertIn("+x = 2", req["preview"])
            self.assertEqual((self.root / "a.py").read_text(), "x = 1\n")  # nothing happens before approval
            conn.push({"type": "approval_response", "id": req["id"], "approved": True})
            done = await conn.wait_for(of_type("run_finished"))
            self.assertEqual(done["result"]["status"], "completed")
            self.assertEqual((self.root / "a.py").read_text(), "x = 2\n")
            conn.push(None)
            await task

        run(go())

    def test_approval_round_trip_deny(self):
        llm = ScriptedLLM([tool_call("read_file", "c1", path="a.py"),
                           tool_call("edit_file", "c2", path="a.py", old_text="x = 1", new_text="x = 2"), "ok, denied"])

        async def go():
            handler, conn, task = self.start(llm)
            await self.login(conn)
            conn.push({"type": "run", "task": "bump x", "mode": "ask"})
            req = await conn.wait_for(of_type("approval_required"))
            conn.push({"type": "approval_response", "id": req["id"], "approved": False, "message": "no thanks"})
            done = await conn.wait_for(of_type("run_finished"))
            self.assertEqual(done["result"]["final_response"], "ok, denied")
            self.assertEqual((self.root / "a.py").read_text(), "x = 1\n")
            conn.push(None)
            await task

        run(go())

    def test_client_cannot_escalate_beyond_server_max_mode(self):
        llm = ScriptedLLM([tool_call("read_file", "c1", path="a.py"),
                           tool_call("edit_file", "c2", path="a.py", old_text="x = 1", new_text="x = 2"), "done"])

        async def go():
            handler, conn, task = self.start(llm, max_mode="ask")
            await self.login(conn)
            conn.push({"type": "run", "task": "x", "mode": "auto"})  # client asks for the moon
            await conn.wait_for(of_type("warning"))
            req = await conn.wait_for(of_type("approval_required"))  # ...but still gets asked
            self.assertEqual((self.root / "a.py").read_text(), "x = 1\n")
            conn.push({"type": "approval_response", "id": req["id"], "approved": False})
            await conn.wait_for(of_type("run_finished"))
            conn.push(None)
            await task

        run(go())

    def test_workspace_outside_roots_is_refused(self):
        async def go():
            handler, conn, task = self.start(ScriptedLLM([]))
            await self.login(conn)
            conn.push({"type": "run", "task": "x", "workspace": "/"})
            err = await conn.wait_for(of_type("error"))
            self.assertIn("outside", err["message"])
            self.assertFalse(any(m["type"] == "task_started" for m in conn.sent))
            conn.push(None)
            await task

        run(go())

    def test_cancel_stops_running_command_and_reports(self):
        marker = self.root / "survived"
        llm = ScriptedLLM([tool_call("run_command", "c1", command=f"sleep 3; touch {marker}")])

        async def go():
            handler, conn, task = self.start(llm)
            await self.login(conn)
            conn.push({"type": "run", "task": "slow", "mode": "auto_edit"})
            req = await conn.wait_for(of_type("approval_required"))
            conn.push({"type": "approval_response", "id": req["id"], "approved": True})
            await conn.wait_for(of_type("tool_started"))
            await asyncio.sleep(0.3)
            t0 = time.time()
            conn.push({"type": "cancel"})  # only possible because the reader keeps reading during a run
            done = await conn.wait_for(of_type("run_finished"))
            self.assertEqual(done["result"]["status"], "cancelled")
            self.assertLess(time.time() - t0, 3)
            await asyncio.sleep(3.2)
            self.assertFalse(marker.exists())
            conn.push(None)
            await task

        run(go())

    def test_busy_and_disconnect_cancels_run(self):
        marker = self.root / "survived2"
        llm = ScriptedLLM([tool_call("run_command", "c1", command=f"sleep 3; touch {marker}")])

        async def go():
            handler, conn, task = self.start(llm)
            await self.login(conn)
            conn.push({"type": "run", "task": "slow", "mode": "auto"})
            await conn.wait_for(of_type("approval_required"))  # unsandboxed => even auto asks
            conn.push({"type": "run", "task": "second"})
            err = await conn.wait_for(of_type("error"))
            self.assertEqual(err["code"], "busy")
            conn.push(None)  # browser tab closed
            await asyncio.wait_for(task, 5)
            self.assertTrue(handler.run_task.done())
            self.assertEqual(handler.broker.pending_ids(), [])

        run(go())

    def test_unknown_message_and_ping(self):
        async def go():
            handler, conn, task = self.start(ScriptedLLM([]))
            await self.login(conn)
            conn.push({"type": "ping"})
            await conn.wait_for(of_type("pong"))
            conn.push({"type": "format_disk"})
            self.assertEqual((await conn.wait_for(of_type("error")))["code"], "bad_request")
            conn.push({"type": "approval_response", "id": "nope", "approved": True})
            self.assertEqual((await conn.wait_for(lambda m: m.get("code") == "unknown_approval"))["type"], "error")
            conn.push(None)
            await task

        run(go())

    def test_session_resume_over_the_wire_and_sessions_listing(self):
        llm = ScriptedLLM(["first", "second"])

        async def go():
            handler, conn, task = self.start(llm)
            await self.login(conn)
            conn.push({"type": "run", "task": "one", "mode": "plan"})
            first = await conn.wait_for(of_type("run_finished"))
            sid = first["result"]["session_id"]
            conn.push({"type": "run", "task": "two", "mode": "plan", "session_id": sid})
            second = await conn.wait_for(lambda m: m.get("type") == "run_finished" and m is not first)
            self.assertEqual(second["result"]["session_id"], sid)
            conn.push({"type": "sessions"})
            listing = await conn.wait_for(of_type("sessions"))
            self.assertEqual(listing["sessions"][0]["messages"], 4)
            conn.push({"type": "run", "task": "x", "session_id": "does-not-exist"})
            self.assertIn("Unknown session", (await conn.wait_for(of_type("error")))["message"])
            conn.push(None)
            await task

        run(go())
