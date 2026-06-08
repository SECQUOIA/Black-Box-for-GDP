"""Tests for the distillation column case data."""

import numpy as np

from case_studies.column_case import (
    COLUMN_ALL_POINTS,
    COLUMN_FEASIBLE_OBJECTIVES,
    COLUMN_NONFINITE_POINTS,
    KNOWN_BEST_POINT,
    KNOWN_BEST_VALUE,
    LOWER_BOUNDS,
    PENALTY,
    UPPER_BOUNDS,
    column_objective,
    is_column_feasible,
)
from case_studies.common import generate_lhc_starting_points


def test_column_case_loads_relocated_csv_data():
    assert tuple(LOWER_BOUNDS.tolist()) == (7, 1)
    assert tuple(UPPER_BOUNDS.tolist()) == (15, 9)
    assert len(COLUMN_ALL_POINTS) == 38
    assert len(COLUMN_FEASIBLE_OBJECTIVES) == 29
    assert len(COLUMN_NONFINITE_POINTS) == 9


def test_column_case_known_best_point():
    assert KNOWN_BEST_POINT == (13, 4)
    assert KNOWN_BEST_VALUE == 19346.12472619312
    assert column_objective((13, 4)) == KNOWN_BEST_VALUE


def test_column_objective_penalizes_nonfinite_and_missing_points():
    assert column_objective((15, 9)) == PENALTY
    assert column_objective((7, 1)) == PENALTY
    assert column_objective((7, 2)) == PENALTY
    assert not is_column_feasible((15, 9))
    assert not is_column_feasible((7, 2))


def test_column_objective_rounds_candidate_points():
    assert column_objective((13.2, 4.1)) == KNOWN_BEST_VALUE
    assert is_column_feasible((13.2, 4.1))


def test_column_lhc_starting_points_are_within_bounds():
    points = generate_lhc_starting_points(
        n_dims=2,
        n_points=3,
        lb=LOWER_BOUNDS,
        ub=UPPER_BOUNDS,
        seed=0,
    )

    assert points == [(8, 3), (15, 9), (10, 4)]
    for point in points:
        assert np.all(np.asarray(point) >= LOWER_BOUNDS)
        assert np.all(np.asarray(point) <= UPPER_BOUNDS)
