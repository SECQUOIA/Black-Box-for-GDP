"""
Shared instrumentation utilities for benchmark runs.

This module keeps objective-call tracking, result-record creation, and CSV
result persistence in one place so DSDA and RBFOpt runs can report the same
schema.
"""

import csv
import json
import time
from datetime import datetime
from pathlib import Path


RESULT_FIELDS = (
    "csv_name",
    "method",
    "seed",
    "n_starts",
    "max_evals",
    "best_value",
    "best_point",
    "total_evals",
    "wall_time_s",
    "found_optimum",
    "incumbent_trajectory",
)


class TrackedObjective:
    """
    Wrap an objective callable and record black-box evaluation telemetry.

    Parameters
    ----------
    objective : callable
        Objective function to evaluate.
    maximize : bool, optional
        If True, larger objective values are treated as better. Otherwise,
        smaller values are treated as better.
    timer : callable, optional
        Monotonic timer used for per-call wall-time measurement.
    """

    def __init__(self, objective, maximize=False, timer=time.perf_counter):
        if not callable(objective):
            raise TypeError("objective must be callable")

        self._objective = objective
        self._maximize = maximize
        self._timer = timer
        self._call_count = 0
        self._incumbent = None
        self._incumbent_trajectory = []
        self._wall_times = []

    def __call__(self, *args, **kwargs):
        start_time = self._timer()
        value = self._objective(*args, **kwargs)
        elapsed = self._timer() - start_time

        self._call_count += 1
        self._wall_times.append(elapsed)
        self._update_incumbent(value)
        self._incumbent_trajectory.append(self._incumbent)

        return value

    @property
    def call_count(self):
        """Number of objective calls recorded by this wrapper."""
        return self._call_count

    @property
    def incumbent_trajectory(self):
        """Best objective value seen so far after each recorded call."""
        return list(self._incumbent_trajectory)

    @property
    def wall_times(self):
        """Per-call wall times in seconds."""
        return list(self._wall_times)

    @property
    def incumbent(self):
        """Best objective value seen so far, or None before the first call."""
        return self._incumbent

    def _update_incumbent(self, value):
        if self._incumbent is None:
            self._incumbent = value
            return

        if self._maximize:
            is_better = value > self._incumbent
        else:
            is_better = value < self._incumbent

        if is_better:
            self._incumbent = value


def make_result_record(
    csv_name,
    method,
    seed,
    n_starts,
    max_evals,
    best_value,
    best_point,
    total_evals,
    wall_time_s,
    found_optimum,
    incumbent_trajectory,
):
    """Build a unified benchmark result record."""
    return {
        "csv_name": csv_name,
        "method": method,
        "seed": seed,
        "n_starts": n_starts,
        "max_evals": max_evals,
        "best_value": best_value,
        "best_point": best_point,
        "total_evals": total_evals,
        "wall_time_s": wall_time_s,
        "found_optimum": found_optimum,
        "incumbent_trajectory": incumbent_trajectory,
    }


def save_results_csv(results_list, output_path):
    """
    Save unified benchmark result records to a CSV file.

    Sequence and mapping values are encoded as JSON strings so points and
    trajectories can be loaded back without ad hoc parsing.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for result in results_list:
            _validate_result_record(result)
            writer.writerow(
                {
                    field: _serialize_for_csv(result[field])
                    for field in RESULT_FIELDS
                }
            )


def make_timestamped_results_dir(base_dir, label):
    """Return a timestamped results directory path for one benchmark run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return Path(base_dir) / f"{label}_{timestamp}"


def _validate_result_record(result):
    missing = [field for field in RESULT_FIELDS if field not in result]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"Result record is missing required fields: {missing_text}")


def _serialize_for_csv(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value)
    return value
