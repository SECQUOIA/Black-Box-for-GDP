"""Shared data and objective helpers for the small-batch case study."""

import csv
import math
from importlib import resources

import numpy as np

import case_study_data.small_batch as small_batch_data


SMALL_BATCH_CSV_NAME = "compl_enum_small_batch_baron.csv"
LOWER_BOUNDS = np.array([2, 2, 1])
UPPER_BOUNDS = np.array([3, 3, 3])
VAR_TYPES = np.array(["I", "I", "I"])
PENALTY = math.inf
DEFAULT_MAX_EVALUATIONS = 10


def load_small_batch_case_data():
    """Load objective data from the relocated small-batch CSV."""
    all_points = set()
    feasible_objectives = {}
    nonfinite_points = set()

    csv_path = resources.files(small_batch_data) / SMALL_BATCH_CSV_NAME
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            point = (int(row["x"]), int(row["y"]), int(row["z"]))
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

    known_best_value = min(feasible_objectives.values())
    known_best_point = min(
        feasible_objectives,
        key=lambda point: feasible_objectives[point],
    )

    return {
        "csv_name": SMALL_BATCH_CSV_NAME,
        "all_points": all_points,
        "feasible_objectives": feasible_objectives,
        "nonfinite_points": nonfinite_points,
        "known_best_point": known_best_point,
        "known_best_value": known_best_value,
    }


SMALL_BATCH_CASE_DATA = load_small_batch_case_data()
SMALL_BATCH_ALL_POINTS = SMALL_BATCH_CASE_DATA["all_points"]
SMALL_BATCH_FEASIBLE_OBJECTIVES = SMALL_BATCH_CASE_DATA["feasible_objectives"]
SMALL_BATCH_NONFINITE_POINTS = SMALL_BATCH_CASE_DATA["nonfinite_points"]
KNOWN_BEST_POINT = SMALL_BATCH_CASE_DATA["known_best_point"]
KNOWN_BEST_VALUE = SMALL_BATCH_CASE_DATA["known_best_value"]


def small_batch_objective(point, penalty=PENALTY, feasible_objectives=None):
    """Evaluate the small-batch objective, penalizing missing or non-finite points."""
    if feasible_objectives is None:
        feasible_objectives = SMALL_BATCH_FEASIBLE_OBJECTIVES

    lattice_point = tuple(int(round(value)) for value in point)
    return feasible_objectives.get(lattice_point, penalty)


def is_small_batch_feasible(point, feasible_objectives=None):
    """Return True if the integer lattice point has a finite objective."""
    if feasible_objectives is None:
        feasible_objectives = SMALL_BATCH_FEASIBLE_OBJECTIVES

    lattice_point = tuple(int(round(value)) for value in point)
    return lattice_point in feasible_objectives
