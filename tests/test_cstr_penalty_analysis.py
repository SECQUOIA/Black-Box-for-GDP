"""Independent audit regressions; no optimizer or NLP calls."""

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "penalty_analysis", ROOT / "experiments/cstr_penalty_1e6/analyze.py"
)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class PenaltyAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = analysis.Archive(ROOT / analysis.RETURN)
        cls.job = cls.archive.read("reproduction/plan.json")[1]
        cls.spec = cls.job["spec"]
        cls.events = cls.archive.events(
            "jobs/" + cls.spec["job_id"] + "/callbacks.jsonl"
        )
        cls.lookup, cls.costs, cls.target, _ = analysis.input_maps(cls.archive, 5)
        cls.result = cls.archive.read("jobs/" + cls.spec["job_id"] + "/result.json")

    @classmethod
    def tearDownClass(cls):
        cls.archive.z.close()

    def test_returned_trace_and_terminal_target(self):
        analysis.audit_events(self.spec, self.events, self.lookup, True)
        events = copy.deepcopy(self.events)
        # Unit fixture: only the final observation is accepted and reaches target.
        for e in events[:-1]:
            e.update(accepted=False, raw_objective=None)
        events[-1].update(accepted=True, raw_objective=self.target, point=[5, 5])
        result, _ = analysis.measure(
            self.spec, events, self.result, self.costs, self.target
        )
        self.assertTrue(result["target_hit"])
        self.assertEqual(result["first_target_evaluation"], self.spec["budget"])

    def test_mutated_response_acceptance_status_and_order_rejected(self):
        for index, key, value in [
            (0, "method_value", 7),
            (0, "accepted", True),
            (0, "evaluation_state", "accepted"),
            (1, "raw_objective", 1e6),
            (0, "point", [2, 1]),
            (0, "penalty_applied", False),
            (-1, "value_returned_to_optimizer", True),
        ]:
            with self.subTest(key=key):
                events = copy.deepcopy(self.events)
                events[index][key] = value
                with self.assertRaises(ValueError):
                    analysis.audit_events(self.spec, events, self.lookup, True)

    def test_raw_nlp_status_mutation_rejected(self):
        events = copy.deepcopy(self.events)
        events[0]["source_row"]["status"] = "accepted"
        with self.assertRaises(ValueError):
            analysis.audit_events(self.spec, events, self.lookup, True)

    def test_overbudget_rejected(self):
        with self.assertRaises(ValueError):
            analysis.audit_events(
                self.spec, self.events + [self.events[-1]], self.lookup, True
            )

    def test_failed_execution_excludes_observed_target(self):
        result, _ = analysis.measure(
            self.spec,
            self.events,
            {"status": "execution_failed", "dfo_wall_s": 1},
            self.costs,
            self.target,
        )
        self.assertTrue(result["target_observed_even_if_failed"])
        self.assertFalse(result["target_hit"])

    def test_missing_cost_stays_unknown_and_repeats_charged(self):
        result, _ = analysis.measure(
            self.spec, self.events, self.result, {}, self.target
        )
        self.assertIsNone(result["estimated_completion_s"])
        self.assertEqual(len(result["missing_cost_keys"]), len(self.events))
        twice = self.events + self.events
        original, _ = analysis.measure(
            self.spec, self.events, self.result, self.costs, self.target
        )
        repeated, _ = analysis.measure(
            self.spec,
            twice,
            {"status": "completed", "dfo_wall_s": 1},
            self.costs,
            self.target,
        )
        self.assertAlmostEqual(
            repeated["point_cost_sum_s"], 2 * original["point_cost_sum_s"]
        )

    def test_full_archive_replay_matches_preserved_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "analysis"
            groups, methods, _ = analysis.analyze(
                ROOT / analysis.RETURN, ROOT / analysis.BUNDLE, output
            )
            self.assertEqual(
                [(m["baseline_hits"], m["penalty_hits"]) for m in methods],
                [(15, 15), (56, 45)],
            )
            self.assertEqual([m["identical_paths"] for m in methods], [60, 30])
            self.assertEqual(len(groups), 12)
            saved = ROOT / "results/cstr_penalty_1e6_analysis_20261022"
            # Numeric times can differ at floating summation roundoff across Python versions.
            for name in (
                "rbfopt_coordinates.csv",
                "callback_paths.csv",
                "runtime_audit.csv",
            ):
                self.assertEqual(
                    (output / name).read_bytes(), (saved / name).read_bytes()
                )


if __name__ == "__main__":
    unittest.main()
