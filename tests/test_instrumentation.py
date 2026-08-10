"""Tests for shared benchmark instrumentation."""

import csv
import json
import math

from instrumentation import TrackedObjective, make_result_record, save_results_csv


def test_tracked_objective_recovers_after_infeasible_nan_values():
    values = iter((math.nan, math.nan, 5.0, math.nan, 3.0))
    objective = TrackedObjective(lambda _point: next(values))

    for index in range(5):
        objective([index])

    trajectory = objective.incumbent_trajectory
    assert math.isnan(trajectory[0])
    assert math.isnan(trajectory[1])
    assert trajectory[2:] == [5.0, 5.0, 3.0]
    assert objective.incumbent == 3.0


def test_maximizing_tracker_also_ignores_nan_after_a_finite_incumbent():
    values = iter((math.nan, 2.0, math.nan, 4.0))
    objective = TrackedObjective(lambda _point: next(values), maximize=True)

    for index in range(4):
        objective([index])

    trajectory = objective.incumbent_trajectory
    assert math.isnan(trajectory[0])
    assert trajectory[1:] == [2.0, 2.0, 4.0]


def test_result_csv_serializes_nonfinite_trajectory_values_as_json_null(tmp_path):
    output_path = tmp_path / "results.csv"
    record = make_result_record(
        csv_name="case.csv",
        method="BAM",
        seed=0,
        n_starts=3,
        max_evals=4,
        best_value=1.0,
        best_point=[1, 1],
        total_evals=4,
        wall_time_s=0.1,
        found_optimum=True,
        incumbent_trajectory=[math.nan, math.inf, -math.inf, 1.0],
    )

    save_results_csv([record], output_path)

    with output_path.open(newline="") as handle:
        row = next(csv.DictReader(handle))
    assert json.loads(row["incumbent_trajectory"]) == [None, None, None, 1.0]
    assert "NaN" not in row["incumbent_trajectory"]
    assert "Infinity" not in row["incumbent_trajectory"]
