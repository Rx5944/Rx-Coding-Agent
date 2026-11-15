from __future__ import annotations

import json
import subprocess
import unittest

from rx_agent.config import Settings, parse_env_file
from rx_agent.core.context import PRUNE_NOTE, ContextManager
from rx_agent.core.session import Session, SessionStore
from rx_agent.errors import ConfigError
from rx_agent.events import EventBus
from rx_agent.llm.mock import ScriptedLLM
from rx_agent.snapshots import Snapshots
from rx_agent.verify import Verifier, is_verification_command

from .helpers import TempCase, assert_valid_transcript, run


def pair(i: int, size: int = 3000):
    call = {"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": f"f{i}.py"})}}
    return [{"role": "assistant", "content": f"step {i}", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "x" * size}]


def transcript(n: int):
    msgs = [{"role": "user", "content": "build the thing"}]
    for i in range(n):
        msgs += pair(i)
    return msgs


class ContextTests(TempCase):
    def manager(self, window=6000):
        return ContextManager(self.settings(context_window=window), EventBus())

    def test_prune_only_touches_old_big_tool_outputs(self):
        msgs = transcript(12)
        n = ContextManager.prune_tool_outputs(msgs, keep_recent=3)
        self.assertEqual(n, 9)
        tools = [m for m in msgs if m["role"] == "tool"]
        self.assertTrue(tools[0]["content"].endswith(PRUNE_NOTE))
        self.assertEqual(len(tools[-1]["content"]), 3000)

    def test_choose_cut_never_orphans_tool_messages(self):
        msgs = transcript(10)
        for keep in (500, 2000, 5000, 9000, 100000):
            cut = ContextManager.choose_cut(msgs, keep)
            self.assertNotEqual(msgs[cut]["role"], "tool", keep)

    def test_compaction_with_llm_summary_keeps_transcript_valid(self):
        events = []
        bus = EventBus()
        bus.subscribe(events.append)
        mgr = ContextManager(self.settings(context_window=6000), bus)
        session = Session(workspace=str(self.root), messages=transcript(14))
        llm = ScriptedLLM(["GOAL: build the thing\nDONE: read f0..f9"])
        before = mgr.estimate(session.messages)
        self.assertTrue(run(mgr.maybe_compact(session, llm)))
        self.assertLess(mgr.estimate(session.messages), before)
        self.assertIn("<conversation_summary>", session.messages[0]["content"])
        assert_valid_transcript(self, session.messages)
        self.assertEqual(events[-1]["type"], "context_compacted")
        self.assertEqual(events[-1]["method"], "summary")
        self.assertEqual(session.messages[-1]["tool_call_id"], "c13")  # the latest work is preserved verbatim

    def test_compaction_falls_back_when_summarizer_fails(self):
        class Broken(ScriptedLLM):
            async def complete(self, *a, **k):
                raise RuntimeError("model down")

        mgr = self.manager()
        session = Session(workspace="x", messages=transcript(14))
        self.assertTrue(run(mgr.maybe_compact(session, Broken([]))))
        assert_valid_transcript(self, session.messages)
        self.assertIn("build the thing", session.messages[0]["content"])

    def test_no_compaction_when_under_budget(self):
        session = Session(workspace="x", messages=transcript(2))
        self.assertFalse(run(ContextManager(self.settings(context_window=100000), EventBus()).maybe_compact(session, ScriptedLLM([]))))

    def test_prune_stage_alone_can_be_enough(self):
        msgs = transcript(20)
        mgr = self.manager(window=12000)
        session = Session(workspace="x", messages=msgs)
        llm = ScriptedLLM([])
        run(mgr.maybe_compact(session, llm))
        self.assertEqual(llm.calls, [])  # no LLM call was needed


class SessionStoreTests(TempCase):
    def test_roundtrip_list_latest_delete_and_corruption(self):
        store = SessionStore(self.data)
        a = Session(workspace="/w1", messages=[{"role": "user", "content": "é ü 日本"}], title="A")
        store.save(a)
        b = Session(workspace="/w2", title="B")
        store.save(b)
        self.assertEqual(store.load(a.id).messages[0]["content"], "é ü 日本")
        self.assertEqual({r["id"] for r in store.list()}, {a.id, b.id})
        self.assertEqual([r["id"] for r in store.list("/w2")], [b.id])
        self.assertEqual(store.latest("/w1").id, a.id)
        (store.dir / "garbage.json").write_text("{not json")
        self.assertEqual(len(store.list()), 2)
        self.assertIsNone(store.load("garbage"))
        self.assertTrue(store.delete(a.id))
        self.assertIsNone(store.load(a.id))

    def test_path_traversal_in_ids_is_neutralised(self):
        store = SessionStore(self.data)
        self.assertEqual(store._path("../../etc/passwd").parent, store.dir)


