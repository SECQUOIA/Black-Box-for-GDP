"""Shared data and objective helpers for the dynamic mode-switching case."""

import numpy as np


LOWER_BOUNDS = np.array([1, 2])
UPPER_BOUNDS = np.array([9, 9])
VAR_TYPES = np.array(["I", "I"])
PENALTY = 1e6
DEFAULT_MAX_EVALUATIONS = 12

DYNAMIC_FEASIBLE_OBJECTIVES = {
    (1, 2): -197.14013122689622,
    (1, 3): -206.36041265432806,
    (1, 4): -212.00878719112268,
    (1, 5): -207.62611633572016,
    (1, 6): -196.93118428995865,
    (1, 7): -178.63847525562682,
    (1, 8): -146.87850122234687,
    (1, 9): -87.5338894428716,
    (2, 3): -117.07438084784795,
    (2, 4): -137.1797042946188,
    (2, 5): -192.870848809807,
    (2, 6): -192.88392569521721,
    (2, 7): -175.94473700875903,
    (2, 8): -144.71276519403037,
    (2, 9): -85.82696130620648,
    (3, 4): -77.19743879461578,
    (3, 5): -88.41538101128177,
    (3, 6): -119.38309938589616,
    (3, 7): -170.89539354574913,
    (3, 8): -141.82503814335138,
    (3, 9): -83.55206301486514,
    (4, 5): -55.81190616713566,
    (4, 6): -62.4732860007934,
    (4, 7): -77.86237831841856,
    (4, 8): -135.07901900226858,
    (4, 9): -80.51745201314861,
    (5, 6): -43.41238657553521,
    (5, 7): -47.28320969606174,
    (5, 8): -54.212220237141665,
    (5, 9): -66.30029047415469,
    (6, 7): -36.01889379296989,
    (6, 8): -37.96970292827284,
    (6, 9): -39.58228460866401,
    (7, 8): -31.679373632369185,
    (7, 9): -32.196321090299925,
    (8, 9): -29.327202909495576,
    (9, 9): -28.596739202011523,
}

KNOWN_BEST_VALUE = min(DYNAMIC_FEASIBLE_OBJECTIVES.values())
KNOWN_BEST_POINT = min(
    DYNAMIC_FEASIBLE_OBJECTIVES,
    key=lambda point: DYNAMIC_FEASIBLE_OBJECTIVES[point],
)


def dynamic_objective(point, penalty=PENALTY):
    """Evaluate the dynamic case objective, penalizing logic-infeasible points."""
    lattice_point = tuple(int(round(value)) for value in point)
    return DYNAMIC_FEASIBLE_OBJECTIVES.get(lattice_point, penalty)


def is_dynamic_feasible(point):
    """Return True if the integer lattice point is feasible in the dynamic case."""
    lattice_point = tuple(int(round(value)) for value in point)
    return lattice_point in DYNAMIC_FEASIBLE_OBJECTIVES
