from __future__ import annotations

import asyncio
import json
import time

from rx_agent.core.session import SessionStore
from rx_agent.errors import LLMError
from rx_agent.events import EVENTS
from rx_agent.llm.base import LLMResponse, ToolCall
from rx_agent.llm.mock import ScriptedLLM, tool_call
from rx_agent.permissions.approvals import StaticApprover

from .helpers import TempCase, assert_valid_transcript, run

CHECK = "python3 -c 'import calc; assert calc.add(2,3)==5; print(\"ok\")'"


class LoopTests(TempCase):
    def setUp(self):
        super().setUp()
        self.write("calc.py", "def add(a, b):\n    return a - b\n")

    def fix_script(self):
        return [
            [tool_call("read_file", "c1", path="calc.py"), tool_call("list_dir", "c2")],
            tool_call("edit_file", "c3", path="calc.py", old_text="return a - b", new_text="return a + b"),
            tool_call("run_command", "c4", command=CHECK),
            "Fixed add() in calc.py. Verified with an assertion.",
        ]

    def test_end_to_end_fix_with_verification(self):
        llm = ScriptedLLM(self.fix_script())
        agent, events = self.agent(llm)
        result = run(agent.run(agent.new_session(), "fix add"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.iterations, 4)
        self.assertEqual(result.files_modified, ["calc.py"])
        self.assertTrue(result.verification["passed"])
        self.assertFalse(result.verification["dirty_since_last_pass"])
        self.assertIn("return a + b", (self.root / "calc.py").read_text())
        self.assertEqual(result.usage["total_tokens"], 480)
        unknown = {e["type"] for e in events} - set(EVENTS)
        self.assertEqual(unknown, set())
        sequence = [e["type"] for e in events]
        self.assertEqual(sequence[0], "task_started")
        self.assertEqual(sequence[-1], "task_completed")
        assert_valid_transcript(self, agent_session_messages(llm))

    def test_system_prompt_is_rebuilt_each_step_and_mentions_environment(self):
        self.write("RX.md", "# Rules\n- test: `python3 -m unittest -q`\nAlways be concise.\n")
        llm = ScriptedLLM(["done"])
        agent, _ = self.agent(llm)
        run(agent.run(agent.new_session(), "hi"))
        system = llm.calls[0]["messages"][0]["content"]
        self.assertIn("Always be concise", system)
        self.assertIn("python3 -m unittest -q", system)
        self.assertIn("sandbox 'local'", system)

    def test_denied_edit_does_not_abort_and_model_is_told(self):
        llm = ScriptedLLM([
            tool_call("read_file", "c1", path="calc.py"),
            tool_call("edit_file", "c2", path="calc.py", old_text="a - b", new_text="a + b"),
            "I could not edit the file because you denied it.",
        ])
        approver = StaticApprover(False)
        agent, events = self.agent(llm, mode="ask", approver=approver)
        result = run(agent.run(agent.new_session(), "fix add"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(approver.requests), 1)
        self.assertIn("a - b", (self.root / "calc.py").read_text())
        last_tool_msg = [m for m in llm.calls[-1]["messages"] if m["role"] == "tool"][-1]["content"]
        self.assertIn("denied", last_tool_msg)
        self.assertIn("tool_denied", [e["type"] for e in events])

    def test_approval_preview_is_a_diff_and_remember_skips_next_prompt(self):
        llm = ScriptedLLM([
            tool_call("run_command", "c1", command="python3 -c 'print(1)'"),
            tool_call("run_command", "c2", command="python3 -c 'print(2)'"),
            "done",
        ])
        approver = StaticApprover(True, remember=True)
        agent, _ = self.agent(llm, mode="ask", approver=approver)
        run(agent.run(agent.new_session(), "go"))
        self.assertEqual(len(approver.requests), 1)  # second call was pre-approved by 'remember'

        llm = ScriptedLLM([tool_call("read_file", "c1", path="calc.py"),
                           tool_call("edit_file", "c2", path="calc.py", old_text="a - b", new_text="a + b"), "ok"])
        approver = StaticApprover(True)
        agent, _ = self.agent(llm, mode="ask", approver=approver)
        run(agent.run(agent.new_session(), "go"))
        self.assertIn("+    return a + b", approver.requests[0].preview)

    def test_dangerous_commands_blocked_without_asking_even_in_auto(self):
        llm = ScriptedLLM([tool_call("run_command", "c1", command="rm -rf /"), "ok"])
        approver = StaticApprover(True)
        agent, _ = self.agent(llm, mode="auto", approver=approver)
        run(agent.run(agent.new_session(), "go"))
        self.assertEqual(approver.requests, [])
        self.assertIn("blocked", [m for m in llm.calls[-1]["messages"] if m["role"] == "tool"][-1]["content"].lower())

    def test_plan_mode_hides_edit_tools_and_denies_them(self):
        llm = ScriptedLLM([tool_call("write_file", "c1", path="x.py", content="x"), "plan: change calc.py"])
        agent, _ = self.agent(llm, mode="plan")
        result = run(agent.run(agent.new_session(), "plan it"))
        names = {t["function"]["name"] for t in llm.calls[0]["tools"]}
        self.assertNotIn("edit_file", names)
        self.assertIn("read_file", names)
        self.assertFalse((self.root / "x.py").exists())
        self.assertEqual(result.status, "completed")
        self.assertIn("PLAN MODE", llm.calls[0]["messages"][0]["content"])

    def test_cancel_mid_command_leaves_valid_transcript_and_kills_process(self):
        marker = self.root / "finished"
        llm = ScriptedLLM([tool_call("run_command", "c1", command=f"sleep 3; touch {marker}")])
        agent, events = self.agent(llm)
        session = agent.new_session()

        async def go():
            task = asyncio.create_task(agent.run(session, "slow"))
            for _ in range(100):
                if any(e["type"] == "command_output" or e["type"] == "tool_started" for e in events):
                    break
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.3)
            started = time.time()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertLess(time.time() - started, 3)
            await asyncio.sleep(3.2)

        run(go())
        self.assertFalse(marker.exists(), "cancelled command kept running")
        assert_valid_transcript(self, session.messages)
        self.assertEqual(events[-1]["type"], "task_cancelled")

    def test_loop_guard_stops_death_spirals(self):
        # the guard trips on the 6th identical call; the very next model call is the forced final report
        steps = [tool_call("read_file", f"c{i}", path="missing.txt") for i in range(6)] + ["I am stuck; file missing."]
        agent, _ = self.agent(ScriptedLLM(steps))
        result = run(agent.run(agent.new_session(), "read it"))
        self.assertEqual(result.status, "stuck")
        self.assertLess(result.iterations, 9)
        self.assertIn("stuck", result.final_response)

    def test_agent_is_nudged_to_verify_before_finishing(self):
        llm = ScriptedLLM([
            tool_call("read_file", "c1", path="calc.py"),
            tool_call("edit_file", "c2", path="calc.py", old_text="a - b", new_text="a + b"),
            "All done!",                                  # tries to finish without verifying
            tool_call("run_command", "c3", command=CHECK),  # nudged -> verifies
            "Fixed and verified.",
        ])
        agent, _ = self.agent(llm)
        result = run(agent.run(agent.new_session(), "fix"))
        self.assertEqual(result.final_response, "Fixed and verified.")
        self.assertTrue(result.verification["passed"])
        nudge = [m for m in llm.calls[3]["messages"] if m["role"] == "user" and "system-reminder" in m["content"]]
        self.assertEqual(len(nudge), 1)

    def test_nudge_is_capped_and_skipped_for_docs(self):
        llm = ScriptedLLM([tool_call("write_file", "c1", path="NOTES.md", content="# hi\n"), "done"])
        agent, _ = self.agent(llm)
        self.assertEqual(run(agent.run(agent.new_session(), "write notes")).iterations, 2)
        self.write("x.py", "x = 1\n")
        llm = ScriptedLLM([tool_call("read_file", "c0", path="x.py"),
                           tool_call("edit_file", "c1", path="x.py", old_text="1", new_text="2"), "a", "b", "c", "d"])
        agent, _ = self.agent(llm, max_verify_nudges=2)
        result = run(agent.run(agent.new_session(), "edit"))
        self.assertEqual(result.final_response, "c")  # two nudges, then it is allowed to finish
        self.assertFalse(result.verification["ran"])

    def test_malformed_arguments_and_unknown_tools_are_recoverable(self):
        llm = ScriptedLLM([
            [ToolCall("a", "read_file", '{"path": "calc.py"'), ToolCall("b", "teleport", "{}"),
             ToolCall("c", "read_file", '```json\n{"path": "calc.py",}\n```')],
            "ok",
        ])
        agent, _ = self.agent(llm)
        run(agent.run(agent.new_session(), "go"))
        tools = [m["content"] for m in llm.calls[-1]["messages"] if m["role"] == "tool"]
        self.assertIn("valid JSON", tools[0])
        self.assertIn("Unknown tool 'teleport'", tools[1])
        self.assertIn("return a - b", tools[2])  # fenced JSON with trailing comma was repaired
        assert_valid_transcript(self, llm.calls[-1]["messages"][1:])

    def test_iteration_limit_produces_a_final_report(self):
        steps = [tool_call("list_dir", "c0", path="."), tool_call("glob", "g1", pattern="*.py"),
                 "Ran out of steps; here is where I am."]
        agent, _ = self.agent(ScriptedLLM(steps), max_iterations=2)
        result = run(agent.run(agent.new_session(), "explore"))
        self.assertEqual(result.status, "iteration_limit")
        self.assertIn("where I am", result.final_response)

    def test_parallel_reads_keep_call_order(self):
        self.write("b.txt", "BBB\n")
        llm = ScriptedLLM([[tool_call("read_file", "c1", path="calc.py"), tool_call("read_file", "c2", path="b.txt"),
                            tool_call("glob", "c3", pattern="*.py")], "ok"])
        agent, _ = self.agent(llm)
        run(agent.run(agent.new_session(), "go"))
        msgs = [m for m in llm.calls[-1]["messages"] if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in msgs], ["c1", "c2", "c3"])
        self.assertIn("BBB", msgs[1]["content"])

    def test_llm_failure_returns_error_and_keeps_transcript_valid(self):
        class Boom(ScriptedLLM):
            async def complete(self, *a, **k):
                raise LLMError("HTTP 401", status=401)

        agent, events = self.agent(Boom([]))
        session = agent.new_session()
        result = run(agent.run(session, "go"))
        self.assertEqual(result.status, "error")
        self.assertIn("401", result.error)
        self.assertEqual(events[-1]["type"], "task_failed")

    def test_empty_replies_are_nudged_then_accepted(self):
        llm = ScriptedLLM([LLMResponse(content=""), "real answer"])
        agent, _ = self.agent(llm)
        self.assertEqual(run(agent.run(agent.new_session(), "go")).final_response, "real answer")

    def test_sessions_persist_resume_and_continue(self):
        store = SessionStore(self.data)
        agent, _ = self.agent(ScriptedLLM(["first answer", "second answer"]), store=store)
        session = agent.new_session()
        run(agent.run(session, "first question"))
        loaded = store.load(session.id)
        self.assertEqual([m["role"] for m in loaded.messages], ["user", "assistant"])
        agent2, _ = self.agent(llm2 := ScriptedLLM(["second answer"]), store=store)
        run(agent2.run(loaded, "follow-up"))
        seen = [m.get("content") for m in llm2.calls[0]["messages"]]
        self.assertIn("first answer", seen)  # the model sees the earlier turn
        self.assertEqual(len(store.load(session.id).messages), 4)
        self.assertEqual(store.latest(str(self.root)).id, session.id)

    def test_undo_restores_workspace(self):
        llm = ScriptedLLM([tool_call("read_file", "c1", path="calc.py"),
                           tool_call("edit_file", "c2", path="calc.py", old_text="a - b", new_text="a + b"),
                           tool_call("write_file", "c3", path="new.txt", content="n"), "done"])
        agent, events = self.agent(llm, snapshots=True)
        result = run(agent.run(agent.new_session(), "change things"))
        self.assertIsNotNone(result.snapshot_id)
        self.assertTrue((self.root / "new.txt").exists())
        out = run(agent.undo())
        self.assertTrue(out["ok"], out)
        self.assertEqual((self.root / "calc.py").read_text(), "def add(a, b):\n    return a - b\n")
        self.assertFalse((self.root / "new.txt").exists())
        self.assertIn("snapshot_created", [e["type"] for e in events])

    def test_secrets_in_parent_environment_never_reach_commands(self):
        import os
        os.environ["OPENROUTER_API_KEY"] = "sk-or-should-not-leak"
        self.addCleanup(os.environ.pop, "OPENROUTER_API_KEY", None)
        llm = ScriptedLLM([tool_call("run_command", "c1", command="env"), "ok"])
        agent, _ = self.agent(llm)
        run(agent.run(agent.new_session(), "dump env"))
        out = [m for m in llm.calls[-1]["messages"] if m["role"] == "tool"][-1]["content"]
        self.assertNotIn("sk-or-should-not-leak", out)
        self.assertNotIn("OPENROUTER", out)


