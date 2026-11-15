from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from .helpers import TempCase, run
from .test_llm import FakeServer, sse

SRC = str(Path(__file__).resolve().parent.parent / "src")


def tool_chunk(name, args, call_id="c1"):
    return [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": call_id, "function": {"name": name, "arguments": json.dumps(args)}}]}}]},
            {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}}]


class CliEndToEnd(TempCase):
    def env(self, server):
        return {"PATH": os.environ["PATH"], "PYTHONPATH": SRC, "HOME": str(self._tmp), "RX_HOME": str(self.data),
                "RX_PROVIDER": "openai-compatible", "OPENAI_COMPATIBLE_BASE_URL": server.url, "RX_MODEL": "fake",
                "RX_SANDBOX": "local", "RX_LLM_RETRIES": "1"}

    def rx(self, server, *args):
        return subprocess.run([sys.executable, "-m", "rx_agent", *args], env=self.env(server), cwd=self._tmp,
                              capture_output=True, text=True, timeout=60)

    def test_run_writes_file_reports_json_then_undo_removes_it(self):
        server = FakeServer([
            lambda h: sse(h, tool_chunk("write_file", {"path": "hello.txt", "content": "hi\n"})),
            lambda h: sse(h, [{"choices": [{"delta": {"content": "Created hello.txt."}}]}]),
        ])
        self.addCleanup(server.close)
        proc = self.rx(server, "run", "create hello.txt", "-w", str(self.root), "--mode", "auto", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "hello.txt").read_text(), "hi\n")
        result = json.loads(proc.stdout[proc.stdout.index("{\n"):])
        self.assertEqual((result["status"], result["files_modified"]), ("completed", ["hello.txt"]))
        self.assertEqual(result["usage"]["total_tokens"], 60)
        # the request really carried tool schemas and our system prompt
        first = server.requests[0]["body"]
        self.assertEqual(first["messages"][0]["role"], "system")
        self.assertIn("write_file", [t["function"]["name"] for t in first["tools"]])
        undo = self.rx(server, "undo", "-w", str(self.root))
        self.assertEqual(undo.returncode, 0, undo.stdout + undo.stderr)
        self.assertFalse((self.root / "hello.txt").exists())
        sessions = self.rx(server, "sessions", "-w", str(self.root))
        self.assertIn("create hello.txt", sessions.stdout)

    def test_missing_api_key_is_a_clean_error_not_a_traceback(self):
        env = {**self.env(FakeServer([])), "RX_PROVIDER": "openrouter"}
        env.pop("OPENAI_COMPATIBLE_BASE_URL")
        proc = subprocess.run([sys.executable, "-m", "rx_agent", "run", "x", "-w", str(self.root)], env=env,
                              cwd=self._tmp, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("OPENROUTER_API_KEY", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_eval_oracle_via_cli(self):
        proc = self.rx(FakeServer([]), "eval", "--oracle", "--task", "fix_off_by_one", "--task", "cli_sum")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2/2 passed", proc.stdout)

    def test_doctor_runs(self):
        proc = self.rx(FakeServer([]), "doctor")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("sandbox:", proc.stdout)


class RipgrepBranchTests(TempCase):
    def test_uses_rg_when_present_and_falls_back_when_it_fails(self):
        from rx_agent.tools import default_registry

        self.write("src/a.py", "needle\n")
        bindir = self._tmp / "bin"
        bindir.mkdir()
        rg = bindir / "rg"
        rg.write_text(f"#!/bin/sh\necho '{self.root}/src/a.py:1:needle'\n")
        rg.chmod(rg.stat().st_mode | stat.S_IEXEC)
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{bindir}:{old}"
        self.addCleanup(os.environ.__setitem__, "PATH", old)
        reg, ctx = default_registry(), self.ctx()
        r = run(reg.execute(ctx, reg.get("grep"), {"pattern": "needle"}))
        self.assertEqual(r.content.strip(), "src/a.py:1:needle")  # absolute prefix stripped
        rg.write_text("#!/bin/sh\nexit 2\n")  # rg error => fallback to the Python implementation
        r = run(reg.execute(ctx, reg.get("grep"), {"pattern": "needle"}))
        self.assertIn("src/a.py:1:needle", r.content)


class DoctorPingTests(TempCase):
    env = CliEndToEnd.env
    rx = CliEndToEnd.rx

    def test_ping_succeeds_and_checks_tool_calling(self):
        server = FakeServer([
            lambda h: sse(h, [{"choices": [{"delta": {"content": "OK"}}]}, {"choices": [], "usage": {"total_tokens": 9}}]),
            lambda h: sse(h, tool_chunk("get_time", {})),
        ])
        self.addCleanup(server.close)
        proc = self.rx(server, "doctor", "--ping")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("model answered", proc.stdout)
        self.assertIn("tool calling works", proc.stdout)

    def test_ping_explains_a_rejected_key(self):
        from .test_llm import error

        server = FakeServer([lambda h: error(h, 401, '{"error":{"message":"No auth credentials found"}}')])
        self.addCleanup(server.close)
        proc = self.rx(server, "doctor", "--ping")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("No auth credentials found", proc.stdout)
        self.assertIn("API key was rejected", proc.stdout)

    def test_ping_flags_models_that_ignore_tools(self):
        server = FakeServer([lambda h: sse(h, [{"choices": [{"delta": {"content": "OK"}}]}]),
                             lambda h: sse(h, [{"choices": [{"delta": {"content": "I cannot do that"}}]}])])
        self.addCleanup(server.close)
        proc = self.rx(server, "doctor", "--ping")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("did NOT call the tool", proc.stdout)
