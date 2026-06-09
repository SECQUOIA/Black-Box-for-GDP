"""Tests for the CSTR case data."""

import math

import numpy as np

from case_studies.common import generate_lhc_starting_points
from case_studies.cstr_case import (
    CSTR_FEASIBLE_OBJECTIVES,
    CSTR_LOGICAL_INFEASIBLE_POINTS,
    KNOWN_BEST_POINT,
    KNOWN_BEST_VALUE,
    LOWER_BOUNDS,
    UPPER_BOUNDS,
    cstr_objective,
    is_cstr_feasible,
    load_cstr_case_data,
)


def test_cstr_case_loads_default_grid_data():
    assert tuple(LOWER_BOUNDS.tolist()) == (1, 1)
    assert tuple(UPPER_BOUNDS.tolist()) == (7, 7)
    assert len(CSTR_FEASIBLE_OBJECTIVES) == 28
    assert len(CSTR_LOGICAL_INFEASIBLE_POINTS) == 21


def test_cstr_case_known_best_point():
    assert KNOWN_BEST_POINT == (7, 7)
    assert KNOWN_BEST_VALUE == 2.965911187241821
    assert cstr_objective((7, 7)) == KNOWN_BEST_VALUE


def test_cstr_case_can_load_larger_grid_size():
    case_data = load_cstr_case_data(grid_size=17)

    assert case_data["csv_name"] == "compl_enum_cstr_17_baron_hull.csv"
    assert tuple(case_data["upper_bounds"].tolist()) == (17, 17)
    assert len(case_data["feasible_objectives"]) == 153
    assert len(case_data["logical_infeasible_points"]) == 136
    assert case_data["known_best_point"] == (17, 17)
    assert case_data["known_best_value"] == 2.81525078099529


def test_cstr_objective_penalizes_logically_infeasible_and_missing_points():
    assert math.isinf(cstr_objective((1, 2)))
    assert math.isinf(cstr_objective((8, 8)))
    assert not is_cstr_feasible((1, 2))
    assert not is_cstr_feasible((8, 8))


def test_cstr_objective_rounds_candidate_points():
    assert cstr_objective((6.8, 6.6)) == KNOWN_BEST_VALUE
    assert is_cstr_feasible((6.8, 6.6))


def test_cstr_lhc_starting_points_are_within_bounds():
    points = generate_lhc_starting_points(
        n_dims=2,
        n_points=3,
        lb=LOWER_BOUNDS,
        ub=UPPER_BOUNDS,
        seed=0,
    )

    assert points == [(2, 2), (7, 7), (3, 3)]
    for point in points:
        assert np.all(np.asarray(point) >= LOWER_BOUNDS)
        assert np.all(np.asarray(point) <= UPPER_BOUNDS)