def agent_session_messages(llm: ScriptedLLM):
    return llm.calls[-1]["messages"][1:]


class ApprovalEventTests(TempCase):
    def test_approval_event_carries_timeout_for_broker_approvers(self):
        from rx_agent.permissions.approvals import BrokerApprover

        self.write("a.py", "x = 1\n")
        broker = BrokerApprover(timeout=0.3)  # nobody answers => auto-deny, exactly like the screenshot scenario
        llm = ScriptedLLM([tool_call("read_file", "c1", path="a.py"),
                           tool_call("edit_file", "c2", path="a.py", old_text="x = 1", new_text="x = 2"), "gave up"])
        agent, events = self.agent(llm, mode="ask", approver=broker)
        result = run(agent.run(agent.new_session(), "bump"))
        req = next(e for e in events if e["type"] == "approval_required")
        self.assertEqual(req["timeout"], 0.3)
        self.assertIn("timed out", next(e for e in events if e["type"] == "tool_denied")["reason"])
        self.assertEqual(result.status, "completed")
        self.assertEqual((self.root / "a.py").read_text(), "x = 1\n")


class BudgetAndCostTests(TempCase):
    def test_token_budget_ends_the_run_with_a_report(self):
        from rx_agent.llm.base import LLMResponse, Usage

        self.write("a.txt", "x\n")
        heavy = lambda name, i: LLMResponse(tool_calls=[tool_call(name, f"c{i}", path="a.txt")], usage=Usage(30000, 100, 30100))  # noqa: E731
        llm = ScriptedLLM([heavy("read_file", 1), heavy("read_file", 2), "Stopped at budget; read a.txt twice."])
        agent, events = self.agent(llm, max_run_tokens=50000)
        result = run(agent.run(agent.new_session(), "go"))
        self.assertEqual(result.status, "budget_exceeded")
        self.assertIn("budget", [m for m in llm.calls[-1]["messages"] if m["role"] == "user"][-1]["content"])
        self.assertIn("Stopped at budget", result.final_response)
        self.assertLessEqual(result.iterations, 2)

    def test_budget_zero_disables_it(self):
        agent, _ = self.agent(ScriptedLLM(["done"]), max_run_tokens=0, max_run_seconds=0)
        self.assertEqual(run(agent.run(agent.new_session(), "go")).status, "completed")

    def test_time_budget_ignores_time_spent_waiting_for_the_human(self):
        from rx_agent.permissions.approvals import CallbackApprover, ApprovalResponse

        self.write("a.py", "x = 1\n")

        async def slow_human(req):
            await asyncio.sleep(1.3)  # the user went to get coffee
            return ApprovalResponse(True)

        llm = ScriptedLLM([tool_call("read_file", "c1", path="a.py"),
                           tool_call("edit_file", "c2", path="a.py", old_text="x = 1", new_text="x = 2"),
                           tool_call("run_command", "c3", command="python3 -c 'print(1)'"), "done"])
        agent, _ = self.agent(llm, mode="ask", approver=CallbackApprover(slow_human), max_run_seconds=1)
        result = run(agent.run(agent.new_session(), "go"))
        self.assertEqual(result.status, "completed")  # 2.6s of wall time, but only the agent's own time counts
        self.assertGreater(result.approval_wait, 2.4)
        self.assertGreater(result.duration, result.approval_wait)

    def test_old_file_bodies_are_not_resent_to_the_model(self):
        big = "<html>" + "A" * 6000 + "</html>"
        steps = [tool_call("write_file", f"w{i}", path=f"p{i}.html", content=big.replace("A", chr(65 + i))) for i in range(9)] + ["done"]
        llm = ScriptedLLM(steps)
        agent, _ = self.agent(llm, prune_keep_turns=3)
        run(agent.run(agent.new_session(), "make pages"))
        final_request = json.dumps(llm.calls[-1]["messages"])
        self.assertNotIn("A" * 100, final_request)           # page 0's body is gone...
        self.assertIn("p0.html", final_request)               # ...but the model still knows the file exists
        self.assertIn("I" * 100, final_request)               # the newest page body is intact
        self.assertEqual((self.root / "p0.html").read_text(), big.replace("A", "A"))  # and the file on disk is untouched

    def test_system_prompt_teaches_batching(self):
        llm = ScriptedLLM(["ok"])
        agent, _ = self.agent(llm)
        run(agent.run(agent.new_session(), "hi"))
        self.assertIn("Batch independent actions", llm.calls[0]["messages"][0]["content"])


