"""Check the NLP-solve figure inputs: enumeration counts and plotted runs."""

import unittest

from review_comparison import joint_process as base
from review_comparison import joint_process_main as main_figure
from review_comparison import joint_process_nlp as nlp


class JointProcessNlpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counts, _ = nlp.enumeration(base.ROOT)
        rows, _ = main_figure.load(base.ROOT)
        cls.selected = nlp.select(rows)

    def test_enumeration_counts(self):
        expected = {f"cstr_{n}": n * (n + 1) // 2 for n in (5, 10, 15, 20, 25, 30)}
        expected.update(column=36, small_batch=12, dynamic=37)
        self.assertEqual(self.counts, expected)

    def test_all_seeds_and_gdpopt_runs_plotted(self):
        self.assertEqual(len(self.selected), len(nlp.CONDITIONS) * (10 * 5 + 3))

    def test_ric_and_loa_match_enumeration_on_smaller_cstr(self):
        for case in ["cstr_5", "cstr_10", "cstr_15", "cstr_20"]:
            for method in ["ric", "loa"]:
                run = next(r for r in self.selected if r["case"] == case and r["method"] == method)
                self.assertEqual(int(run["nlp_calls"]), self.counts[case])

    def test_dfo_runs_never_exceed_budget(self):
        for r in self.selected:
            if r["family"] == "DFO":
                self.assertLessEqual(int(r["nlp_calls"]), r["panel_budget"])


if __name__ == "__main__":
    unittest.main()
