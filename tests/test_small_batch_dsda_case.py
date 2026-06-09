"""Tests for the small-batch DSDA runner."""

import pytest

from case_studies.small_batch_case import KNOWN_BEST_POINT, KNOWN_BEST_VALUE
from case_studies.small_batch_dsda import (
    choose_best_feasible_start,
    run_small_batch_dsda,
)
from instrumentation import TrackedObjective


def test_small_batch_dsda_selects_lowest_feasible_lhc_start():
    objective = TrackedObjective(
        {
            (2, 3, 2): 209964.94866578083,
            (3, 2, 2): 222943.12301931926,
            (2, 2, 1): 167427.65711470306,
        }.__getitem__
    )

    (
        selected_start,
        selected_start_value,
        feasible_start_values,
        starting_point_values,
    ) = choose_best_feasible_start(
        [(2, 3, 2), (3, 2, 2), (2, 2, 1)],
        objective,
    )

    assert selected_start == (2, 2, 1)
    assert selected_start_value == 167427.65711470306
    assert starting_point_values == [
        ((2, 3, 2), 209964.94866578083),
        ((3, 2, 2), 222943.12301931926),
        ((2, 2, 1), 167427.65711470306),
    ]
    assert feasible_start_values == [
        ((2, 2, 1), 167427.65711470306),
        ((2, 3, 2), 209964.94866578083),
        ((3, 2, 2), 222943.12301931926),
    ]
    assert objective.call_count == 3


def test_small_batch_dsda_raises_if_no_lhc_starts_are_feasible():
    objective = TrackedObjective(lambda _point: 0.0)

    with pytest.raises(ValueError, match="No feasible LHC starting points"):
        choose_best_feasible_start([(1, 2, 1), (3, 3, 4)], objective)

    assert objective.call_count == 2


def test_small_batch_dsda_finds_known_best_from_default_seed():
    result = run_small_batch_dsda(seed=0, n_starts=3, max_evaluations=10)

    assert result["starting_points"] == [(2, 3, 2), (3, 2, 2), (2, 2, 1)]
    assert result["selected_start"] == (2, 2, 1)
    assert result["best_point"] == KNOWN_BEST_POINT
    assert result["best_value"] == KNOWN_BEST_VALUE
    assert result["result_record"]["method"] == "DSDA"
    assert result["result_record"]["found_optimum"]
    assert result["tracked_evals"] <= 10