class FailureVisibilityTests(TempCase):
    def test_failed_run_reports_error_text_in_result_and_server_log(self):
        from rx_agent.server.handler import ConnectionHandler, ServerConfig
        from rx_agent.llm.base import LLMClient
        from .test_server import FakeConn, TOKEN, of_type

        class Rejecting(LLMClient):
            model = "m"

            async def complete(self, *a, **k):
                raise LLMError("HTTP 402 from model API: Insufficient credits\n→ out of credits", status=402)

        cfg = ServerConfig(token=TOKEN, roots=[self.root], settings=self.settings(mode="ask"), llm_factory=lambda s: Rejecting(),
                           sandbox_factory=lambda s, ws: __import__("rx_agent.sandbox.local", fromlist=["x"]).LocalSandbox(s, ws))

        async def go():
            handler, conn = ConnectionHandler(cfg), FakeConn()
            task = asyncio.create_task(handler.serve(conn))
            conn.push({"type": "auth", "token": TOKEN})
            await conn.wait_for(of_type("ready"))
            conn.push({"type": "run", "task": "hello", "mode": "plan"})
            done = await conn.wait_for(of_type("run_finished"))
            conn.push(None)
            await task
            return done

        with self.assertLogs("rx.server", level="WARNING") as logs:
            done = run(go())
        self.assertEqual(done["result"]["status"], "error")
        self.assertIn("Insufficient credits", done["result"]["error"])
        self.assertTrue(any("Insufficient credits" in line for line in logs.output))


