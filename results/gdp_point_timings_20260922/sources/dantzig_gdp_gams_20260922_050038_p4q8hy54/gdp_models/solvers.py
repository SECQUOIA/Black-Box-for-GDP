"""Explicit native/GAMS solver selection and reproducible GAMS options."""

from functools import lru_cache
import math
from pathlib import Path
import tempfile

import pyomo.environ as pyo

from .preflight import SetupError


# Keep the original native IPOPT name; the comparison uses gams_ipopt.
GAMS_SOLVERS = {"gams_ipopt": "ipopt", "ipopth": "ipopth", "conopt": "conopt", "baron": "baron"}
SOLVERS = ("ipopt", *GAMS_SOLVERS)


def is_gams(solver):
    if solver not in SOLVERS:
        raise ValueError(f"Unknown solver {solver!r}; choose from {SOLVERS}")
    return solver in GAMS_SOLVERS


def optimizer_for(solver, executable=None):
    kwargs = {"executable": executable} if executable else {}
    if is_gams(solver):
        return pyo.SolverFactory("gams", solver_io="shell", **kwargs)
    return pyo.SolverFactory("ipopt", **kwargs)


def solve_options(solver, time_limit):
    if not is_gams(solver):
        return {"options": {"max_cpu_time": time_limit, "max_iter": 3000,
                            "bound_relax_factor": 0, "tol": 1e-8}}
    options = {"solver": GAMS_SOLVERS[solver], "mtype": "nlp", "warmstart": True,
               "io_options": {"put_results_format": "dat"},
               "add_options": [f"option reslim={time_limit};", "option iterlim=3000;",
                               "option threads=1;", "option optcr=0.00001;"]}
    if solver in {"gams_ipopt", "ipopth"}:
        options["add_options"].append("GAMS_MODEL.optfile=1;")
    return options


def option_file_lines(solver):
    if solver in {"gams_ipopt", "ipopth"}:
        linear_solver = "mumps" if solver == "gams_ipopt" else "ma27"
        return ["tol 1e-8", "bound_relax_factor 0", "max_iter 3000",
                "warm_start_init_point no", f"linear_solver {linear_solver}"]
    return []  # CONOPT uses its own tolerances; independent primal check is common.


def read_gams_statistics(path):
    """Preserve raw statuses: Pyomo can overwrite limit codes with model status."""
    stats = {}
    if path.is_file():
        for line in path.read_text().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                value = float(parts[1])
            except ValueError:
                value = math.nan
            stats[parts[0]] = value if math.isfinite(value) else None
    return stats


def solve_gams(optimizer, model, solver, time_limit, tee=False):
    # DAT output avoids requiring the proprietary GAMS Python/GDX packages.
    with tempfile.TemporaryDirectory(prefix="gdp-gams-") as directory:
        path = Path(directory)
        lines = option_file_lines(solver)
        if lines:
            (path / f"{GAMS_SOLVERS[solver]}.opt").write_text("\n".join(lines) + "\n")
        result = optimizer.solve(model, tee=tee, load_solutions=False,
                                 keepfiles=True, tmpdir=directory,
                                 **solve_options(solver, time_limit))
        statistics = read_gams_statistics(path / "resultsstat.dat")
    if not {"SOLVESTAT", "MODELSTAT"} <= statistics.keys():
        raise RuntimeError("GAMS did not return raw solve/model status codes")
    if statistics["SOLVESTAT"] == 7 or str(result.solver.termination_condition) == "licensingProblems":
        raise SetupError(f"GAMS/{GAMS_SOLVERS[solver]} license failure")
    return result, statistics


@lru_cache(maxsize=None)
def gams_smoke_check(solver, executable, executable_sha256):
    """Actually invoke each chosen solver once, before thousands of NLP calls.

    The binary digest is part of the cache key. No solve time enters a point's
    timing table. This is an availability check, not a GDP convergence test.
    """
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(0, 3), initialize=0.5)
    m.obj = pyo.Objective(expr=(m.x - 1) ** 2)
    try:
        result, stats = solve_gams(optimizer_for(solver, executable), m, solver, 15, tee=True)
        if (stats["SOLVESTAT"] != 1 or stats["MODELSTAT"] not in {1, 2}
                or str(result.solver.status) in {"error", "aborted"} or not len(result.solution)):
            raise RuntimeError(f"GAMS statuses: {stats}")
        m.solutions.load_from(result)
        if m.x.value is None or abs(m.x.value - 1) > 1e-4:
            raise RuntimeError("Simple quadratic test returned an incorrect solution")
    except Exception as error:
        raise SetupError(f"GAMS/{GAMS_SOLVERS[solver]} execution check failed: {error}") from error
    return {"solver": GAMS_SOLVERS[solver], "test": "quadratic", "status": "passed"}
