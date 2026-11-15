from __future__ import annotations


from rx_agent.errors import ToolError
from rx_agent.tools import default_registry
from rx_agent.tools.validate import validate_args
from rx_agent.workspace.paths import Workspace

from .helpers import TempCase, run


def call(case, tool_name, ctx=None, **args):
    ctx = ctx or case.ctx()
    reg = default_registry()
    return run(reg.execute(ctx, reg.get(tool_name), args)), ctx


class ValidationTests(TempCase):
    def test_coercion_and_errors(self):
        schema = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1}, "b": {"type": "boolean"},
                                                   "s": {"type": "string"}}, "required": ["s"]}
        ok, err = validate_args(schema, {"s": "x", "n": "5", "b": "true"})
        self.assertEqual((ok, err), ({"s": "x", "n": 5, "b": True}, None))
        self.assertIn("missing required", validate_args(schema, {})[1])
        self.assertIn("unknown argument", validate_args(schema, {"s": "x", "zzz": 1})[1])
        self.assertIn(">= 1", validate_args(schema, {"s": "x", "n": 0})[1])


class PathTests(TempCase):
    def test_escapes_are_rejected(self):
        ws = Workspace(self.root)
        for bad in ("../x", "/etc/passwd", "a/../../x"):
            with self.assertRaises(ToolError):
                ws.resolve(bad)

    def test_symlink_escape_is_rejected(self):
        (self._tmp / "outside.txt").write_text("secret")
        (self.root / "link").symlink_to(self._tmp / "outside.txt")
        with self.assertRaises(ToolError):
            Workspace(self.root).resolve("link")

    def test_absolute_path_inside_workspace_is_accepted(self):
        self.write("a.txt", "x")
        self.assertEqual(Workspace(self.root).resolve(str(self.root / "a.txt")), self.root / "a.txt")


