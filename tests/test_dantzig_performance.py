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
    assert len(profiles) == 360 and len(summary) == 36
    assert sum(math.isinf(r["tts99_s"]) for r in summary) == 2
    column_bam = next(r for r in summary if r["case"] == "column" and r["method"] == "bam")
    assert column_bam["target_hits"] == 0 and column_bam["runs"] == 10
    dynamic_dsda = next(r for r in summary if r["case"] == "dynamic" and r["budget"] == 50 and r["method"] == "dsda")
    assert dynamic_dsda["target_hits"] == 10
    assert dynamic_dsda["tts99_s"] == pytest.approx(26.6937, abs=.0001)


def test_followup_replaces_small_batch_and_adds_paired_column_seed_without_changing_other_runs():
    from scripts.plot_dantzig_cost_breakdown import load_runs
    from scripts.plot_dantzig_performance import PANELS
    original = load_runs(PANELS, include_followup=False)[0]
    current, _, _, _, manifest = load_runs(PANELS)
    untouched = {r["job_id"]: r for r in original if r["case"] != "small_batch"}
    assert all(next(r for r in current if r["job_id"] == key) == value
               for key, value in untouched.items())
    for method, hits in zip(METHODS, (8, 5, 2, 7)):
        batch = [r for r in current if r["case"] == "small_batch" and r["method"] == method]
        assert len(batch) == 10 and {r["seed"] for r in batch} == set(range(10))
        assert all(r["job_id"].startswith("small_batch_full_B10_") for r in batch)
        assert sum(r["lookup_target_hit"] for r in batch) == hits
    for method, hits in zip(METHODS, (8, 5, 0, 5)):
        group = [r for r in current if r["case"] == "column" and r["method"] == method]
        assert len(group) == 10 and {r["seed"] for r in group} == set(range(1, 11))
        assert sum(r["lookup_target_hit"] for r in group) == hits
    selection = manifest["followup_selection"]
    assert len(selection["added_job_ids"]) == 44 and len(selection["replaced_job_ids"]) == 40
    assert not set(selection["replaced_job_ids"]) & {r["job_id"] for r in current}


def test_followup_uses_original_method_timer_and_charges_every_callback():
    import json
    from scripts.plot_dantzig_cost_breakdown import FOLLOWUP, followup_runs, read_csv
    raw = {r["job_id"]: r for r in read_csv(FOLLOWUP / "runs.csv")}
    ledger = json.loads((FOLLOWUP / "nlp_costs.json").read_text())
    rows, _ = followup_runs()
    for row in rows:
        events = [e for e in ledger["callbacks"] if e["job_id"] == row["job_id"]]
        measured = float(raw[row["job_id"]]["wall_time_s"])
        assert row["recorded_dfo_s"] == measured
        estimate = measured + math.fsum(e["point_evaluation_s"] - e["recorded_lookup_call_s"] for e in events)
        assert row["estimated_total_s"] == pytest.approx(estimate, rel=1e-12)
    dsda = next(r for r in rows if r["method"] == "dsda")
    events = [e for e in ledger["callbacks"] if e["job_id"] == dsda["job_id"]]
    assert len(events) == 16 and sum(e["repeated_point"] for e in events) == 3
    fmqa = next(r for r in rows if r["method"] == "fmqa_sa")
    extra = [e for e in ledger["callbacks"] if e["job_id"] == fmqa["job_id"] and e["point"] == [8, 5]]
    assert len(extra) == 1 and extra[0]["point_evaluation_s"] == pytest.approx(.37258498603478074)


def test_full_domain_costs_include_repeated_and_infeasible_evaluations():
    from scripts.plot_dantzig_cost_breakdown import FULL_BATCH, full_batch_runs, read_csv
    rows, _ = full_batch_runs()
    events = read_csv(FULL_BATCH / "evaluation_costs.csv")
    assert len(events) == 400
    assert sum(e["lookup_feasible"] == "False" for e in events) == 197
    assert sum(e["repeated_point"] == "True" for e in events) == 7
    for row in rows:
        group = [e for e in events if e["job_id"] == row["job_id"]]
        assert len(group) == 10
        expected = row["recorded_dfo_s"] + math.fsum(float(e["point_evaluation_s"]) - float(e["objective_wall_s"]) for e in group)
        assert row["estimated_total_s"] == pytest.approx(expected, rel=1e-12)
        assert row["unaccepted_nlp_s"] > 0
    _, summary = performance_tables(rows)
    assert {r["method"]: r["runs_99"] for r in summary} == dict(zip(METHODS, (3, 7, 21, 4)))
    for row, expected in zip(sorted(summary, key=lambda r: METHODS.index(r["method"])), (11.4918852, 35.5743427, 88.7638447, 18.7301774)):
        assert row["tts99_s"] == pytest.approx(expected, abs=1e-7)


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
    assert all(r["runs"] == 10 for r in rows if r["family"] == "DFO")
    loa = next(r for r in rows if r["case"] == "cstr" and r["cstr_size"] == "15" and r["method"] == "loa")
    # This validated incumbent is better than the historical lookup target.
    assert loa["target_attained"] == 1 and loa["final_objective"] < loa["target_value"]
    assert loa["time_limits"] == 1
    assert sum(r["time_limits"] for r in rows) == 23
    assert sum(r["bound_conflicts"] for r in rows) == 5
