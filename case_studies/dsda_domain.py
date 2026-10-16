"""Process-only DSDA membership and initialization; never screen lookup outcomes."""

from itertools import product
import math


def box_membership(lower, upper):
    """Dummy keys for the explicit integer box, independent of objective data."""
    if len(lower) != len(upper) or not len(lower):
        raise ValueError("Invalid box dimensions")
    bounds = list(zip(lower, upper))
    if any(int(lo) != lo or int(hi) != hi or hi < lo for lo, hi in bounds):
        raise ValueError("Expected ordered integer bounds")
    return dict.fromkeys(product(*(range(int(lo), int(hi) + 1) for lo, hi in bounds)))


def validate_design(points, lower, upper, n_starts, budget):
    """Keep frozen order; fail before callbacks if the initial design cannot fit."""
    if budget is not None and (int(budget) != budget or budget < n_starts):
        raise ValueError("max_evaluations must cover the entire initial design")
    points = [tuple(p) for p in points]
    if len(points) != n_starts or n_starts < 1:
        raise ValueError("Initial design length differs from n_starts")
    for point in points:
        if len(point) != len(lower) or any(
            int(v) != v or not lo <= v <= hi for v, lo, hi in zip(point, lower, upper)
        ):
            raise ValueError("Initial point outside the declared integer box")
    return points


def rank_observed_starts(points, tracked_objective, penalty=math.inf):
    """Select only from charged observations; no separate feasibility-map query."""
    observations = [(tuple(p), tracked_objective(tuple(p))) for p in points]
    valid = [(p, v) for p, v in observations if math.isfinite(v) and v != penalty]
    if not valid:
        raise ValueError(
            "No feasible LHC starting points: all observed responses unsuccessful"
        )
    valid.sort(key=lambda item: item[1])  # Stable ordering preserves first tie.
    point, value = valid[0]
    return point, value, valid, observations
