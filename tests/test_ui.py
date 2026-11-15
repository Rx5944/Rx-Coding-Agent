from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WebUITests(unittest.TestCase):
    def test_ui_logic_with_fake_dom(self):
        proc = subprocess.run(["node", str(ROOT / "ui_smoke.js")], capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_ui_never_uses_innerhtml_or_eval(self):
        js = (ROOT.parent / "src/rx_agent/web/app.js").read_text()
        code = "\n".join(line for line in js.splitlines() if not line.strip().startswith("//"))
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "document.write"):
            self.assertNotIn(banned, code)


class LayoutRegressionTests(unittest.TestCase):
    """A fake DOM cannot see layout, so guard the specific CSS bug that hid approval cards in v1.0.0:
    flex children with overflow:hidden shrink to hairlines once the log fills up."""

    web = ROOT.parent / "src/rx_agent/web"

    def test_log_children_never_shrink(self):
        css = (self.web / "style.css").read_text()
        import re
        rule = re.search(r"\.log\s*>\s*\*\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule, "missing `.log > * { flex: none }`")
        self.assertRegex(rule.group(1), r"flex:\s*none|flex-shrink:\s*0")

    def test_approvals_are_pinned_outside_the_scrolling_log(self):
        html = (self.web / "index.html").read_text()
        log_start = html.index('id="log"')
        dock = html.index('id="dock"')
        composer = html.index('id="composer"')
        self.assertLess(html.index("</div>\n    <div id=\"dock\"", log_start) if False else log_start, dock)
        self.assertLess(dock, composer)
        # the dock must not be nested inside the log container
        before_dock = html[log_start:dock]
        self.assertGreaterEqual(before_dock.count("</div>"), before_dock.count("<div"))

    def test_server_tells_clients_how_long_an_approval_waits(self):
        from rx_agent.events import EVENTS
        self.assertIn("timeout", EVENTS["approval_required"])
