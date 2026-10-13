"""Rerun only Small Batch RBFOpt with the other cases' solver search settings."""

from contextlib import contextmanager
import importlib.metadata
import math
import os
from pathlib import Path
import platform
import sys
import time

import small_batch_full_domain as full
from overnight_benchmark.common import append, csv_file, jsonl, sha

ROOT = Path(__file__).resolve().parent
KIND = "small_batch_rbfopt_solver_v1"
BUNDLE_FOLDER = "small_batch_rbfopt_solver_runner"
RUN_PREFIX = "small_batch_rbfopt_solver_"
RUNTIME_ROLES = ("dfo",)
RECORD_AUXILIARY_SOLVERS = True
REQUIREMENTS = "requirements-small-batch-rbfopt-solver.txt"
SOURCE_FILES = (*full.SOURCE_FILES, "small_batch_rbfopt_solver.py", REQUIREMENTS,
                "run_small_batch_rbfopt_solver_dantzig.sh", "docs/small_batch_rbfopt_solver.md",
                "tests/test_small_batch_rbfopt_solver.py")
SETTINGS = {"algorithm": "MSRSM", "global_search_method": "solver", "rbf": "auto"}
PROTOCOL = {**full.PROTOCOL,
    "methods": ["rbfopt"], "rbfopt": "MSRSM + solver + rbf=auto; RBFOpt 4.3.0 defaults otherwise",
    "auxiliary_solvers": "Bonmin for RBF surrogate MINLPs; IPOPT where requested by RBFOpt",
    "solver_audit": "Every Pyomo Bonmin/IPOPT solve start/end, options, termination, time and exception",
    "timing_includes": "Optimizer, callback trace writes and auxiliary solver audit writes",
    "replaces": "Only the 10 Small Batch full-domain MSRSM/sampling runs after validation",
}


def plan():
    return [{**spec, "settings": dict(SETTINGS), "job_id": spec["job_id"] + "_solver"}
            for spec in full.plan() if spec["method"] == "rbfopt"]


problem = full.problem


@contextmanager
def solver_audit(path):
    """Observe the existing RBFOpt calls without changing options or exceptions."""
    import pyomo.environ  # Register the executable solver plugins before wrapping.
    import pyomo.opt
    factory = pyomo.opt.SolverFactory
    count = 0
    if path.exists():
        raise ValueError("Refusing to append a new run to an existing solver trace")

    def audited_factory(name, *args, **kwargs):
        nonlocal count
        solver = factory(name, *args, **kwargs)
        if name not in {"bonmin", "ipopt"}:
            return solver
        original_solve = solver.solve

        def solve(*solve_args, **solve_kwargs):
            nonlocal count
            count += 1
            identifier = count
            append(path, {"event": "solver_start", "call_id": identifier, "solver": name,
                          "executable": solver.executable(), "options": dict(solver.options),
                          "scope": "RBFOpt auxiliary surrogate problem"})
            started = time.perf_counter()
            try:
                result = original_solve(*solve_args, **solve_kwargs)
            except Exception as error:
                append(path, {"event": "solver_end", "call_id": identifier, "solver": name,
                              "wall_s": time.perf_counter() - started, "exception_type": type(error).__name__,
                              "error": str(error), "status": "exception", "termination_condition": None})
                raise
            append(path, {"event": "solver_end", "call_id": identifier, "solver": name,
                          "wall_s": time.perf_counter() - started, "exception_type": None,
                          "status": str(result.solver.status),
                          "termination_condition": str(result.solver.termination_condition)})
            return result

        solver.solve = solve
        return solver

    pyomo.opt.SolverFactory = audited_factory
    try:
        yield
    finally:
        pyomo.opt.SolverFactory = factory


def solver_trace(path):
    events = jsonl(path)
    if not events or len(events) % 2:
        raise ValueError("Missing or incomplete auxiliary solver calls")
    counts, exceptions, nonoptimal = {}, 0, 0
    for identifier, (start, end) in enumerate(zip(events[::2], events[1::2]), 1):
        if (start["event"] != "solver_start" or end["event"] != "solver_end"
                or start["call_id"] != identifier or end["call_id"] != identifier
                or start["solver"] != end["solver"] or start["solver"] not in {"bonmin", "ipopt"}
                or not math.isfinite(end["wall_s"]) or end["wall_s"] < 0):
            raise ValueError("Auxiliary solver trace does not reconcile")
        counts[start["solver"]] = counts.get(start["solver"], 0) + 1
        exceptions += end["exception_type"] is not None
        nonoptimal += end["termination_condition"] != "optimal"
    if not counts.get("bonmin"):
        raise ValueError("No actual Bonmin invocation in this solver-search run")
    return {"path": path.name, "sha256": sha(path), "calls": len(events) // 2,
            "calls_by_solver": counts, "exceptions": exceptions, "nonoptimal_calls": nonoptimal}


