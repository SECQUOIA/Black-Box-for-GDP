"""Tests for the distillation column DSDA runner."""

import pytest

from case_studies.column_case import KNOWN_BEST_POINT, KNOWN_BEST_VALUE
from case_studies.column_dsda import (
    choose_best_feasible_start,
    run_column_dsda,
)
from instrumentation import TrackedObjective


def test_column_dsda_selects_lowest_feasible_lhc_start():
    objective_values = {
        (14, 4): 19740.33791404187,
        (12, 1): 20515.889497874727,
    }
    objective = TrackedObjective(
        lambda point: objective_values.get(tuple(point), 1e6)
    )

    (
        selected_start,
        selected_start_value,
        feasible_start_values,
        starting_point_values,
    ) = choose_best_feasible_start(
        [(14, 4), (12, 1), (9, 8)],
        objective,
    )

    assert selected_start == (14, 4)
    assert selected_start_value == 19740.33791404187
    assert starting_point_values == [
        ((14, 4), 19740.33791404187),
        ((12, 1), 20515.889497874727),
        ((9, 8), 1e6),
    ]
    assert feasible_start_values == [
        ((14, 4), 19740.33791404187),
        ((12, 1), 20515.889497874727),
    ]
    assert objective.call_count == 3


def test_column_dsda_raises_if_no_lhc_starts_are_feasible():
    objective = TrackedObjective(lambda _point: 0.0)

    with pytest.raises(ValueError, match="No feasible LHC starting points"):
        choose_best_feasible_start([(8, 3), (15, 9), (10, 4)], objective)

    assert objective.call_count == 3


def test_column_dsda_finds_known_best_from_default_seed():
    result = run_column_dsda(seed=1, n_starts=3, max_evaluations=16)

    assert result["starting_points"] == [(14, 4), (12, 1), (9, 8)]
    assert result["starting_point_values"] == [
        ((14, 4), 19740.33791404187),
        ((12, 1), 20515.889497874727),
        ((9, 8), 1e6),
    ]
    assert result["feasible_start_values"] == [
        ((14, 4), 19740.33791404187),
        ((12, 1), 20515.889497874727),
    ]
    assert result["selected_start"] == (14, 4)
    assert result["best_point"] == KNOWN_BEST_POINT
    assert result["best_value"] == KNOWN_BEST_VALUE
    assert result["result_record"]["method"] == "DSDA"
    assert result["result_record"]["found_optimum"]
    assert result["result_record"]["solver_iterations"] == result["run_result"][
        "major_iterations"
    ]
    assert result["tracked_evals"] <= 16