class ReadWriteEditTests(TempCase):
    def test_read_numbers_lines_and_paginates(self):
        self.write("f.txt", "\n".join(f"line{i}" for i in range(1, 11)) + "\n")
        r, _ = call(self, "read_file", path="f.txt", offset=3, limit=2)
        self.assertTrue(r.ok)
        self.assertIn("     3\tline3", r.content)
        self.assertIn("offset=5", r.content)
        self.assertNotIn("line5\n", r.content.replace("offset=5", ""))

    def test_binary_and_missing_files(self):
        (self.root / "b.bin").write_bytes(b"\x00\x01\x02")
        self.assertIn("binary", call(self, "read_file", path="b.bin")[0].content)
        self.assertFalse(call(self, "read_file", path="nope.txt")[0].ok)

    def test_edit_requires_read_and_detects_staleness(self):
        p = self.write("a.py", "x = 1\n")
        ctx = self.ctx()
        r, _ = call(self, "edit_file", ctx, path="a.py", old_text="x = 1", new_text="x = 2")
        self.assertFalse(r.ok)
        self.assertIn("not read", r.content)
        call(self, "read_file", ctx, path="a.py")
        p.write_text("x = 99\n")  # changed behind the agent's back
        r, _ = call(self, "edit_file", ctx, path="a.py", old_text="x = 99", new_text="x = 2")
        self.assertFalse(r.ok)
        self.assertIn("changed on disk", r.content)

    def test_edit_happy_path_returns_diff_and_updates_tracker(self):
        p = self.write("a.py", "def f():\n    return 1\n")
        ctx = self.ctx()
        call(self, "read_file", ctx, path="a.py")
        r, _ = call(self, "edit_file", ctx, path="a.py", old_text="return 1", new_text="return 2")
        self.assertTrue(r.ok)
        self.assertIn("-    return 1", r.content)
        self.assertIn("+    return 2", r.content)
        # a second edit works without re-reading because the tracker saw our own write
        r, _ = call(self, "edit_file", ctx, path="a.py", old_text="return 2", new_text="return 3")
        self.assertTrue(r.ok)
        self.assertEqual(p.read_text(), "def f():\n    return 3\n")

    def test_non_unique_match_and_replace_all(self):
        self.write("a.txt", "foo\nbar\nfoo\n")
        ctx = self.ctx()
        call(self, "read_file", ctx, path="a.txt")
        r, _ = call(self, "edit_file", ctx, path="a.txt", old_text="foo", new_text="baz")
        self.assertFalse(r.ok)
        self.assertIn("matches 2 places", r.content)
        r, _ = call(self, "edit_file", ctx, path="a.txt", old_text="foo", new_text="baz", replace_all=True)
        self.assertTrue(r.ok)
        self.assertEqual((self.root / "a.txt").read_text(), "baz\nbar\nbaz\n")

    def test_not_found_gives_closest_match_hint(self):
        self.write("a.py", "def compute(total):\n    return total * 2\n")
        ctx = self.ctx()
        call(self, "read_file", ctx, path="a.py")
        r, _ = call(self, "edit_file", ctx, path="a.py", old_text="def compute(total):\n  return total * 3", new_text="x")
        self.assertFalse(r.ok)
        self.assertIn("Closest match", r.content)

    def test_trailing_whitespace_tolerated(self):
        self.write("a.txt", "keep  \nchange me   \nend\n")
        ctx = self.ctx()
        call(self, "read_file", ctx, path="a.txt")
        r, _ = call(self, "edit_file", ctx, path="a.txt", old_text="change me", new_text="changed")
        self.assertTrue(r.ok, r.content)
        self.assertIn("changed", (self.root / "a.txt").read_text())

    def test_crlf_is_preserved(self):
        (self.root / "w.txt").write_bytes(b"one\r\ntwo\r\nthree\r\n")
        ctx = self.ctx()
        call(self, "read_file", ctx, path="w.txt")
        r, _ = call(self, "edit_file", ctx, path="w.txt", old_text="one\ntwo", new_text="uno\ndos")
        self.assertTrue(r.ok, r.content)
        self.assertEqual((self.root / "w.txt").read_bytes(), b"uno\r\ndos\r\nthree\r\n")

    def test_syntax_error_warning(self):
        self.write("a.py", "x = 1\n")
        ctx = self.ctx()
        call(self, "read_file", ctx, path="a.py")
        r, _ = call(self, "edit_file", ctx, path="a.py", old_text="x = 1", new_text="x = (")
        self.assertTrue(r.ok)
        self.assertIn("syntax error", r.content)

    def test_multi_edit_is_atomic(self):
        self.write("a.txt", "alpha\nbeta\n")
        ctx = self.ctx()
        call(self, "read_file", ctx, path="a.txt")
        r, _ = call(self, "multi_edit", ctx, path="a.txt", edits=[
            {"old_text": "alpha", "new_text": "A"}, {"old_text": "MISSING", "new_text": "B"}])
        self.assertFalse(r.ok)
        self.assertIn("Edit #2", r.content)
        self.assertEqual((self.root / "a.txt").read_text(), "alpha\nbeta\n")
        r, _ = call(self, "multi_edit", ctx, path="a.txt", edits=[
            {"old_text": "alpha", "new_text": "A"}, {"old_text": "beta", "new_text": "B"}])
        self.assertTrue(r.ok)
        self.assertEqual((self.root / "a.txt").read_text(), "A\nB\n")

    def test_write_file_new_and_overwrite_guard(self):
        r, _ = call(self, "write_file", path="pkg/new.py", content="print(1)\n")
        self.assertTrue(r.ok)
        self.assertTrue(r.meta["created"])
        ctx = self.ctx()
        r, _ = call(self, "write_file", ctx, path="pkg/new.py", content="print(2)\n")
        self.assertFalse(r.ok)
        self.assertIn("not read", r.content)

    def test_writes_to_outside_paths_fail(self):
        r, _ = call(self, "write_file", path="../evil.txt", content="x")
        self.assertFalse(r.ok)
        self.assertFalse((self._tmp / "evil.txt").exists())

    def test_no_temp_files_left_behind(self):
        call(self, "write_file", path="a.txt", content="hi")
        self.assertEqual([p.name for p in self.root.iterdir()], ["a.txt"])


class PatchTests(TempCase):
    def test_apply_patch_modifies_and_creates(self):
        self.write("src/a.py", "def f():\n    return 1\n")
        patch = ("--- a/src/a.py\n+++ b/src/a.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
                 "--- /dev/null\n+++ b/src/new.py\n@@ -0,0 +1,2 @@\n+X = 1\n+Y = 2\n")
        r, _ = call(self, "apply_patch", patch=patch)
        self.assertTrue(r.ok, r.content)
        self.assertEqual((self.root / "src/a.py").read_text(), "def f():\n    return 2\n")
        self.assertEqual((self.root / "src/new.py").read_text(), "X = 1\nY = 2\n")

    def test_bad_patch_changes_nothing_and_wrong_counts_are_tolerated(self):
        self.write("a.txt", "one\ntwo\n")
        bad = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n nope\n-two\n+TWO\n"
        r, _ = call(self, "apply_patch", patch=bad)
        self.assertFalse(r.ok)
        self.assertEqual((self.root / "a.txt").read_text(), "one\ntwo\n")
        miscounted = "--- a/a.txt\n+++ b/a.txt\n@@ -1,9 +1,9 @@\n one\n-two\n+TWO\n"
        r, _ = call(self, "apply_patch", patch=miscounted)
        self.assertTrue(r.ok, r.content)
        self.assertEqual((self.root / "a.txt").read_text(), "one\nTWO\n")

    def test_patch_cannot_escape_workspace_or_touch_git(self):
        for target in ("../x.txt", ".git/config"):
            patch = f"--- /dev/null\n+++ b/{target}\n@@ -0,0 +1 @@\n+x\n"
            r, _ = call(self, "apply_patch", patch=patch)
            self.assertFalse(r.ok)
        self.assertFalse((self._tmp / "x.txt").exists())

    def test_patch_inside_parent_git_repo_still_works(self):
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self._tmp)
        self.write("a.txt", "x\n")
        patch = "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-x\n+y\n"
        r, _ = call(self, "apply_patch", patch=patch)
        self.assertTrue(r.ok, r.content)
        self.assertEqual((self.root / "a.txt").read_text(), "y\n")


