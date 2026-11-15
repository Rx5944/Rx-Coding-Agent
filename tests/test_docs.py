from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "docs/LEARNING.md").read_text()


class LearningGuideTests(unittest.TestCase):
    """The guide is only useful while it is true: every pointer must resolve."""

    def test_every_file_and_symbol_pointer_exists(self):
        pointers = set(re.findall(r"`((?:src/rx_agent|tests|scripts|docs)/[\w./]+?\.(?:py|js|css|md))(?:::([\w_]+))?`", DOC))
        short = set(re.findall(r"`((?:core|llm|tools|permissions|sandbox|workspace|server|evals|web)/[\w/]+\.(?:py|js))::(\w+)`", DOC))
        short |= set(re.findall(r"`((?:snapshots|verify|events|config)\.py)::(\w+)`", DOC))
        self.assertGreater(len(pointers) + len(short), 50, "the guide should stay rich in code pointers")
        missing = []
        for path, symbol in sorted(pointers):
            f = ROOT / path
            if not f.exists():
                missing.append(f"{path} (file missing)")
            elif symbol and symbol not in f.read_text():
                missing.append(f"{path}::{symbol}")
        self.assertEqual(missing, [])

    def test_bare_symbol_pointers_after_a_file_resolve(self):
        # forms like `core/loop.py::_prepare` written relative to src/rx_agent
        rel = set(re.findall(r"`((?:core|llm|tools|permissions|sandbox|workspace|server|evals|web)/[\w/]+\.(?:py|js))::(\w+)`", DOC))
        bad = [f"{p}::{s}" for p, s in sorted(rel) if s not in (ROOT / "src/rx_agent" / p).read_text()]
        self.assertEqual(bad, [])
        top = set(re.findall(r"`((?:snapshots|verify|events|config)\.py)::(\w+)`", DOC))
        bad = [f"{p}::{s}" for p, s in sorted(top) if s not in (ROOT / "src/rx_agent" / p).read_text()]
        self.assertEqual(bad, [])

    def test_documented_tool_count_and_bug_guards_are_real(self):
        from rx_agent.tools import default_registry

        self.assertEqual(len(default_registry().names()), 16)
        self.assertIn("16 tools", DOC.replace("(16)", "16 tools"))
        for ref in re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", DOC):
            self.assertIn(ref[1], (ROOT / ref[0]).read_text(), ref)


class TourTests(unittest.TestCase):
    def test_tour_runs_and_teaches_the_key_moments(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/tour.py")], capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        for needle in ("CHAPTER 8", "[APPROVAL REQUEST] edit calc.py", "missing required argument 'path'",
                       "Blocked:", "verification recorded] ok=True", "DANGEROUS echo", "after undo:", "Tour complete"):
            self.assertIn(needle, out)
        self.assertIn("passed=True", out)