class SnapshotTests(TempCase):
    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.root, capture_output=True, text=True).stdout

    def test_restore_reverts_modified_deleted_and_new_files_without_touching_user_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root)
        self.write("a.txt", "one\n")
        self.write("keep.txt", "k\n")
        self.write(".gitignore", "secret.env\n")
        self.write("secret.env", "S\n")
        status_before = self.git("status", "--short")
        snaps = Snapshots(self.root, self.data)
        sid = snaps.create("start")
        self.write("a.txt", "CHANGED\n")
        self.write("new/dir/n.txt", "n\n")
        (self.root / "keep.txt").unlink()
        self.assertEqual(sorted(snaps.changed_since(sid)), ["a.txt", "keep.txt", "new/dir/n.txt"])
        out = snaps.restore(sid)
        self.assertEqual(sorted(out["restored"]), ["a.txt", "keep.txt"])
        self.assertEqual((self.root / "a.txt").read_text(), "one\n")
        self.assertTrue((self.root / "keep.txt").exists())
        self.assertFalse((self.root / "new/dir/n.txt").exists())
        self.assertTrue((self.root / "secret.env").exists())
        self.assertEqual(self.git("status", "--short"), status_before)
        self.assertEqual(self.git("log", "--oneline"), "")  # the user's repo got no commits

    def test_list_returns_newest_first_and_unknown_id_errors(self):
        snaps = Snapshots(self.root, self.data)
        self.write("a.txt", "1")
        first = snaps.create("first")
        self.write("a.txt", "2")
        second = snaps.create("second")
        self.assertEqual([s["id"] for s in snaps.list()], [second, first])
        with self.assertRaises(Exception):
            snaps.restore("deadbeef")


class VerifyTests(TempCase):
    def test_detection(self):
        self.write("tests/test_a.py", "import unittest\n")
        self.assertIn("unittest", Verifier(self.root).detect()["test"])
        self.write("pyproject.toml", "[tool.pytest.ini_options]\n[tool.ruff]\n[tool.mypy]\n")
        found = Verifier(self.root).detect()
        self.assertIn("pytest", found["test"])
        self.assertEqual((found["lint"], found["typecheck"]), ("ruff check .", "mypy ."))

    def test_node_go_and_declared_override(self):
        self.write("package.json", json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}))
        self.write("go.mod", "module x\n")
        found = Verifier(self.root).detect()
        self.assertEqual((found["test"], found["lint"]), ("npm test", "npm run lint"))
        self.write("RX.md", "## Commands\n- test: `make check`\n")
        self.assertEqual(Verifier(self.root).detect()["test"], "make check")

    def test_is_verification_command(self):
        yes = ["pytest -q", "python -m pytest tests/", "npm test", "npm run lint", "cargo test", "go test ./...",
               "python3 -c 'assert 1'", "python app.py", "ruff check .", "make test", "mypy src"]
        no = ["ls -la", "git status", "cat README.md", "mkdir x", "pip install pytest"]
        self.assertEqual([c for c in yes if not is_verification_command(c)], [])
        self.assertEqual([c for c in no if is_verification_command(c)], [])


class ConfigTests(unittest.TestCase):
    def test_from_env_defaults_and_overrides(self):
        s = Settings.from_env({})
        self.assertEqual((s.provider, s.mode, s.sandbox), ("openrouter", "ask", "auto"))
        s = Settings.from_env({"RX_PROVIDER": "ollama", "RX_MODEL": "qwen", "RX_MODE": "auto-edit", "RX_MAX_ITERATIONS": "7",
                               "RX_SANDBOX_NETWORK": "yes", "OPENROUTER_API_KEY": "k"})
        self.assertEqual((s.provider, s.model, s.mode, s.max_iterations, s.sandbox_network, s.api_key),
                         ("ollama", "qwen", "auto_edit", 7, True, None))
        self.assertEqual(Settings.from_env({"OPENROUTER_API_KEY": "abc"}).api_key, "abc")
        self.assertEqual(Settings.from_env({"MODEL_PROVIDER": "nvidia", "NVIDIA_API_KEY": "n"}).base_url, "https://integrate.api.nvidia.com/v1")

    def test_invalid_values_raise_clear_errors(self):
        for env in ({"RX_PROVIDER": "nope"}, {"RX_MODE": "yolo"}, {"RX_MAX_ITERATIONS": "ten"}):
            with self.assertRaises(ConfigError):
                Settings.from_env(env)

    def test_env_file_parser(self):
        import tempfile
        from pathlib import Path
        p = Path(tempfile.mkdtemp()) / ".env"
        p.write_text('# c\nA=1\nexport B="two words"\nC=\'x\'\nD=val # trailing\nbroken\n')
        self.assertEqual(parse_env_file(p), {"A": "1", "B": "two words", "C": "x", "D": "val"})


