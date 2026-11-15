from __future__ import annotations

from rx_agent.evals.runner import format_report, run_suite, validate_tasks
from rx_agent.evals.tasks import TASKS
from rx_agent.llm.mock import ScriptedLLM

from .helpers import TempCase, run


class EvalTests(TempCase):
    def test_every_task_fails_before_and_passes_with_reference_solution(self):
        self.assertEqual(validate_tasks(), [])

    def test_task_ids_unique_and_nonempty(self):
        ids = [t.id for t in TASKS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 8)

    def test_oracle_agent_passes_whole_suite_through_the_real_loop(self):
        report = run(run_suite(TASKS, self.settings(), oracle=True))
        failed = [r for r in report["tasks"] if not r["passed"]]
        self.assertEqual(failed, [], format_report(report))
        self.assertEqual(report["pass_rate"], 1.0)

    def test_a_do_nothing_agent_fails_everything(self):
        report = run(run_suite(TASKS[:3], self.settings(), llm_factory=lambda s: ScriptedLLM(["I did nothing."])))
        self.assertEqual(report["passed"], 0)
        self.assertIn("FAIL", format_report(report))
