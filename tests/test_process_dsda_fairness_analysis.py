"""Accounting tests independent of measured runs."""

import math
import unittest
from process_dsda_fairness_analysis import join_costs, outcome_summary


class CostTests(unittest.TestCase):
    def test_same_coordinate_rejection_reuse_prefers_cstr30_and_records_source(self):
        spec = {"case_name": "cstr", "grid_size": 20, "max_evaluations": 29,
                "seed": 4, "job_id": "cstr20"}
        events = [{"point": [6, 7], "objective_wall_s": 0.01, "lookup_successful": False}] * 2
        costs = {("cstr", str(size), (6, 7)): {
            "point_evaluation_s": duration, "point_outcome": "preprocessing_infeasible",
            "point_source": str(size), "point_source_sha256": "hash"}
            for size, duration in [(15, 0.4), (25, 0.3), (30, 0.2)]}
        summary, ledger, missing = join_costs(spec, events, costs, 0.1, 0.0)
        self.assertEqual(missing, [])
        self.assertEqual(summary["reused_cstr_rejection_callbacks"], 2)
        self.assertAlmostEqual(summary["estimated_total_s"], 0.48)
        self.assertEqual(ledger[0]["cstr_size"], "20")
        self.assertEqual(ledger[0]["point_cost_cstr_size"], "30")
        del costs["cstr", "30", (6, 7)]
        self.assertEqual(join_costs(spec, events, costs, 0.1, 0)[1][0]["point_cost_cstr_size"], "25")
        for value in costs.values():
            value["point_outcome"] = "accepted"
        self.assertIsNone(join_costs(spec, events, costs, 0.1, 0)[0]["estimated_total_s"])

    def test_exact_size_repeats_and_missing_costs(self):
        spec = {
            "case_name": "cstr",
            "grid_size": 10,
            "max_evaluations": 15,
            "seed": 0,
            "job_id": "sample",
        }
        events = [{"point": [1, 2], "objective_wall_s": 0.1}] * 2
        costs = {
            ("cstr", "10", (1, 2)): {
                "point_evaluation_s": 2.0,
                "point_outcome": "preprocessing_infeasible",
                "point_source": "x",
                "point_source_sha256": "hash",
            }
        }
        row, ledger, missing = join_costs(spec, events, costs, 1.0, 0.0)
        self.assertEqual(row["estimated_total_s"], 4.8)
        self.assertEqual(row["unaccepted_nlp_s"], 4.0)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(missing, [])
        spec["grid_size"] = 5
        row, _, missing = join_costs(spec, events, costs, 1.0, 0.0)
        self.assertIsNone(row["estimated_total_s"])
        self.assertIsNone(row["accepted_nlp_s"])
        self.assertEqual(len(missing), 2)

    def test_incomplete_group_has_no_subset_median(self):
        template = {
            "case": "column",
            "cstr_size": "",
            "budget": 16,
            "method": "dsda",
            "lookup_target_hit": True,
            "search_overhead_s": 1.0,
            "accepted_nlp_s": 1.0,
            "unaccepted_nlp_s": 0.0,
            "dynamic_preparation_s": 0.0,
        }
        rows = [
            dict(template, estimated_total_s=2.0),
            dict(template, estimated_total_s=None),
        ]
        s = outcome_summary(rows)[0]
        self.assertEqual(s["target_hits"], 2)
        self.assertEqual(s["timed_runs"], 1)
        self.assertIsNone(s["median_completion_s"])
        self.assertIsNone(s["tts99_s"])
        self.assertIsNone(s["accepted_nlp_pct"])

    def test_all_failures_stay_in_denominator_and_time_median(self):
        rows = [
            {
                "case": "dynamic",
                "cstr_size": "",
                "budget": 12,
                "method": "dsda",
                "lookup_target_hit": False,
                "estimated_total_s": t,
                "search_overhead_s": t - 1.0,
                "accepted_nlp_s": 0.0,
                "unaccepted_nlp_s": 0.5,
                "dynamic_preparation_s": 0.5,
            }
            for t in (2.0, 4.0)
        ]
        s = outcome_summary(rows, expected_runs=2)[0]
        self.assertEqual(s["runs"], 2)
        self.assertEqual(s["median_completion_s"], 3.0)
        self.assertEqual(s["tts99_s"], math.inf)
        self.assertAlmostEqual(sum(s[k] for k in s if k.endswith("_pct")), 100.0)

    def test_missing_seed_suppresses_aggregate_even_with_all_observed_costs(self):
        rows = [{"case": "cstr", "cstr_size": "15", "budget": 22,
                 "method": "dsda", "lookup_target_hit": False,
                 "estimated_total_s": 1.0}] * 9
        summary = outcome_summary(rows)[0]
        self.assertFalse(summary["matrix_complete"])
        self.assertFalse(summary["cost_complete"])
        for key in ("hit_rate", "runs_99", "median_completion_s", "tts99_s"):
            self.assertIsNone(summary[key])


if __name__ == "__main__":
    unittest.main()
