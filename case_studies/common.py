"""Shared utilities for reproducible case-study runs."""

import math

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

    integer_lower_bounds = np.ceil(lower_bounds).astype(int)
    integer_upper_bounds = np.floor(upper_bounds).astype(int)
    lattice_size = math.prod(integer_upper_bounds - integer_lower_bounds + 1)
    if n_points > lattice_size:
        raise ValueError(
            f"Cannot generate {n_points} unique starts from a lattice with "
            f"only {lattice_size} points"
        )

    sampler = LatinHypercube(d=n_dims, seed=seed)
    points = []
    seen = set()

    def add_samples(unit_samples):
        scaled = lower_bounds + unit_samples * (upper_bounds - lower_bounds)
        for row in scaled:
            rounded = np.rint(row).astype(int)
            clamped = np.minimum(
                np.maximum(rounded, integer_lower_bounds),
                integer_upper_bounds,
            )
            point = tuple(int(value) for value in clamped)
            if point not in seen:
                points.append(point)
                seen.add(point)

    add_samples(sampler.random(n=n_points))
    attempts = 0
    max_attempts = max(100, 10 * lattice_size)
    while len(points) < n_points and attempts < max_attempts:
        add_samples(sampler.random(n=1))
        attempts += 1

    if len(points) < n_points:
        raise RuntimeError(
            "Unable to generate the requested number of unique LHC lattice starts"
        )
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
