"""Shared helpers for warm-started BAM benchmark and case-study runners."""

import math
import os
import sys
import time
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np

from instrumentation import TrackedObjective


def configure_bam_license(bam_module, bam_license_file=None):
    """Configure a BAM license file when the caller supplies one."""
    if not bam_license_file:
        return ""

    license_path = str(Path(bam_license_file).expanduser())
    bam_module.set_license_file(license_path)
    return license_path


@contextmanager
def suppress_solver_output():
    """Suppress native solver banners and iteration logs."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        stdout_fd = sys.stdout.fileno()
        stderr_fd = sys.stderr.fileno()
    except (AttributeError, OSError):
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                yield
        return

    saved_stdout_fd = os.dup(stdout_fd)
    saved_stderr_fd = os.dup(stderr_fd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)

    try:
        os.dup2(devnull_fd, stdout_fd)
        os.dup2(devnull_fd, stderr_fd)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout_fd, stdout_fd)
        os.dup2(saved_stderr_fd, stderr_fd)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)


def run_bam_with_initial_design(
    objective,
    lower_bounds,
    upper_bounds,
    starting_points,
    max_evaluations,
    bam_license_file=None,
    bam_module=None,
    verbose=False,
):
    """Run BAM from pre-evaluated initial points and return raw telemetry."""
    if bam_module is None:
        import bam as bam_module

    configured_license_file = configure_bam_license(
        bam_module,
        bam_license_file=bam_license_file,
    )
    init_node_pos = np.asarray(starting_points, dtype=float)
    if init_node_pos.ndim != 2:
        raise ValueError("starting_points must be a 2-D sequence of points")

    initial_evals = len(init_node_pos)
    if max_evaluations is not None and max_evaluations < initial_evals:
        raise ValueError(
            "max_evaluations must be greater than or equal to n_starts so "
            "all shared initial LHC points fit inside the evaluation budget"
        )

    n_dims = len(lower_bounds)
    bounds = [
        (float(lower_bound), float(upper_bound))
        for lower_bound, upper_bound in zip(lower_bounds, upper_bounds)
    ]
    tracked_objective = TrackedObjective(objective)
    start_time = time.perf_counter()
    init_node_val = np.asarray(
        [tracked_objective(point) for point in init_node_pos],
        dtype=float,
    )

    ranking_values = np.where(np.isfinite(init_node_val), init_node_val, np.inf)
    best_index = int(np.argmin(ranking_values))
    best_value = float(init_node_val[best_index])
    best_point = init_node_pos[best_index]
    remaining_evals = (
        None if max_evaluations is None else max_evaluations - initial_evals
    )
    bam_result = None

    if remaining_evals is None or remaining_evals > 0:
        options = {
            "print_to_screen": int(verbose),
            "x_evaluated": init_node_pos,
            "f_evaluated": init_node_val,
        }
        if remaining_evals is not None:
            options["max_evals"] = remaining_evals

        output_context = nullcontext() if verbose else suppress_solver_output()
        with output_context:
            bam_result = bam_module.minimize(
                tracked_objective,
                x0=None,
                bounds=bounds,
                integrality=[1] * n_dims,
                options=options,
            )
        best_value = float(bam_result.fun)
        best_point = np.asarray(bam_result.x, dtype=float)

    wall_time_s = time.perf_counter() - start_time
    best_point_rounded = [int(round(value)) for value in best_point]
    adaptive_evals = tracked_objective.call_count - initial_evals

    return {
        "starting_points": starting_points,
        "best_value": best_value,
        "best_point": best_point_rounded,
        "evalcount": getattr(bam_result, "nfev", 0),
        "iterations": getattr(bam_result, "nit", 0),
        "status": getattr(bam_result, "status", None),
        "message": getattr(bam_result, "message", ""),
        "tracked_evals": tracked_objective.call_count,
        "initial_evals": initial_evals,
        "adaptive_evals": adaptive_evals,
        "unique_evals": tracked_objective.unique_evaluation_count,
        "wall_time_s": wall_time_s,
        "incumbent_trajectory": tracked_objective.incumbent_trajectory,
        "objective_wall_times": tracked_objective.wall_times,
        "bam_license_file": configured_license_file,
        "result": bam_result,
    }


def make_nan_infeasible_objective(feasible_objectives):
    """Return objective values from a feasible map and NaN for infeasible points."""

    def objective(point):
        lattice_point = tuple(int(round(value)) for value in point)
        return feasible_objectives.get(lattice_point, math.nan)

    return objective
