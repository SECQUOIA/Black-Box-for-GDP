"""Tests for the dynamic case-study DSDA runner."""

import numpy as np
import pytest

from case_studies.common import generate_lhc_starting_points
from case_studies.dynamic_case import KNOWN_BEST_POINT, KNOWN_BEST_VALUE, PENALTY
from case_studies.dynamic_dsda import (
    choose_best_feasible_start,
    run_dynamic_dsda,
)
from instrumentation import TrackedObjective


def test_dynamic_dsda_selects_lowest_feasible_lhc_start():
    points = generate_lhc_starting_points(
        n_dims=2,
        n_points=3,
        lb=np.array([1, 2]),
        ub=np.array([9, 9]),
        seed=0,
    )
    objective = TrackedObjective(
        {
            (2, 4): -137.1797042946188,
            (9, 9): -28.596739202011523,
            (4, 5): -55.81190616713566,
        }.__getitem__
    )

    (
        selected_start,
        selected_start_value,
        feasible_start_values,
        starting_point_values,
    ) = choose_best_feasible_start(
        points,
        objective,
    )

    assert selected_start == (2, 4)
    assert selected_start_value == -137.1797042946188
    assert starting_point_values == [
        ((2, 4), -137.1797042946188),
        ((9, 9), -28.596739202011523),
        ((4, 5), -55.81190616713566),
    ]
    assert feasible_start_values == [
        ((2, 4), -137.1797042946188),
        ((4, 5), -55.81190616713566),
        ((9, 9), -28.596739202011523),
    ]
    assert objective.call_count == 3


def test_dynamic_dsda_ignores_infeasible_lhc_starts():
    result = run_dynamic_dsda(seed=1, n_starts=3, max_evaluations=12)

    assert result["starting_points"] == [(8, 4), (6, 2), (3, 8)]
    assert result["starting_point_values"][:3] == [
        ((8, 4), PENALTY),
        ((6, 2), PENALTY),
        ((3, 8), -141.82503814335138),
    ]
    assert result["feasible_start_values"] == [((3, 8), -141.82503814335138)]
    assert result["selected_start"] == (3, 8)


def test_dynamic_dsda_finds_known_best_from_seed_zero():
    result = run_dynamic_dsda(seed=0, n_starts=3, max_evaluations=12)

    assert result["starting_points"] == [(2, 4), (9, 9), (4, 5)]
    assert result["selected_start"] == (2, 4)
    assert result["best_point"] == KNOWN_BEST_POINT
    assert result["best_value"] == KNOWN_BEST_VALUE
    assert result["result_record"]["method"] == "DSDA"
    assert result["result_record"]["found_optimum"]
    assert result["tracked_evals"] <= 12


def test_dynamic_dsda_does_not_re_evaluate_selected_start_after_ranking():
    result = run_dynamic_dsda(seed=0, n_starts=3, max_evaluations=4)

    assert result["tracked_evals"] == 4
    assert result["run_result"]["point_evaluations"] == 1
    assert result["run_result"]["points_explored"] == 2


def test_dynamic_dsda_raises_if_no_lhc_starts_are_feasible():
    objective = TrackedObjective(lambda _point: 0.0)

    with pytest.raises(ValueError, match="No feasible LHC starting points"):
        choose_best_feasible_start([(8, 4), (6, 2)], objective)

    assert objective.call_count == 2
