"""Check the seven-method tables against the audited PR #56 return and the published values."""

import unittest

from review_comparison import seven_methods as sm


class SevenMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {}
        cls.rows = sm.load(sm.ROOT, cls.inputs)

    def test_grid_hits_at_full_budget(self):
        _, data = sm.grid_table(self.rows)
        hits = {r["method"]: r["hits"] for r in data if r["budget"] == 100}
        self.assertEqual((hits["miso"], hits["rbfopt_msrsm_genetic"], hits["nomad"], hits["dsda"]),
                         (181, 171, 126, 101))

    def test_completion_table_keeps_published_medians(self):
        _, data = sm.completion_table(self.rows, sm.enumeration(sm.ROOT, {}))
        median = {(r["case"], r["budget"], r["method"]): r["median_completion_s"] for r in data}
        self.assertAlmostEqual(median["column", 13, "dsda"], 35.44, places=2)
        self.assertAlmostEqual(median["dynamic", 50, "rbfopt_msrsm_genetic"], 65.14, places=2)
        self.assertAlmostEqual(median["dynamic", 50, "miso"], 195.36, places=2)

    def test_nomad_grid_costs_leave_out_crashed_runs(self):
        _, data = sm.grid_cost_table(self.rows)
        nomad = next(r for r in data if r["method"] == "nomad")
        self.assertEqual((nomad["runs"], nomad["timed_runs"], nomad["target_hits"]), (210, 189, 126))
        self.assertTrue(all(r["timed_runs"] == 210 for r in data if r["method"] != "nomad"))

    def test_exploratory_tests_match_the_runs(self):
        _, data = sm.exploratory_table(sm.ROOT, {}, self.rows)
        family = [r for r in data if r["family"] == "exploratory_70"]
        self.assertEqual(len(family), 70)
        self.assertAlmostEqual(min(r["p_holm_70"] for r in family), 0.546875)
        pooled = {(r["first"], r["second"]): (r["first_only"], r["second_only"])
                  for r in data if r["family"] == "pooled_descriptive"}
        self.assertEqual(pooled["miso", "rbfopt_msrsm_genetic"], (7, 9))
        self.assertEqual(pooled["nomad", "dsda"], (9, 2))

    def test_restarts_leave_target_hits_unchanged(self):
        tex = sm.restart_table(sm.ROOT, {})
        rows = [line.split(" & ") for line in tex.splitlines() if line.startswith("\\texttt{")]
        self.assertEqual(len(rows), 14)
        for i in (2, 3, 4):
            self.assertEqual(sum(int(r[i]) for r in rows), 74)

    def test_grid_rates_without_two_functions(self):
        rate = {(r["budget"], r["method"]): round(r["percent"], 1) for r in sm.grid_exclusions(self.rows)}
        self.assertEqual((rate[100, "miso"], rate[100, "nomad"], rate[100, "rbfopt_msrsm_genetic"]),
                         (84.7, 55.8, 79.5))


if __name__ == "__main__":
    unittest.main()
