"""Verify the presentation update cannot silently change the retained evidence."""

import copy
import unittest

from review_comparison import grid_presentation as g


class GridPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.curves = g.load_inputs()

    def test_all_curves_match_archived_records(self):
        g.validate(self.rows, self.curves)
        self.assertEqual(len(self.rows), 6300)
        self.assertEqual(len(self.curves), 30)

    def test_missing_and_duplicate_runs_are_rejected(self):
        for rows in [self.rows[1:], self.rows + [self.rows[0]]]:
            with self.assertRaisesRegex(ValueError, "Missing, duplicate"):
                g.validate(rows, self.curves)

    def test_changed_curve_is_rejected(self):
        curves = copy.deepcopy(self.curves)
        curves[0]["y"][-1] += 1 / 210
        with self.assertRaisesRegex(ValueError, "Archived curve"):
            g.validate(self.rows, curves)

    def test_quartiles_include_misses_and_use_linear_interpolation(self):
        rows = [dict(method=m, budget=100, hit=i < 10,
                     total_s=float(i), point_cost_s=float(i), search_s=float(i))
                for m in g.m.GRID for i in range(210)]
        for r in g.cost_quartiles(rows):
            self.assertEqual((r["runs"], r["target_hits"]), (210, 10))
            self.assertEqual([r[f"total_s_q{q}"] for q in (25, 50, 75)],
                             [52.25, 104.5, 156.75])

    def test_actual_target_totals_and_medians(self):
        summary = g.cost_quartiles(self.rows)
        self.assertEqual([r["target_hits"] for r in summary], [101, 171, 147, 129, 45, 124])
        self.assertEqual([round(r["total_s_q50"], 2) for r in summary],
                         [24.08, 70.81, 64.42, 124.13, 60.51, 61.81])

    def test_table_has_six_rows_and_protected_brackets(self):
        text = g.table_rows(g.cost_quartiles(self.rows))
        self.assertEqual(len(text.splitlines()), 6)
        self.assertEqual(text.count(r"\\{["), 18)
        self.assertIn("0.0039", text)


if __name__ == "__main__":
    unittest.main()
