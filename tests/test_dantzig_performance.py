"""Check failure accounting and completion-time TTS99 for published profiles."""

import math

import pytest

from scripts.plot_dantzig_performance import METHODS, performance_tables


def example_runs():
    return [{"case": "column", "cstr_size": "", "budget": 16, "seed": seed,
             "method": method, "lookup_target_hit": hit, "estimated_total_s": seconds}
            for seed, values in enumerate(((10., 20., .1, 30.), (30., 40., .2, 50.)))
            for method, seconds, hit in zip(METHODS, values,
                                           (True, seed == 0, False, False))]


def test_profiles_ignore_fast_failed_methods_and_tts_uses_all_times():
    ratios, summary = performance_tables(example_runs())
    assert next(r for r in ratios if r["seed"] == 0 and r["method"] == "rbfopt")["time_ratio"] == 2
    assert all(math.isinf(r["time_ratio"]) for r in ratios if not r["lookup_target_hit"])
    rows = {r["method"]: r for r in summary}
    assert rows["dsda"]["tts99_s"] == 20
    assert rows["rbfopt"]["median_completion_s"] == 30
    assert rows["rbfopt"]["runs_99"] == 7
    assert rows["rbfopt"]["tts99_s"] == 210
    assert math.isinf(rows["bam"]["tts99_s"])


def test_all_failed_starts_stay_in_denominator_and_pairing_is_required():
    runs = example_runs()
    for row in runs:
        if row["seed"] == 1:
            row["lookup_target_hit"] = False
    ratios, summary = performance_tables(runs)
    assert len(ratios) == 8 and all(r["runs"] == 2 for r in summary)
    assert all(math.isinf(r["time_ratio"]) for r in ratios if r["seed"] == 1)
    assert next(r for r in summary if r["method"] == "dsda")["hit_rate"] == .5
    with pytest.raises(ValueError, match="paired seed"):
        performance_tables(runs[:-1])


def test_current_profiles_use_all_nine_panels_and_match_published_costs():
    from scripts.plot_dantzig_cost_breakdown import load_runs
    from scripts.plot_dantzig_performance import PANELS
    runs, _, _, _, _ = load_runs(PANELS)
    ratios, summary = performance_tables(runs)
    assert len(ratios) == 356 and len(summary) == 36
    assert sum(math.isinf(r["tts99_s"]) for r in summary) == 2
    column_bam = next(r for r in summary if r["case"] == "column" and r["method"] == "bam")
    assert column_bam["target_hits"] == 0 and column_bam["runs"] == 9
    dynamic_dsda = next(r for r in summary if r["case"] == "dynamic" and r["budget"] == 50 and r["method"] == "dsda")
    assert dynamic_dsda["target_hits"] == 10
    assert dynamic_dsda["tts99_s"] == pytest.approx(26.6937, abs=.0001)


def test_full_benchmark_includes_all_solvers_and_keeps_attainment_and_limits():
    from collections import Counter
    from scripts.plot_dantzig_performance import full_benchmark
    rows = full_benchmark()
    assert len(rows) == 81
    assert Counter(r["family"] for r in rows) == {"DFO": 36, "GDPopt": 27, "MINLP": 18}
    assert all(r["runs"] == 1 for r in rows if r["family"] != "DFO")
    loa = next(r for r in rows if r["case"] == "cstr" and r["cstr_size"] == "15" and r["method"] == "loa")
    # This validated incumbent is better than the historical lookup target.
    assert loa["target_attained"] == 1 and loa["final_objective"] < loa["target_value"]
    assert loa["time_limits"] == 1
    assert sum(r["time_limits"] for r in rows) == 23
    assert sum(r["bound_conflicts"] for r in rows) == 5