class SearchTests(TempCase):
    def setUp(self):
        super().setUp()
        self.write(".gitignore", "build/\n*.log\n")
        self.write("src/app.py", "import os\n\nclass App:\n    def run(self):\n        return 'TODO fix'\n\ndef main():\n    pass\n")
        self.write("src/util.js", "export function helper() {}\nexport const arrow = (x) => x\n")
        self.write("build/out.py", "TODO ignored\n")
        self.write("debug.log", "TODO ignored\n")
        self.write("node_modules/pkg/index.js", "TODO ignored\n")
        self.write("README.md", "# Title\nTODO docs\n")

    def test_grep_respects_ignores_and_filters(self):
        r, _ = call(self, "grep", pattern="TODO")
        self.assertTrue(r.ok)
        self.assertIn("src/app.py", r.content)
        self.assertIn("README.md", r.content)
        for ignored in ("build/", "debug.log", "node_modules"):
            self.assertNotIn(ignored, r.content)
        r, _ = call(self, "grep", pattern="todo", case_insensitive=True, glob="*.py", output_mode="files")
        self.assertEqual(r.content.strip(), "src/app.py")

    def test_grep_bad_regex_is_a_clear_error(self):
        r, _ = call(self, "grep", pattern="(unclosed")
        self.assertFalse(r.ok)
        self.assertIn("Invalid regular expression", r.content)

    def test_grep_context_and_cap(self):
        r, _ = call(self, "grep", pattern="class App", context=1, path="src")
        self.assertIn("src/app.py-2-", r.content)
        self.write("big.txt", "hit\n" * 500)
        r, _ = call(self, "grep", pattern="hit", max_results=10)
        self.assertIn("truncated", r.content)

    def test_glob(self):
        r, _ = call(self, "glob", pattern="*.py")
        self.assertEqual(r.content.strip(), "src/app.py")
        r, _ = call(self, "glob", pattern="src/**/*.js")
        self.assertEqual(r.content.strip(), "src/util.js")

    def test_repo_map_and_symbol_index_stay_fresh_after_edits(self):
        r, ctx = call(self, "repo_map")
        self.assertIn("class App: run", r.content)
        self.assertIn("src/util.js", r.content)
        self.assertNotIn("node_modules", r.content)
        r, _ = call(self, "find_symbol", ctx, name="main")
        self.assertIn("src/app.py:7", r.content)
        # edit the file; the index must notice (v0 cached forever)
        (self.root / "src/app.py").write_text("def brand_new():\n    pass\n")
        import os, time
        os.utime(self.root / "src/app.py", (time.time() + 5, time.time() + 5))
        r, _ = call(self, "find_symbol", ctx, name="brand_new")
        self.assertIn("src/app.py:1", r.content)
        r, _ = call(self, "find_symbol", ctx, name="main")
        self.assertIn("No matching", r.content)

    def test_list_dir_hides_ignored(self):
        r, _ = call(self, "list_dir")
        self.assertIn("src/", r.content)
        self.assertNotIn("node_modules", r.content)
        self.assertNotIn("debug.log", r.content)


class TodoGitTests(TempCase):
    def test_todo_updates_session_and_emits(self):
        ctx = self.ctx()
        seen = []
        ctx.events.subscribe(seen.append)

        class S:
            todos = []

        ctx.session = S()
        r, _ = call(self, "todo_write", ctx, todos=[{"content": "a", "status": "completed"}, {"content": "b", "status": "in_progress"}])
        self.assertIn("1/2", r.content)
        self.assertEqual(len(ctx.session.todos), 2)
        self.assertEqual(seen[0]["type"], "todos_updated")

    def test_git_tools(self):
        import subprocess
        self.assertIn("not a git", call(self, "git_status")[0].content)
        subprocess.run(["git", "init", "-q"], cwd=self.root)
        self.write("a.txt", "x\n")
        self.assertIn("a.txt", call(self, "git_status")[0].content)


class FriendlyMissingDirTests(TempCase):
    def test_list_missing_dir_explains_write_file_creates_parents(self):
        r, _ = call(self, "list_dir", path="target")
        self.assertFalse(r.ok)
        self.assertIn("does not exist yet", r.content)
        self.assertIn("no mkdir needed", r.content)
        self.write("f.txt", "x")
        self.assertIn("is a file", call(self, "list_dir", path="f.txt")[0].content)
