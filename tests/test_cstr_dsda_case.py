"""Tests for the CSTR DSDA runner."""

import pytest

from case_studies.cstr_case import (
    CSTR_FEASIBLE_OBJECTIVES,
    KNOWN_BEST_POINT,
    KNOWN_BEST_VALUE,
)
from case_studies.cstr_dsda import choose_best_feasible_start, run_cstr_dsda
from instrumentation import TrackedObjective


def test_cstr_dsda_selects_lowest_feasible_lhc_start():
    objective = TrackedObjective(CSTR_FEASIBLE_OBJECTIVES.__getitem__)

    (
        selected_start,
        selected_start_value,
        feasible_start_values,
        starting_point_values,
    ) = choose_best_feasible_start(
        [(2, 2), (7, 7), (3, 3)],
        objective,
        CSTR_FEASIBLE_OBJECTIVES,
    )

    assert selected_start == (7, 7)
    assert selected_start_value == 2.965911187241821
    assert starting_point_values == [
        ((2, 2), 4.061881684530914),
        ((7, 7), 2.965911187241821),
        ((3, 3), 3.3148454030723937),
    ]
    assert feasible_start_values == [
        ((7, 7), 2.965911187241821),
        ((3, 3), 3.3148454030723937),
        ((2, 2), 4.061881684530914),
    ]
    assert objective.call_count == 3


def test_cstr_dsda_raises_if_no_lhc_starts_are_feasible():
    objective = TrackedObjective(lambda _point: float("inf"))

    with pytest.raises(ValueError, match="No feasible LHC starting points"):
        choose_best_feasible_start(
            [(1, 7), (2, 6)],
            objective,
            CSTR_FEASIBLE_OBJECTIVES,
        )

    assert objective.call_count == 2


def test_cstr_dsda_finds_known_best_from_default_seed():
    result = run_cstr_dsda(grid_size=7, seed=0, n_starts=3, max_evaluations=10)

    assert result["starting_points"] == [(2, 2), (7, 7), (3, 3)]
    assert result["selected_start"] == (7, 7)
    assert result["best_point"] == KNOWN_BEST_POINT
    assert result["best_value"] == KNOWN_BEST_VALUE
    assert result["result_record"]["method"] == "DSDA"
    assert result["result_record"]["found_optimum"]
    assert result["result_record"]["solver_iterations"] == result["run_result"][
        "major_iterations"
    ]
    assert result["tracked_evals"] <= 10
