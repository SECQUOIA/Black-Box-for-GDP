"""Current-backend selection and scientific handling of unmeasured costs."""

import math

from fmqa_benchmark.current_runner import translate_arguments
from scripts.plot_dantzig_cost_breakdown import load_runs
from scripts.plot_dantzig_performance import PANELS, performance_tables, plot_profiles


def test_default_entry_points_route_to_qhd():
    args = translate_arguments(["plan"])
    assert args[args.index("--scope") + 1] == "process"
    assert args[args.index("--experiment") + 1] == "fmqa_qhd"
    args = translate_arguments(["plan", "--dataset", "grid"])
    assert args[args.index("--scope") + 1] == "grid"
    from fmqa_benchmark.optimizer import optimize
    from fmqa_benchmark.qhd_surrogate import train
    assert optimize.__kwdefaults__["trainer"] is train


def test_current_fmqa_replaces_every_seed_and_retains_other_methods():
    old = load_runs(PANELS, fmqa_backend="numpy_legacy")[0]
    current = load_runs(PANELS)[0]
    assert {r["job_id"]: r for r in old if r["method"] != "fmqa_sa"} == {
        r["job_id"]: r for r in current if r["method"] != "fmqa_sa"}
    fmqa = [r for r in current if r["method"] == "fmqa_sa"]
    assert len(fmqa) == 90 and all(r["backend"] == "pytorch_qhd_data" for r in fmqa)
    assert not {r["job_id"] for r in fmqa} & {r["job_id"] for r in old}
    batch = [r for r in fmqa if r["case"] == "small_batch"]
    assert sum(r["lookup_target_hit"] for r in batch) == 6


def test_missing_time_is_neither_failure_nor_zero_and_does_not_bias_group_median():
    runs = [{"case": p[0], "cstr_size": p[1], "budget": p[2], "method": m, "seed": s,
             "lookup_target_hit": True, "estimated_total_s": 10. + s}
            for p in PANELS for m in ("dsda", "rbfopt", "bam", "fmqa_sa") for s in (0, 1)]
    for r in runs:
        if r["method"] == "fmqa_sa" and r["seed"] == 1:
            r.update(estimated_total_s=math.nan, missing_point_costs=1)
    profiles, summaries = performance_tables(runs)
    for row in summaries:
        if row["method"] == "fmqa_sa":
            assert row["target_hits"] == row["runs"] == 2
            assert row["timed_runs"] == 1 and math.isnan(row["tts99_s"])
    import matplotlib.pyplot as plt
    fig = plot_profiles(profiles)
    try:
        assert all(len(ax.lines) == 3 for ax in fig.axes)
        assert all(any(t.get_text() == "FMQA-SA: N/A" for t in ax.texts) for ax in fig.axes)
    finally:
        plt.close(fig)


def test_logical_rejection_plan_covers_only_missing_unique_coordinates():
    from fmqa_qhd_point_runner import plan
    rows = plan()
    assert len(rows) == 96
    assert sum(r["case_name"] == "column" for r in rows) == 1
    assert all(r["point"][0] < r["point"][1] for r in rows if r["case_name"] == "cstr")


def test_completed_point_ledger_counts_every_visit_and_reconciles_run_times():
    import csv
    import gzip
    import json
    from collections import defaultdict

    import pytest

    from fmqa_benchmark.publication import CURRENT, process_runs

    supplement = json.loads((CURRENT / "point_supplement.json").read_text())
    measured = {r["source_member"]: r["total_wall_s"] for r in supplement["points"]}
    assert len(measured) == 96
    groups, filled = defaultdict(list), []
    with gzip.open(CURRENT / "publication_evaluation_costs.csv.gz", "rt") as stream:
        for row in csv.DictReader(stream):
            groups[row["job_id"]].append(row)
            if row["point_source"] in measured:
                assert float(row["point_evaluation_s"]) == measured[row["point_source"]]
                assert row["point_outcome"] == "preprocessing_infeasible"
                filled.append(row)
    assert len(groups) == 1190 and sum(map(len, groups.values())) == 58030
    assert len(filled) == 112 and len({r["job_id"] for r in filled}) == 42
    for rows in groups.values():
        costs = []
        for row in rows:
            costs.append(float(row["point_evaluation_s"]))
            assert float(row["cumulative_point_evaluation_s"]) == pytest.approx(math.fsum(costs), rel=1e-12)
    runs, _ = process_runs()
    for row in runs:
        assert row["cost_complete"] and row["missing_point_costs"] == 0
        events = groups[row["job_id"]]
        expected = row["recorded_dfo_s"] + row["dynamic_preparation_s"] + math.fsum(
            float(e["point_evaluation_s"]) - float(e["objective_wall_s"]) for e in events)
        assert row["estimated_total_s"] == pytest.approx(expected, rel=1e-12)
