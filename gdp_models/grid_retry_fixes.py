"""Opt-in, worker-local corrections for the recorded Pyomo 6.10.0 failures.

Neither correction changes the analytic objective, CSV, solvers or budgets.
The profile is nevertheless separate from the original process comparison.
"""
from contextlib import contextmanager
import importlib
import math

PROFILE = "pyomo610-grid-v1"
FBBT_GRIDS = {"camel3", "dropwave", "sum_of_squares"}


def supported_retry(job):
    return (
        job["grid_name"] in FBBT_GRIDS
        and job["method"] in {"ric", "gloa", "loa"}
        and job["error_kind"] == "fbbt"
    ) or (
        job["grid_name"] == "alpine1" and job["method"] == "loa"
        and job["error_kind"] == "differentiation"
    )


@contextmanager
def corrected_gdpopt(profile, grid_name, method):
    """Restore all original Pyomo functions on normal and exceptional exit."""
    if profile is None:
        yield {}
        return
    import pyomo.environ as pyo
    from pyomo.version import version
    from pyomo.core.expr.numeric_expr import PowExpression
    from pyomo.contrib.gdpopt.loa import GDP_LOA_Solver

    if profile != PROFILE or version != "6.10.0":
        raise ValueError(f"{PROFILE} requires Pyomo 6.10.0, observed {version}")
    if not (grid_name in FBBT_GRIDS and method in {"ric", "gloa", "loa"}
            or grid_name == "alpine1" and method == "loa"):
        raise ValueError("Correction profile is restricted to the ten diagnosed pairs")
    fbbt = importlib.import_module("pyomo.contrib.fbbt.fbbt")
    dispatch = fbbt._prop_bnds_root_to_leaf_map
    original_power = dispatch[PowExpression]
    original_cuts = GDP_LOA_Solver._add_cuts_to_discrete_problem
    audit = {"retry_fix_profile": PROFILE, "fixed_exponent_bound_resets": 0,
             "loa_cuts_skipped_after_bound_convergence": 0}

    def fixed_power(node, bounds, tolerance):
        exponent = node.args[1]
        if pyo.is_fixed(exponent):
            value = pyo.value(exponent)
            if bounds[exponent] != (value, value):
                audit["fixed_exponent_bound_resets"] += 1
                # A fixed exponent is a constant, not an interval variable.
                # Roundoff elsewhere must not turn 2 into (2, 2-epsilon).
                bounds[exponent] = (value, value)
        return original_power(node, bounds, tolerance)

    def cuts_after_convergence_check(solver, subproblem, discrete, sense, config, timing):
        if (math.isfinite(solver.LB) and math.isfinite(solver.UB)
                and solver.bounds_converged(config)):
            audit["loa_cuts_skipped_after_bound_convergence"] += 1
            return
        return original_cuts(solver, subproblem, discrete, sense, config, timing)

    try:
        if grid_name in FBBT_GRIDS:
            dispatch[PowExpression] = fixed_power
        if grid_name == "alpine1":
            GDP_LOA_Solver._add_cuts_to_discrete_problem = cuts_after_convergence_check
        yield audit
    finally:
        dispatch[PowExpression] = original_power
        GDP_LOA_Solver._add_cuts_to_discrete_problem = original_cuts
