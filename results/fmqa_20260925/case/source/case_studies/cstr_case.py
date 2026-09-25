"""Shared data and objective helpers for the CSTR case study."""

import csv
import math
from importlib import resources

import numpy as np

import case_study_data.cstr as cstr_data


CSTR_CSV_TEMPLATE = "compl_enum_cstr_{grid_size}_baron_hull.csv"
DEFAULT_GRID_SIZE = 7
DEFAULT_MAX_EVALUATIONS = 10
LOWER_BOUNDS = np.array([1, 1])
VAR_TYPES = np.array(["I", "I"])
PENALTY = math.inf


def cstr_csv_name(grid_size=DEFAULT_GRID_SIZE):
    """Return the packaged CSV filename for a CSTR grid size."""
    return CSTR_CSV_TEMPLATE.format(grid_size=int(grid_size))


def load_cstr_case_data(grid_size=DEFAULT_GRID_SIZE):
    """Load objective data from one relocated CSTR completed-enumeration CSV."""
    grid_size = int(grid_size)
    csv_name = cstr_csv_name(grid_size)
    csv_path = resources.files(cstr_data) / csv_name
    if not csv_path.is_file():
        raise FileNotFoundError(f"Missing CSTR case-study CSV: {csv_name}")

    all_points = set()
    feasible_objectives = {}
    nonfinite_points = set()

    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            point = (int(row["x"]), int(row["y"]))
            all_points.add(point)

            try:
                objective = float(row["Objective"])
            except ValueError:
                objective = math.nan

            if math.isfinite(objective):
                previous = feasible_objectives.get(point)
                feasible_objectives[point] = (
                    objective if previous is None else min(previous, objective)
                )
            else:
                nonfinite_points.add(point)

    logical_infeasible_points = {
        (x_value, y_value)
        for x_value in range(1, grid_size + 1)
        for y_value in range(1, grid_size + 1)
        if y_value > x_value
    }
    upper_bounds = np.array([grid_size, grid_size])
    known_best_value = min(feasible_objectives.values())
    known_best_point = min(
        feasible_objectives,
        key=lambda point: feasible_objectives[point],
    )

    return {
        "csv_name": csv_name,
        "grid_size": grid_size,
        "lower_bounds": LOWER_BOUNDS.copy(),
        "upper_bounds": upper_bounds,
        "all_points": all_points,
        "feasible_objectives": feasible_objectives,
        "nonfinite_points": nonfinite_points,
        "logical_infeasible_points": logical_infeasible_points,
        "known_best_point": known_best_point,
        "known_best_value": known_best_value,
    }


CSTR_CASE_DATA = load_cstr_case_data()
CSTR_CSV_NAME = CSTR_CASE_DATA["csv_name"]
UPPER_BOUNDS = CSTR_CASE_DATA["upper_bounds"]
CSTR_ALL_POINTS = CSTR_CASE_DATA["all_points"]
CSTR_FEASIBLE_OBJECTIVES = CSTR_CASE_DATA["feasible_objectives"]
CSTR_NONFINITE_POINTS = CSTR_CASE_DATA["nonfinite_points"]
CSTR_LOGICAL_INFEASIBLE_POINTS = CSTR_CASE_DATA["logical_infeasible_points"]
KNOWN_BEST_POINT = CSTR_CASE_DATA["known_best_point"]
KNOWN_BEST_VALUE = CSTR_CASE_DATA["known_best_value"]


def cstr_objective(
    point,
    grid_size=DEFAULT_GRID_SIZE,
    penalty=PENALTY,
    feasible_objectives=None,
):
    """Evaluate the CSTR objective, penalizing missing or infeasible points."""
    if feasible_objectives is None:
        feasible_objectives = (
            CSTR_FEASIBLE_OBJECTIVES
            if grid_size == DEFAULT_GRID_SIZE
            else load_cstr_case_data(grid_size)["feasible_objectives"]
        )

    lattice_point = tuple(int(round(value)) for value in point)
    return feasible_objectives.get(lattice_point, penalty)


def is_cstr_feasible(point, grid_size=DEFAULT_GRID_SIZE, feasible_objectives=None):
    """Return True if the integer lattice point has a finite CSTR objective."""
    if feasible_objectives is None:
        feasible_objectives = (
            CSTR_FEASIBLE_OBJECTIVES
            if grid_size == DEFAULT_GRID_SIZE
            else load_cstr_case_data(grid_size)["feasible_objectives"]
        )

    lattice_point = tuple(int(round(value)) for value in point)
    return lattice_point in feasible_objectives