class AgePruneTests(TempCase):
    @staticmethod
    def write_pair(i, content_chars, result_chars=300):
        args = json.dumps({"path": f"f{i}.html", "content": "x" * content_chars})
        return [{"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "write_file", "arguments": args}}]},
                {"role": "tool", "tool_call_id": f"c{i}", "content": "r" * result_chars}]

    def history(self, n, big=14000):
        msgs = [{"role": "user", "content": "build a site"}]
        for i in range(n):
            msgs += self.write_pair(i, big)
        return msgs

    def test_old_file_bodies_are_dropped_recent_ones_kept_and_json_stays_valid(self):
        msgs = self.history(12)
        changed = ContextManager.age_prune(msgs, keep_turns=4)
        self.assertGreater(changed, 0)
        args = [json.loads(m["tool_calls"][0]["function"]["arguments"]) for m in msgs if m["role"] == "assistant"]
        self.assertIn("omitted", args[0]["content"])
        self.assertEqual(args[0]["path"], "f0.html")  # the path survives, so the model knows what it wrote
        self.assertEqual(len(args[-1]["content"]), 14000)  # recent turns untouched
        self.assertEqual(len(args[-4]["content"]), 14000)
        self.assertIn("omitted", args[-5]["content"])
        assert_valid_transcript(self, msgs)

    def test_idempotent_and_off_switch(self):
        msgs = self.history(10)
        ContextManager.age_prune(msgs, 3)
        self.assertEqual(ContextManager.age_prune(msgs, 3), 0)
        fresh = self.history(10)
        self.assertEqual(ContextManager.age_prune(fresh, 0), 0)
        self.assertEqual(len(json.loads(fresh[1]["tool_calls"][0]["function"]["arguments"])["content"]), 14000)

    def test_old_tool_outputs_keep_head_and_tail(self):
        msgs = self.history(8)
        msgs[2]["content"] = "HEAD" + "m" * 5000 + "TAIL-ERROR"
        ContextManager.age_prune(msgs, 3)
        self.assertTrue(msgs[2]["content"].startswith("HEAD"))
        self.assertTrue(msgs[2]["content"].endswith("TAIL-ERROR"))
        self.assertLess(len(msgs[2]["content"]), 1000)

    def test_edits_and_long_commands_are_shrunk_too(self):
        call = {"id": "c1", "type": "function", "function": {"name": "multi_edit", "arguments": json.dumps(
            {"path": "a.py", "edits": [{"old_text": "o" * 900, "new_text": "n" * 900}]})}}
        cmd = {"id": "c2", "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": "python3 -c '" + "z" * 2000 + "'"})}}
        msgs = [{"role": "user", "content": "x"},
                {"role": "assistant", "content": "", "tool_calls": [call]}, {"role": "tool", "tool_call_id": "c1", "content": "ok"},
                {"role": "assistant", "content": "", "tool_calls": [cmd]}, {"role": "tool", "tool_call_id": "c2", "content": "ok"}]
        msgs += self.write_pair(9, 10) + self.write_pair(10, 10)
        ContextManager.age_prune(msgs, 2)
        edits = json.loads(msgs[1]["tool_calls"][0]["function"]["arguments"])["edits"][0]
        self.assertIn("omitted", edits["old_text"])
        self.assertLess(len(json.loads(msgs[3]["tool_calls"][0]["function"]["arguments"])["command"]), 400)

    def test_substantial_token_savings_on_a_file_writing_run(self):
        """Models the cost structure of a 26-step website build: each step re-sends the full history."""
        full, live = [{"role": "user", "content": "build a premium website"}], [{"role": "user", "content": "build a premium website"}]
        plain = pruned = 0
        for step in range(26):
            add = self.write_pair(step, 14000 if 2 <= step <= 11 else 700, 400)
            full += add
            live += add
            ContextManager.age_prune(live, 6)
            plain += sum(estimate_message_tokens(m) for m in full)
            pruned += sum(estimate_message_tokens(m) for m in live)
        self.assertLess(pruned, plain * 0.55, f"expected >45% saving, got {1 - pruned / plain:.0%}")


from rx_agent.util import estimate_message_tokens  # noqa: E402
