"""Shared utilities for reproducible case-study runs."""

import numpy as np
from scipy.stats.qmc import LatinHypercube


def generate_lhc_starting_points(n_dims, n_points, lb, ub, seed):
    """Generate deterministic Latin Hypercube points on an integer lattice."""
    if n_dims < 1:
        raise ValueError("n_dims must be at least 1")
    if n_points < 1:
        raise ValueError("n_points must be at least 1")
    if len(lb) != n_dims or len(ub) != n_dims:
        raise ValueError("lb and ub must match n_dims")

    lower_bounds = np.asarray(lb, dtype=float)
    upper_bounds = np.asarray(ub, dtype=float)
    if np.any(upper_bounds < lower_bounds):
        raise ValueError("ub must be greater than or equal to lb")

    sampler = LatinHypercube(d=n_dims, seed=seed)
    unit_samples = sampler.random(n=n_points)
    scaled = lower_bounds + unit_samples * (upper_bounds - lower_bounds)

    points = []
    for row in scaled:
        rounded = np.rint(row).astype(int)
        clamped = np.minimum(np.maximum(rounded, lower_bounds), upper_bounds)
        points.append(tuple(int(value) for value in clamped))
    return points


def rank_starting_points(starting_points, tracked_objective, is_feasible):
    """Evaluate and rank LHC starts while preserving full initial accounting."""
    starting_point_values = []
    feasible_start_values = []

    for point in starting_points:
        lattice_point = tuple(point)
        value = tracked_objective(lattice_point)
        starting_point_values.append((lattice_point, value))
        if is_feasible(lattice_point):
            feasible_start_values.append((lattice_point, value))

    if not feasible_start_values:
        raise ValueError("No feasible LHC starting points were generated for DSDA.")

    feasible_start_values.sort(key=lambda item: item[1])
    selected_start, selected_start_value = feasible_start_values[0]
    return (
        selected_start,
        selected_start_value,
        feasible_start_values,
        starting_point_values,
    )
