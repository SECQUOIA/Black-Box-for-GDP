"""Check publication records against independently retained analysis results."""

import math

import pytest

from review_comparison import manuscript as m


@pytest.fixture(scope="module")
def publication():
    return m.load()


def test_every_condition_matches_frozen_analysis(publication):
    rows, groups, terminals = publication
    original = m.read(m.BASE / "tables/condition_summary.csv")
    assert len(original) == len(groups)
    for r in original:
        key = r["scope"], r["case"], int(r["budget"]), r["method"]
        s = m.summarize(groups[key])
        assert s["n"] == int(r["completed_slots"]) == 10
        assert s["hits"] == int(r["target_reached"])
        assert s["median"] == pytest.approx(float(r["median_completion_s"]))
        if s["hits"]:
            assert s["tts"] == pytest.approx(float(r["empirical_tts99_s"]))
        else:
            assert math.isinf(s["tts"])
    assert len(rows) == 8190
    assert all(1 <= r["first_hit"] <= r["evaluations"] for r in rows if r["hit"])
    assert all(r["first_hit"] is None for r in rows if not r["hit"])
    assert all(r["method"] in (m.GEN, m.UNI) for r in terminals)


def test_primary_costs_include_all_outcomes_and_repeats(publication):
    rows, groups, _ = publication
    process = [r for r in rows if r["scope"] == "process" and r["method"] in m.PRIMARY]
    assert len(process) == 700
    assert sum(r["evaluations"] for r in process) == 16252
    assert sum(r["category"] == "execution_failed" for r in process) == 1
    assert sum(r["hit"] for r in process) == 326
    assert all(
        r["total_s"] == r["search_s"] + r["point_cost_s"] + r["prep_s"] for r in rows
    )
    assert all(r["prep_s"] > 0 for r in process if r["case"] == "dynamic")
    assert m.summarize(process)["tts"] is None
    for b in m.BUDGETS:
        for c in {r["case"] for r in rows if r["scope"] == "grid"}:
            if b == 10:
                a = {r["seed"]: r["hit"] for r in groups["grid", c, b, "bam"]}
                p = {r["seed"]: r["hit"] for r in groups["grid", c, b, m.PRE]}
                assert a == p


def test_paired_publication_matches_independent_fmqa_analysis(publication, tmp_path):
    rows, groups, _ = publication
    m.tables(rows, groups, tmp_path)
    paired = m.read(tmp_path / "paired_comparisons.csv")
    fmqa = {
        (
            r["scope"],
            int(r["budget"]),
            "all_functions" if r["scope"] == "grid" else r["case"],
        ): r
        for r in paired
        if r["new"] == "fmqa_sa" and r["reference"] == m.UNI
    }
    assert len(fmqa) == 19
    for r in m.read(m.BASE / "fmqa_uniform/paired_success.csv"):
        p = fmqa[r["scope"], int(r["budget"]), r["case"]]
        for a, b in [
            ("difference", "mean_paired_success_difference"),
            ("low", "descriptive_95_low"),
            ("high", "descriptive_95_high"),
        ]:
            assert float(p[a]) == pytest.approx(float(r[b]), abs=1e-14)
        assert int(p["problem_groups"]) == (21 if r["scope"] == "grid" else 1)
    intervals = (tmp_path / "process_intervals.tex").read_text()
    assert "0 [0.00, 0.31]" in intervals
    assert "10 [0.69, 1.00]" in intervals
    assert "5 [0.19, 0.81]" in intervals
