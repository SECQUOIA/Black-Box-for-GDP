"""Solve and time one actual NLP, with conservative acceptance of its result."""

import math
from time import perf_counter

import pyomo.environ as pyo
from pyomo.common.errors import InfeasibleConstraintException
from pyomo.version import version as pyomo_version

from .models import dynamic_template, integer_point, prepare_nlp
from .preflight import SetupError
from .solvers import GAMS_SOLVERS, is_gams, optimizer_for, option_file_lines, solve_gams, solve_options


def primal_violation(prepared):
    """Maximum absolute bound/constraint violation, including presolved rows."""
    worst = 0.0
    m = prepared.model
    for constraint in prepared.constraints:
        body = pyo.value(constraint.body, exception=False)
        if body is None or not math.isfinite(body):
            return math.inf
        if constraint.has_lb():
            worst = max(worst, pyo.value(constraint.lower) - body)
        if constraint.has_ub():
            worst = max(worst, body - pyo.value(constraint.upper))
    for var in m.component_data_objects(pyo.Var, active=True, descend_into=True):
        # Unused variables can remain uninitialized; every constraint/objective
        # expression is checked separately for uninitialized/nonfinite values.
        if var.value is None:
            continue
        if not math.isfinite(var.value):
            return math.inf
        if var.has_lb():
            worst = max(worst, pyo.value(var.lb) - var.value)
        if var.has_ub():
            worst = max(worst, var.value - pyo.value(var.ub))
    return worst


def accepted_solution(termination, objective, violation, tolerance):
    return bool(
        termination in {"optimal", "locallyOptimal", "globallyOptimal"}
        and objective is not None and math.isfinite(objective)
        and math.isfinite(violation) and violation <= tolerance
    )


def evaluate_point(case, point, *, solver, cstr_size=5, initialization="auto",
                   time_limit=60.0, feasibility_tolerance=1e-5, executable=None,
                   tee=False, artifact_dir=None, baron_lp_solver=None):
    """Return a JSON-compatible result; solver choice is deliberately explicit.

    ``objective`` is populated only for accepted solutions. A time-limited or
    infeasible candidate is recorded separately and never returned as a valid
    black-box objective. Errors configuring sources/dependencies propagate.
    Each call builds a fresh NLP; there is no objective cache or warm start.
    Dynamic clones a single discretized template. Its one-time preparation
    is excluded from point timings and recorded separately by the batch.
    """
    via_gams = is_gams(solver)
    if not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError("time_limit must be finite and positive")
    if not math.isfinite(feasibility_tolerance) or feasibility_tolerance <= 0:
        raise ValueError("feasibility_tolerance must be finite and positive")
    if case == "dynamic":
        dynamic_template()  # Outside per-point timing, even for the first point.
    started = perf_counter()
    point = integer_point(point)
    report = {
        "case": case, "point": list(point), "solver": solver,
        "solver_interface": "gams_shell" if via_gams else "native_ipopt",
        "gams_solver": GAMS_SOLVERS.get(solver),
        "cstr_size": cstr_size if case == "cstr" else None,
        "initialization_requested": initialization,
        "pyomo_version": pyomo_version, "time_limit_s": time_limit,
        "feasibility_tolerance": feasibility_tolerance,
        "accepted": False, "objective": None, "candidate_objective": None,
        "max_primal_violation": None, "solve_wall_s": 0.0,
    }
    try:
        prepared = prepare_nlp(case, point, cstr_size=cstr_size, initialization=initialization)
    except InfeasibleConstraintException as error:
        report.update(status="preprocessing_infeasible", termination="not_solved",
                      message=str(error), total_wall_s=perf_counter() - started)
        return report
    report.update(prepared.metadata)
    report.update(prepared.timings)
    m = prepared.model
    optimizer = optimizer_for(solver, executable)
    options = solve_options(solver, time_limit)
    report["solver_options"] = options
    if via_gams:
        report["solver_option_file"] = option_file_lines(solver)
        if solver == "baron" and baron_lp_solver is not None:
            report["solver_option_file"] = [
                f"LPSol {dict(clp=8, cplex=3)[baron_lp_solver]}", "NLPSol 9"]
            report["solver_options"]["add_options"].append("GAMS_MODEL.optfile=1;")
    if via_gams:
        report["solver_executable"] = optimizer.executable()
    elif executable:
        report["solver_executable"] = str(executable)
    solve_started = perf_counter()
    try:
        if via_gams:
            extra = {}
            if artifact_dir is not None:
                extra["artifact_dir"] = artifact_dir
            if baron_lp_solver is not None:
                extra["baron_lp_solver"] = baron_lp_solver
            result, stats = solve_gams(optimizer, m, solver, time_limit, tee=tee, **extra)
            report.update(gams_statistics=stats, gams_solve_status=stats["SOLVESTAT"],
                          gams_model_status=stats["MODELSTAT"])
            if str(result.solver.status) not in {"error", "aborted"} and len(result.solution):
                m.solutions.load_from(result)
            else:
                report.update(status="solver_error", termination=str(result.solver.termination_condition),
                              solver_status=str(result.solver.status), message=str(result.solver.message),
                              solve_wall_s=perf_counter() - solve_started,
                              total_wall_s=perf_counter() - started)
                return report
        else:
            result = optimizer.solve(m, tee=tee, **options)
    except SetupError:
        raise
    except ImportError as error:
        raise SetupError(f"Missing/broken solver dependency: {error}") from error
    except Exception as error:
        report.update(status="solver_error", termination="error", message=str(error),
                      solve_wall_s=perf_counter() - solve_started,
                      total_wall_s=perf_counter() - started)
        return report
    report["solve_wall_s"] = perf_counter() - solve_started
    termination = str(result.solver.termination_condition)
    if via_gams:
        termination = {2: "maxIterations", 3: "maxTimeLimit", 5: "maxEvaluations"}.get(
            stats["SOLVESTAT"], termination
        )
    objective = pyo.value(m.obj, exception=False)
    violation = primal_violation(prepared)
    accepted = (str(result.solver.status) not in {"error", "aborted"} and
                (not via_gams or (stats["SOLVESTAT"] == 1 and stats["MODELSTAT"] in {1, 2})) and
                accepted_solution(termination, objective, violation, feasibility_tolerance))
    report.update(
        status="accepted" if accepted else "rejected", accepted=accepted,
        objective=float(objective) if accepted else None,
        candidate_objective=float(objective) if objective is not None and math.isfinite(objective) else None,
        termination=termination, solver_status=str(result.solver.status),
        message=str(result.solver.message),
        max_primal_violation=violation if math.isfinite(violation) else None,
        total_wall_s=perf_counter() - started,
    )
    return report
