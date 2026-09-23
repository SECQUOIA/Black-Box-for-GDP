"""Shared data and objective helpers for the distillation column case."""

import csv
import math
from importlib import resources

import numpy as np

import case_study_data.column as column_data


COLUMN_CSV_NAME = "compl_enum_column_17_baron.csv"
LOWER_BOUNDS = np.array([7, 1])
UPPER_BOUNDS = np.array([15, 9])
VAR_TYPES = np.array(["I", "I"])
PENALTY = 1e6
DEFAULT_MAX_EVALUATIONS = 16


def load_column_case_data():
    """Load objective data from the relocated distillation column CSV."""
    all_points = set()
    feasible_objectives = {}
    nonfinite_points = set()

    csv_path = resources.files(column_data) / COLUMN_CSV_NAME
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

    return {
        "csv_name": COLUMN_CSV_NAME,
        "all_points": all_points,
        "feasible_objectives": feasible_objectives,
        "nonfinite_points": nonfinite_points,
    }


COLUMN_CASE_DATA = load_column_case_data()
COLUMN_ALL_POINTS = COLUMN_CASE_DATA["all_points"]
COLUMN_FEASIBLE_OBJECTIVES = COLUMN_CASE_DATA["feasible_objectives"]
COLUMN_NONFINITE_POINTS = COLUMN_CASE_DATA["nonfinite_points"]

KNOWN_BEST_VALUE = min(COLUMN_FEASIBLE_OBJECTIVES.values())
KNOWN_BEST_POINT = min(
    COLUMN_FEASIBLE_OBJECTIVES,
    key=lambda point: COLUMN_FEASIBLE_OBJECTIVES[point],
)


def column_objective(point, penalty=PENALTY):
    """Evaluate the column objective, penalizing missing or non-finite points."""
    lattice_point = tuple(int(round(value)) for value in point)
    return COLUMN_FEASIBLE_OBJECTIVES.get(lattice_point, penalty)


def is_column_feasible(point):
    """Return True if the integer lattice point has a finite column objective."""
    lattice_point = tuple(int(round(value)) for value in point)
    return lattice_point in COLUMN_FEASIBLE_OBJECTIVES
