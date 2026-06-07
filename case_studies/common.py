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