def run_dfo(spec, config, directory):
    if spec["method"] != "rbfopt" or spec["settings"] != SETTINGS:
        raise ValueError("Expected RBFOpt MSRSM/solver/auto")
    path = directory / "solver_calls.jsonl"
    with solver_audit(path):
        output = full.run_dfo(spec, config)
    return {**output, "solver_trace": solver_trace(path)}


def validate_saved_result(job, result):
    if result["spec"]["settings"] != SETTINGS:
        raise ValueError("Saved RBFOpt settings differ from the solver-search protocol")
    if result["solver_trace"] != solver_trace(job / "solver_calls.jsonl"):
        raise ValueError("Auxiliary solver trace checksum/count mismatch")


def smoke(config):
    """Fail preflight if either executable cannot solve a tiny test model."""
    import pyomo.environ as pyo
    for name in ("bonmin", "ipopt"):
        model = pyo.ConcreteModel()
        model.x = pyo.Var(bounds=(0, 3), initialize=0,
                          domain=pyo.Integers if name == "bonmin" else pyo.Reals)
        model.objective = pyo.Objective(expr=(model.x - 1) ** 2)
        solver = pyo.SolverFactory(name, executable=config[name], solver_io="nl")
        solver.options["max_cpu_time"] = 20
        if name == "bonmin":
            solver.options["bonmin.time_limit"] = 30
        solved = solver.solve(model)
        if not pyo.check_optimal_termination(solved) or abs(pyo.value(model.x) - 1) > 1e-4:
            raise ValueError(f"{name} failed the executable smoke test")


def runtime(config, role):
    from case_studies.common import generate_lhc_starting_points
    from cpu_affinity import affinity_record, pin_cpu
    from process_followup_runner import THREAD_ENV
    if role != "dfo":
        raise ValueError("This experiment needs only the RBFOpt environment")
    if not platform.node().startswith("dantzig") and not config["allow_other_host"]:
        raise ValueError("Use Dantzig, or --allow-other-host for a local check")
    cpu = pin_cpu(config["cpu"])
    expected = dict(line.split("==") for line in (ROOT / REQUIREMENTS).read_text().splitlines()
                    if line and not line.startswith("#"))
    versions = {name: importlib.metadata.version(name) for name in expected}
    if versions != expected:
        raise ValueError(f"Environment differs from {REQUIREMENTS}: {versions}")
    identities = {}
    for name in ("bonmin", "ipopt"):
        path = Path(config[name])
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"Missing executable: {name}: {path}")
        identities[name + "_sha256"] = sha(path)
    for spec in plan():
        starts = generate_lhc_starting_points(3, 3, spec["lower_bounds"], spec["upper_bounds"], spec["seed"])
        if [list(point) for point in starts] != spec["starting_points"]:
            raise ValueError("LHC coordinates differ from the frozen design")
    smoke(config)
    return {"host": platform.node(), "system": platform.system(), "machine": platform.machine(),
            "libc": list(platform.libc_ver()), "python": platform.python_version(), "executable": sys.executable,
            "versions": versions, "affinity": affinity_record(cpu),
            "thread_environment": {k: os.environ.get(k) for k in THREAD_ENV},
            "reference_sha256": sha(ROOT / full.REFERENCE), **identities}


def report_costs(directory, results, callbacks):
    summary = full.report_costs(directory, results, callbacks)
    rows = []
    for result in results:
        if result["status"] == "completed":
            spec = result["spec"]
            validate_saved_result(directory / "jobs" / spec["job_id"], result)
            rows.extend({"job_id": spec["job_id"], "seed": spec["seed"], **event}
                        for event in jsonl(directory / "jobs" / spec["job_id"] / "solver_calls.jsonl"))
    csv_file(directory / "auxiliary_solver_calls.csv", rows)
    ends = [row for row in rows if row["event"] == "solver_end"]
    return {**summary, "rbfopt_settings": SETTINGS,
            "auxiliary_solver_calls": len(ends),
            "auxiliary_solver_exceptions": sum(row["exception_type"] is not None for row in ends),
            "auxiliary_solver_nonoptimal_calls": sum(row["termination_condition"] != "optimal" for row in ends)}
