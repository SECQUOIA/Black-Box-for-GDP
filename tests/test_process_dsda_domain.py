"""Source-only DSDA fairness regression tests extracted from Benchmark.

Historical archive, publication selection, and recovery checks stay on Benchmark.
No process NLP solver or other DFO optimizer is invoked.
"""
import math
import unittest
from unittest.mock import patch

from case_studies.dsda_domain import box_membership, rank_observed_starts
from grid_dsda import dsda_from_csv, get_neighbors
from instrumentation import TrackedObjective

class MembershipOnly(dict):
    def __getitem__(self, key):
        raise AssertionError("Uncharged dictionary value access")

    def get(self, *args):
        raise AssertionError("Uncharged dictionary value access")

    def values(self):
        raise AssertionError("Uncharged dictionary values access")

    def items(self):
        raise AssertionError("Uncharged dictionary items access")

def search(lower, upper, start, oracle, budget=100, initial_value=None):
    tracked = TrackedObjective(oracle)
    result = dsda_from_csv(
        "",
        start,
        diagonal=True,
        verbose=False,
        max_points_explored=budget,
        grid=MembershipOnly(box_membership(lower, upper)),
        tracked_objective=tracked,
        start_value=initial_value,
    )
    return tracked, result


class FairnessTests(unittest.TestCase):
    def test_boundaries_zero_and_one(self):
        for lower in (0, 1):
            domain = MembershipOnly(
                box_membership([lower, lower], [lower + 2, lower + 2])
            )
            for x, y in domain:
                expected = sorted(
                    (a, b)
                    for a in range(lower, lower + 3)
                    for b in range(lower, lower + 3)
                    if (a, b) != (x, y) and max(abs(a - x), abs(b - y)) == 1
                )
                self.assertEqual(get_neighbors((x, y), domain, True), expected)
                tracked, r = search(
                    [lower, lower],
                    [lower + 2, lower + 2],
                    (x, y),
                    lambda p: 1.0,
                    initial_value=1.0,
                )
                self.assertEqual(tracked.evaluation_points, expected)
                self.assertEqual(r["point_evaluations"], len(expected))

    def test_hidden_nan_consumes_callback(self):
        calls = []

        def oracle(p):
            calls.append(p)
            return math.nan if p == (0, 1) else 1.0

        tracked, result = search([0, 0], [2, 2], (1, 1), oracle, initial_value=0.0)
        self.assertEqual(len(calls), 8)
        self.assertIn((0, 1), calls)
        self.assertEqual(tracked.call_count, 8)
        self.assertEqual(result["best_point"], (1, 1))

    def test_three_dimensional_box(self):
        expected = [
            (a, b, c)
            for a in (1, 2, 3)
            for b in (1, 2, 3)
            for c in (1, 2, 3)
            if (a, b, c) != (2, 2, 2)
        ]
        d = MembershipOnly(box_membership([1] * 3, [3] * 3))
        self.assertEqual(get_neighbors((2, 2, 2), d, True), expected)
        tracked, _ = search(
            [1] * 3, [3] * 3, (2, 2, 2), lambda p: math.nan, initial_value=0.0
        )
        self.assertEqual(tracked.evaluation_points, expected)
        self.assertEqual(tracked.call_count, 26)

    def test_initialization_and_mid_neighborhood_caps(self):
        from case_studies.column_dsda import run_column_dsda
        from case_studies import column_case

        starts = [(14, 4), (12, 1), (9, 8)]
        for cap in (3, 4, 6):
            with patch(
                "case_studies.column_dsda.generate_lhc_starting_points",
                side_effect=AssertionError("Must use frozen points"),
            ):
                out = run_column_dsda(starting_points=starts, max_evaluations=cap)
            self.assertEqual(out["tracked_evals"], cap)
            self.assertEqual(out["starting_points"], starts)
            if cap == 4:
                self.assertEqual(out["run_result"]["explored_points"][1][0], (13, 3))
            observed = out["starting_point_values"] + (
                out["run_result"]["explored_points"] if out["run_result"] else []
            )
            self.assertIn(tuple(out["best_point"]), [p[0] for p in observed])
            self.assertEqual(
                column_case.column_objective(out["best_point"]), out["best_value"]
            )
        with patch(
            "case_studies.column_dsda.column_objective",
            side_effect=AssertionError("No callback permitted"),
        ):
            with self.assertRaisesRegex(ValueError, "entire initial design"):
                run_column_dsda(starting_points=starts, max_evaluations=2)

    def test_line_search_unsuccessful_and_true_boundary(self):
        # Neighborhood: (0,), (2,); line trial (3,) must be charged before rejection.
        tr, r = search(
            [0],
            [4],
            (1,),
            lambda p: math.nan if p == (3,) else -float(p[0]),
            initial_value=-1.0,
        )
        self.assertEqual(tr.evaluation_points[:3], [(0,), (2,), (3,)])
        self.assertEqual(r["history"][1]["line_search_points"][-1][2], "rejected")
        tr, r = search([0], [3], (1,), lambda p: -float(p[0]), initial_value=-1.0)
        self.assertNotIn((4,), tr.evaluation_points)
        self.assertIn(
            ((4,), None, "out_of_bounds"), r["history"][1]["line_search_points"]
        )

    def test_mid_line_search_cap(self):
        tr, r = search(
            [0], [10], (1,), lambda p: -float(p[0]), budget=3, initial_value=-1.0
        )
        self.assertEqual(tr.evaluation_points, [(0,), (2,), (3,)])
        self.assertEqual(r["best_point"], (3,))
        self.assertEqual(r["stop_reason"], "max_points_explored")

    def test_repeated_initial_calls_and_start_value_reuse(self):
        tr = TrackedObjective(lambda p: float(p[0]))
        p, v, _, obs = rank_observed_starts([(1,), (1,), (2,)], tr)
        self.assertEqual(tr.call_count, 3)
        r = dsda_from_csv(
            "",
            p,
            grid=MembershipOnly(box_membership([0], [3])),
            tracked_objective=tr,
            start_value=v,
            max_points_explored=1,
            verbose=False,
        )
        self.assertEqual(tr.evaluation_points, [(1,), (1,), (2,), (0,)])
        self.assertEqual(r["point_evaluations"], 1)
        tr, r = search([0], [3], (1,), lambda p: -float(p[0]), initial_value=-1.0)
        self.assertGreater(tr.call_count, tr.unique_evaluation_count)

    def test_initial_selection_uses_observations_only(self):
        from case_studies.cstr_dsda import choose_best_feasible_start

        p, v, _, _ = choose_best_feasible_start(
            [(1, 2), (2, 1), (2, 2)],
            TrackedObjective(lambda p: sum(p)),
            MembershipOnly(),
        )
        self.assertEqual((p, v), ((1, 2), 3))
        tr = TrackedObjective(lambda p: math.inf)
        with self.assertRaisesRegex(ValueError, "all observed responses unsuccessful"):
            rank_observed_starts([(1,), (2,), (3,)], tr)
        self.assertEqual(tr.call_count, 3)
