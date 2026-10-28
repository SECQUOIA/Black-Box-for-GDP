"""Data-only regression and rejection tests for publication adoption."""

import copy
import unittest
from collections import Counter

from review_comparison import dsda_publication as d


class PublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.costs, cls.jobs = d.load_inputs()
        cls.records, cls.events, cls.pairs = d.overlay(cls.base, cls.costs, cls.jobs)
        cls.groups, cls.cover, cls.summary = d.summarize(cls.records, cls.events)

    def test_non_dsda_records_unchanged(self):
        self.assertEqual(
            [r for r in self.base if r["method"] != "dsda"],
            [r for r in self.records if r["method"] != "dsda"],
        )

    def test_missing_and_duplicate_pair_rejected(self):
        for jobs in [self.jobs[:-1], self.jobs[:-1] + [self.jobs[0]]]:
            with (
                self.subTest(length=len(jobs)),
                self.assertRaisesRegex(ValueError, "pairing"),
            ):
                d.overlay(self.base, self.costs, jobs)

    def test_response_corruption_rejected(self):
        jobs = list(self.jobs)
        first = copy.deepcopy(jobs[0])
        first[2][0]["raw_objective"] += 1
        jobs[0] = first
        with self.assertRaisesRegex(ValueError, "response mismatch"):
            d.overlay(self.base, self.costs, jobs)

    def test_budget_and_initial_order_rejected(self):
        jobs = list(self.jobs)
        first = copy.deepcopy(jobs[0])
        first[2][0]["point"], first[2][1]["point"] = (
            first[2][1]["point"],
            first[2][0]["point"],
        )
        jobs[0] = first
        with self.assertRaisesRegex(ValueError, "initial design"):
            d.overlay(self.base, self.costs, jobs)

    def test_success_and_coverage(self):
        grid = [
            r for r in self.records if r["scope"] == "grid" and r["method"] == "dsda"
        ]
        self.assertEqual(
            [sum(r["hit"] for r in grid if r["budget"] == b) for b in d.m.BUDGETS],
            [13, 74, 88, 98, 101],
        )
        self.assertEqual(sum(r["evaluations"] for r in grid), 37253)
        process = [
            r for r in self.records if r["scope"] == "process" and r["method"] == "dsda"
        ]
        self.assertEqual(
            (
                len(process),
                sum(r["hit"] for r in process),
                sum(r["evaluations"] for r in process),
            ),
            (140, 74, 2441),
        )
        self.assertEqual(
            sum(r["primary_callbacks"] for r in self.cover),
            self.summary["process_callbacks"],
        )
        self.assertTrue(
            all(
                p["old_hit"] == p["new_hit"]
                and p["old_first_hit"] == p["new_first_hit"]
                for p in self.pairs
                if p["scope"] == "process"
            )
        )

    def test_all_callbacks_charge_cost_including_repeats(self):
        counters = Counter(
            (e["scope"], e["case"], e["budget"], e["seed"]) for e in self.events
        )
        for r in self.records:
            if r["method"] == "dsda":
                self.assertEqual(
                    r["evaluations"],
                    counters[r["scope"], r["case"], r["budget"], r["seed"]],
                )
                self.assertAlmostEqual(
                    r["total_s"], r["point_cost_s"] + r["search_s"] + r["prep_s"]
                )
        self.assertTrue(
            any(e["accepted"] is False and e["point_cost_s"] > 0 for e in self.events)
        )

    def test_grouped_grid_and_separate_process_pairing(self):
        pairs = d.paired_grid(self.groups, [100])
        dsda = next(p for p in pairs if p["new"] == "dsda")
        self.assertAlmostEqual(dsda["difference"], (101 - 171) / 210)
        self.assertEqual((dsda["functions"], dsda["paired_seeds"]), (21, 10))
        process = [
            d.m.process_pair(self.groups, c, b, d.m.GEN, "dsda")
            for c, b in d.CONDITIONS
        ]
        self.assertEqual(len(process), 14)
        self.assertEqual(len([p for p in process if p["case"] == "dynamic"]), 6)

    def test_target_boundary_is_inclusive(self):
        self.assertTrue(d.hit(1e-5, 0))
        self.assertFalse(d.hit(1.00001e-5, 0))
        self.assertFalse(d.hit(None, 0))


if __name__ == "__main__":
    unittest.main()