class MalformedToolCallTests(TempCase):
    """Regression for: 'Run failed: Internal error: KeyError: path' killing a run mid-build."""

    def tool_text(self, llm):
        return [m["content"] for m in llm.calls[-1]["messages"] if m["role"] == "tool"]

    def test_write_file_without_path_is_a_recoverable_error_not_a_crash(self):
        llm = ScriptedLLM([
            tool_call("write_file", "w1", path="target/index.html", content="<html></html>"),
            [ToolCall("w2", "write_file", "")],                 # empty arguments
            [ToolCall("w3", "write_file", '{"file_path": "x.css", "content": "a{}"}')],   # wrong key name
            tool_call("write_file", "w4", path="target/style.css", content="a{}"),         # model recovers
            "done",
        ])
        approver = StaticApprover(True)
        agent, events = self.agent(llm, mode="ask", approver=approver)
        result = run(agent.run(agent.new_session(), "build site"))
        self.assertEqual(result.status, "completed", result.error)
        self.assertEqual(result.files_modified, ["target/index.html", "target/style.css"])
        self.assertEqual(len(approver.requests), 2)  # the user is never asked to approve a call that cannot run
        text = "\n".join(self.tool_text(llm))
        self.assertIn("missing required argument 'path'", text)
        self.assertIn("unknown argument 'file_path'", text)
        self.assertTrue((self.root / "target/style.css").exists())

    def test_output_truncation_gets_an_actionable_hint(self):
        cut = LLMResponse(tool_calls=[ToolCall("w1", "write_file", '{"path": "big.html", "content": "<html><body>' + "x" * 50)],
                          finish_reason="length")
        llm = ScriptedLLM([cut, tool_call("write_file", "w2", path="a.html", content="<p>"), "split it up"])
        agent, _ = self.agent(llm)
        result = run(agent.run(agent.new_session(), "big page"))
        self.assertEqual(result.status, "completed")
        self.assertIn("CUT OFF", self.tool_text(llm)[0])
        self.assertIn("smaller pieces", self.tool_text(llm)[0])
        for m in llm.calls[-1]["messages"]:               # the transcript never keeps invalid JSON arguments
            for c in m.get("tool_calls") or []:
                json.loads(c["function"]["arguments"])

    def test_failing_preview_does_not_kill_the_run(self):
        from rx_agent.tools.base import Tool, ToolResult

        class Weird(Tool):
            name, description, category = "weird_edit", "x", "edit"
            parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

            async def preview(self, ctx, args):
                raise RuntimeError("preview exploded")

            def paths(self, args):
                return [args["path"]]

            async def run(self, ctx, args):
                return ToolResult.success("did it", paths=[args["path"]])

        llm = ScriptedLLM([tool_call("weird_edit", "c1", path="a.txt"), "ok"])
        approver = StaticApprover(True)
        agent, _ = self.agent(llm, mode="ask", approver=approver)
        agent.registry.register(Weird())
        result = run(agent.run(agent.new_session(), "go"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(approver.requests), 1)
        self.assertIn("did it", self.tool_text(llm)[0])

    def test_unexpected_exception_in_one_tool_call_only_fails_that_call(self):
        from rx_agent.tools.base import Tool, ToolResult

        class Broken(Tool):
            name, description, category = "broken_edit", "x", "edit"
            parameters = {"type": "object", "properties": {}}

            def paths(self, args):
                raise RuntimeError("boom in policy path")

            async def run(self, ctx, args):
                return ToolResult.success("never")

        self.write("a.txt", "hello\n")
        llm = ScriptedLLM([[tool_call("broken_edit", "c1"), tool_call("read_file", "c2", path="a.txt")], "recovered"])
        agent, events = self.agent(llm)
        agent.registry.register(Broken())
        result = run(agent.run(agent.new_session(), "go"))
        self.assertEqual(result.status, "completed")
        out = self.tool_text(llm)
        self.assertIn("Internal error while handling broken_edit", out[0])
        self.assertIn("hello", out[1])                    # the next call in the same turn still ran
        self.assertIn("warning", [e["type"] for e in events])
        assert_valid_transcript(self, llm.calls[-1]["messages"][1:])
