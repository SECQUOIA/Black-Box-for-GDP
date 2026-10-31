"""Check the seed-spread, tolerance, overhead, and GDPopt enumeration summaries."""

import unittest

from review_comparison import revision_diagnostics as d


class RevisionDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = d.load_runs()
        cls.spread = {(r["family"], r["method"]): r for r in d.spread_rows(cls.rows, d.references())}

    def test_exact_hits_match_published_counts(self):
        self.assertEqual(self.spread["cstr", "rbfopt_msrsm_genetic"]["exact"], 45)
        self.assertEqual(self.spread["cstr", "dsda"]["exact"], 14)
        self.assertEqual(sum(r["exact"] for (f, m), r in self.spread.items() if m == "fmqa_sa"), 42)

    def test_nomad_and_miso_counts_match_the_audited_return(self):
        self.assertEqual(self.spread["cstr", "miso"]["exact"], 43)
        self.assertEqual(self.spread["cstr", "nomad"]["exact"], 21)
        self.assertEqual(self.spread["column", "miso"]["exact"], 10)
        self.assertEqual(len([r for r in self.rows if r["scope"] == "grid" and r["search_s"] is None]), 21)

    def test_large_values_print_without_exponent(self):
        self.assertEqual(d.g3(1858.4), "1860")
        self.assertEqual(d.g3(98.44), "98.4")

    def test_relaxed_counts_are_monotone(self):
        for r in self.spread.values():
            counts = [r["exact"]] + [r[f"within_{t:g}"] for t in d.TOLERANCES] + [r["runs"]]
            self.assertEqual(counts, sorted(counts))

    def test_bam_cstr_near_misses(self):
        r = self.spread["cstr", "bam"]
        self.assertEqual((r["exact"], r["within_0.01"]), (18, 60))
        self.assertLess(r["max_miss_gap"], 0.007)

    def test_logic_based_methods_enumerate_admissible_configurations(self):
        rows = {(r["case"], r["method"]): r for r in d.enumeration_rows()}
        for r in rows.values():
            self.assertEqual(r["subproblems"], r["distinct_configurations"])
        for case in ["cstr_5", "cstr_10", "cstr_15", "cstr_20", "dynamic"]:
            for method in ["ric", "loa"]:
                r = rows[case, method]
                self.assertEqual(r["distinct_configurations"], r["admissible_configurations"])
        self.assertEqual(rows["cstr_25", "ric"]["distinct_configurations"], 325)


if __name__ == "__main__":
    unittest.main()
