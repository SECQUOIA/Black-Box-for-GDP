"""
Shared instrumentation utilities for benchmark runs.

This module keeps objective-call tracking, result-record creation, and CSV
result persistence in one place so DSDA and RBFOpt runs can report the same
schema.
"""

import csv
import json
import math
import time
from datetime import datetime
from pathlib import Path

from evaluation_trace import ACTIVE_TRACE


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
    "initial_evals",
    "adaptive_evals",
    "unique_evals",
    "solver_evalcount",
    "solver_iterations",
    "solver_status",
    "solver_message",
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
        self._evaluation_points = []

    def __call__(self, *args, **kwargs):
        observer = ACTIVE_TRACE.get()
        point = _freeze_point(args[0]) if args else None
        trace_start = observer.timer() if observer else None
        start_time = self._timer()
        try:
            value = self._objective(*args, **kwargs)
        except BaseException as exception:
            if observer:
                observer.record(
                    point, None, self._incumbent, self._timer() - start_time,
                    trace_start, observer.timer(), type(exception).__name__,
                )
            raise
        elapsed = self._timer() - start_time
        trace_end = observer.timer() if observer else None

        self._call_count += 1
        self._evaluation_points.append(point)
        self._wall_times.append(elapsed)
        self._update_incumbent(value)
        self._incumbent_trajectory.append(self._incumbent)

        if observer:
            observer.record(point, value, self._incumbent, elapsed, trace_start, trace_end)

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
    def evaluation_points(self):
        """Point argument recorded for each objective call, when available."""
        return list(self._evaluation_points)

    @property
    def unique_evaluation_count(self):
        """Number of distinct point arguments recorded by this wrapper."""
        return len({point for point in self._evaluation_points if point is not None})

    @property
    def incumbent(self):
        """Best objective value seen so far, or None before the first call."""
        return self._incumbent

    def _update_incumbent(self, value):
        value_is_nan = _is_nan(value)
        incumbent_is_nan = _is_nan(self._incumbent)

        if self._incumbent is None or incumbent_is_nan:
            self._incumbent = value
            return
        if value_is_nan:
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
    initial_evals=None,
    adaptive_evals=None,
    unique_evals=None,
    solver_evalcount=None,
    solver_iterations=None,
    solver_status=None,
    solver_message="",
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
        "initial_evals": initial_evals,
        "adaptive_evals": adaptive_evals,
        "unique_evals": unique_evals,
        "solver_evalcount": solver_evalcount,
        "solver_iterations": solver_iterations,
        "solver_status": solver_status,
        "solver_message": solver_message,
    }


def save_results_csv(results_list, output_path):
    """
    Save unified benchmark result records to a CSV file.

    Sequence and mapping values are encoded as JSON strings so points and
    trajectories can be loaded back without ad hoc parsing.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results_list = list(results_list)
    # Preserve the original schema for callers that do not report D-SDA target
    # proximity; mixed-method files leave these optional columns empty elsewhere.
    optional = ("observed_best_value", "target_reached")
    fields = RESULT_FIELDS + tuple(
        field for field in optional if any(field in row for row in results_list)
    )

    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results_list:
            _validate_result_record(result)
            writer.writerow(
                {
                    field: _serialize_for_csv(result.get(field))
                    for field in fields
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
        return json.dumps(_json_safe(value), allow_nan=False)
    return value


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        if not math.isfinite(value):
            return None
    except TypeError:
        pass
    return value


def _freeze_point(point):
    if isinstance(point, (str, bytes)):
        return point
    try:
        return tuple(float(value) for value in point)
    except (TypeError, ValueError):
        try:
            return float(point)
        except (TypeError, ValueError):
            return repr(point)


def _is_nan(value):
    if value is None:
        return False
    try:
        return math.isnan(value)
    except TypeError:
        return False
