"""Verify completeness, retained misses, and target-count preservation."""

import copy
import unittest

from review_comparison import review_display as d


class ReviewDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = d.process_rows(d.grid.BASE)

    def test_current_process_population(self):
        self.assertEqual(len(self.rows), 700)
        summary = d.process_summary(self.rows)
        self.assertEqual(len(summary), 70)
        self.assertTrue(all(r["runs"] == 10 for r in summary))
        self.assertNotIn(d.m.SOL, {r["method"] for r in summary})

    def test_incomplete_and_duplicate_records_rejected(self):
        for rows in [self.rows[1:], self.rows + [self.rows[0]]]:
            with self.assertRaisesRegex(ValueError, "Missing, duplicate"):
                d.process_summary(rows)

    def test_nonfinite_and_negative_times_rejected(self):
        for value in [float("nan"), float("inf"), -.1]:
            rows = copy.deepcopy(self.rows)
            rows[0]["search_s"] = value
            with self.assertRaisesRegex(ValueError, "Invalid process search time"):
                d.process_summary(rows)

    def test_all_seeds_enter_quartiles_even_when_unsuccessful(self):
        rows = copy.deepcopy(self.rows)
        for r in rows:
            r["search_s"] = float(r["seed"])
            r["success"] = r["seed"] == 0
            r["category"] = "target_reached" if r["success"] else "execution_failure"
        for r in d.process_summary(rows):
            self.assertEqual(r["target_hits"], 1)
            self.assertEqual([r[f"search_q{q}_s"] for q in (25, 50, 75)], [2.25, 4.5, 6.75])

    def test_case_budgets_are_not_pooled(self):
        rows = copy.deepcopy(self.rows)
        for r in rows:
            r["search_s"] = float(r["budget"])
        for r in d.process_summary(rows):
            self.assertEqual(r["search_q50_s"], r["budget"])

    def test_cstr_target_totals_and_table_rows_preserved(self):
        summary = d.process_summary(self.rows)
        for method, expected in [(d.m.GEN, 45), ("dsda", 14)]:
            self.assertEqual(sum(r["target_hits"] for r in summary
                                 if r["case"].startswith("cstr_") and r["method"] == method), expected)
        table = d.process_table(summary)
        self.assertEqual(len(table.splitlines()), 14)
        self.assertEqual(table.count(r"\makecell{"), 70)
        self.assertEqual(table.count(r"\\{["), 70)

    def test_grid_percentages_and_ties_preserved(self):
        rows, _ = d.grid.load_inputs()
        table = d.grid_table(rows)
        self.assertIn(r"10 & 6.2 & 20.0 & \textbf{52.9} & 7.6 & 6.7 & \textbf{52.9}", table)
        self.assertIn(r"100 & 48.1 & \textbf{81.4} & 70.0 & 61.4 & 21.4 & 59.0", table)


if __name__ == "__main__":
    unittest.main()
