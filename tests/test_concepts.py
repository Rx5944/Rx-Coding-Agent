from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMOS = sorted((ROOT / "scripts/concepts").glob("[0-9][0-9]_*.py"))
DOC = (ROOT / "docs/CONCEPTS.md").read_text()
SRC = ROOT / "src/rx_agent"


class DemoTests(unittest.TestCase):
    def test_there_are_demos(self):
        self.assertGreaterEqual(len(DEMOS), 19)

    def test_every_demo_runs_and_states_its_lesson(self):
        for demo in DEMOS:
            with self.subTest(demo=demo.name):
                proc = subprocess.run([sys.executable, str(demo)], capture_output=True, text=True, timeout=60, cwd="/")
                self.assertEqual(proc.returncode, 0, proc.stdout[-500:] + proc.stderr[-800:])
                self.assertIn("LESSON:", proc.stdout)
                self.assertNotIn("Traceback", proc.stderr)


class CourseStructureTests(unittest.TestCase):
    def test_34_consecutive_concepts_each_with_a_check_and_an_answer(self):
        numbers = [int(n) for n in re.findall(r"^## (\d+)\. ", DOC, re.M)]
        self.assertEqual(numbers, list(range(1, 35)))
        body, answers = DOC.split("## Answers to", 1)
        self.assertEqual(body.count("**Check yourself.**"), 34)
        self.assertEqual([int(n) for n in re.findall(r"^\*\*(\d+)\.\*\* ", answers, re.M)], list(range(1, 35)))
        for label in ("**What.**", "**Why here.**", "**Pitfall.**"):
            self.assertEqual(body.count(label), 34, label)

    def test_every_referenced_demo_exists(self):
        names = set(re.findall(r"`(\d\d_\w+\.py)`", DOC))
        self.assertGreaterEqual(len(names), 18)
        self.assertEqual([n for n in sorted(names) if not (ROOT / "scripts/concepts" / n).exists()], [])
        unreferenced = [d.name for d in DEMOS if d.name not in names]
        self.assertEqual(unreferenced, [], "every demo should be taught in the course")

    def test_every_code_pointer_resolves(self):
        pattern = re.compile(r"`((?:core|llm|tools|permissions|sandbox|workspace|server|evals|web)/[\w/]+\.(?:py|js)|"
                             r"(?:snapshots|verify|events|config|util|errors)\.py|tests/[\w]+\.py)((?:::\w+)+)`")
        pointers = pattern.findall(DOC)
        self.assertGreater(len(pointers), 60)
        bad = []
        for path, chain in pointers:
            f = (ROOT / path) if path.startswith("tests/") else (SRC / path)
            if not f.exists():
                bad.append(f"{path} (missing)")
                continue
            text = f.read_text()
            for symbol in chain.split("::")[1:]:
                if symbol not in text:
                    bad.append(f"{path}::{symbol}")
        self.assertEqual(bad, [])

    def test_plain_file_references_exist(self):
        for ref in set(re.findall(r"`((?:docs|scripts)/[\w./]+\.(?:md|py))`", DOC)):
            self.assertTrue((ROOT / ref).exists(), ref)
