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


def test_profiles_use_absolute_seconds_and_tts_uses_all_times():
    profiles, summary = performance_tables(example_runs())
    assert next(r for r in profiles if r["seed"] == 0 and r["method"] == "rbfopt")["profile_completion_s"] == 20
    assert all(math.isinf(r["profile_completion_s"]) for r in profiles if not r["lookup_target_hit"])
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
    profiles, summary = performance_tables(runs)
    assert len(profiles) == 8 and all(r["runs"] == 2 for r in summary)
    assert all(math.isinf(r["profile_completion_s"]) for r in profiles if r["seed"] == 1)
    assert next(r for r in summary if r["method"] == "dsda")["hit_rate"] == .5
    with pytest.raises(ValueError, match="paired seed"):
        performance_tables(runs[:-1])


def test_current_profiles_use_all_nine_panels_and_match_published_costs():
    from scripts.plot_dantzig_cost_breakdown import load_runs
    from scripts.plot_dantzig_performance import PANELS
    runs, _, _, _, _ = load_runs(PANELS)
    profiles, summary = performance_tables(runs)
    assert len(profiles) == 356 and len(summary) == 36
    assert sum(math.isinf(r["tts99_s"]) for r in summary) == 2
    column_bam = next(r for r in summary if r["case"] == "column" and r["method"] == "bam")
    assert column_bam["target_hits"] == 0 and column_bam["runs"] == 9
    dynamic_dsda = next(r for r in summary if r["case"] == "dynamic" and r["budget"] == 50 and r["method"] == "dsda")
    assert dynamic_dsda["target_hits"] == 10
    assert dynamic_dsda["tts99_s"] == pytest.approx(26.6937, abs=.0001)


def test_plotted_steps_use_seconds_and_keep_failures_in_denominator():
    import matplotlib.pyplot as plt
    from scripts.plot_dantzig_performance import PANELS, plot_profiles
    # Give every panel the same two-seed fixture to check the plotted ECDF itself.
    runs = [{**row, "case": panel[0], "cstr_size": panel[1], "budget": panel[2]}
            for panel in PANELS for row in example_runs()]
    profiles, _ = performance_tables(runs)
    fig = plot_profiles(profiles)
    try:
        for ax in fig.axes:
            dsda, rbfopt, bam, fmqa = ax.lines
            assert list(dsda.get_xdata())[1:-1] == [10., 30.]
            assert list(dsda.get_ydata()) == [0., .5, 1., 1.]
            assert list(rbfopt.get_xdata())[1:-1] == [20.]
            assert list(rbfopt.get_ydata()) == [0., .5, .5]
            assert all(y == 0 for line in (bam, fmqa) for y in line.get_ydata())
            assert ax.get_xlabel() == "Completion time (s, log scale)"
    finally:
        plt.close(fig)


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
