"""Tests for the small-batch case data."""

import math

import numpy as np

from case_studies.common import generate_lhc_starting_points
from case_studies.small_batch_case import (
    KNOWN_BEST_POINT,
    KNOWN_BEST_VALUE,
    LOWER_BOUNDS,
    SMALL_BATCH_ALL_POINTS,
    SMALL_BATCH_FEASIBLE_OBJECTIVES,
    SMALL_BATCH_NONFINITE_POINTS,
    UPPER_BOUNDS,
    is_small_batch_feasible,
    small_batch_objective,
)


def test_small_batch_case_loads_relocated_csv_data():
    assert tuple(LOWER_BOUNDS.tolist()) == (2, 2, 1)
    assert tuple(UPPER_BOUNDS.tolist()) == (3, 3, 3)
    assert len(SMALL_BATCH_ALL_POINTS) == 12
    assert len(SMALL_BATCH_FEASIBLE_OBJECTIVES) == 12
    assert len(SMALL_BATCH_NONFINITE_POINTS) == 0


def test_small_batch_case_known_best_point():
    assert KNOWN_BEST_POINT == (2, 2, 1)
    assert KNOWN_BEST_VALUE == 167427.65711470306
    assert small_batch_objective((2, 2, 1)) == KNOWN_BEST_VALUE


def test_small_batch_objective_penalizes_missing_points():
    assert math.isinf(small_batch_objective((1, 2, 1)))
    assert math.isinf(small_batch_objective((3, 3, 4)))
    assert not is_small_batch_feasible((1, 2, 1))
    assert not is_small_batch_feasible((3, 3, 4))


def test_small_batch_objective_rounds_candidate_points():
    assert small_batch_objective((2.2, 2.1, 1.2)) == KNOWN_BEST_VALUE
    assert is_small_batch_feasible((2.2, 2.1, 1.2))


def test_small_batch_lhc_starting_points_are_within_bounds():
    points = generate_lhc_starting_points(
        n_dims=3,
        n_points=3,
        lb=LOWER_BOUNDS,
        ub=UPPER_BOUNDS,
        seed=0,
    )

    assert points == [(2, 3, 2), (3, 2, 2), (2, 2, 1)]
    for point in points:
        assert np.all(np.asarray(point) >= LOWER_BOUNDS)
        assert np.all(np.asarray(point) <= UPPER_BOUNDS)
