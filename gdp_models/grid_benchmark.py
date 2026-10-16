"""Grid GDP benchmark and actual GAMS/IPOPT point timings, one thread."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from time import perf_counter, time_ns

import pyomo.environ as pyo
from pyomo.core.expr.visitor import StreamBasedExpressionVisitor
from pyomo.solvers.plugins.solvers.GAMS import GAMSShell

from . import comparison
from .grid import (
    BOUNDS,
    CSV_ATOL,
    GRID_SIZE,
    _normalization,
    _read_reference,
    build_grid_gdp,
    fix_grid_point,
    GRID_DIR,
)
from .solvers import option_file_lines, read_gams_statistics, solve_options


METHODS = ("ric", "gloa", "loa", "bigm", "hull")


def method_config(config, method):
    """Exactly the method-specific profiles in the current process comparison."""
    if method not in METHODS:
        raise ValueError(f"Unknown method: {method}")
    return {
        **config,
        "nlp_solver": "baron",
        "mip_solver": "highs",
        "baron_lp_solver": "cplex" if method in {"bigm", "hull"} else "clp",
        "baron_column_hull_lbtt": 0,
    }


class ExplicitGAMS(GAMSShell):
    """Pyomo 6.10's shell constructor otherwise ignores executable=."""

    def __init__(self, executable, version=None):
        super().__init__()
        self.configured_executable = executable
        if version is not None:
            self._version = tuple(version)

    def executable(self):
        return self.configured_executable

    def available(self, exception_flag=True):
        available = os.access(self.configured_executable, os.X_OK)
        if not available and exception_flag:
            raise RuntimeError("Configured GAMS executable is unavailable")
        # A real IPOPT smoke solve occurs in preflight. Do not solve a second,
        # unrelated availability-test model inside every timed point call.
        return available


class Functions(StreamBasedExpressionVisitor):
    def __init__(self):
        super().__init__()
        self.names = set()

    def exitNode(self, node, data):
        if node.__class__.__name__ == "UnaryFunctionExpression":
            self.names.add(node.getname())


def baron_unsupported(model):
    visitor = Functions()
    visitor.walk_expression(model.obj.expr)
    return sorted(visitor.names - {"exp", "log", "log10", "sqrt"})


def prepare_grid(name):
    before = perf_counter()
    model = build_grid_gdp(name, verify_csv=True)
    unsupported = baron_unsupported(model)
    return model, {
        "grid_name": name,
        "preparation_wall_s": perf_counter() - before,
        "audit": model.grid_audit,
        "unsupported_baron_functions": unsupported,
        "point_count": GRID_SIZE**2,
        "normalization": "full analytic grid enumeration, outside search and point timers",
        "initialization": "constructor midpoint; no reference optimum warm start",
    }


def measure_point(name, point, config, work_root, log_path, reference):
    """Fresh GDP -> fixed NLP -> genuine IPOPT invocation, including zero-DOF cases.

    GAMS introduces its standard objective variable/equation even when all
    original variables are fixed. No dummy optimization variable is added here.
    """
    # Prepared once per grid, never charged 961 times to the timed objective.
    _normalization(name)
    started = perf_counter()
    model = build_grid_gdp(name, verify_csv=False)
    fix_grid_point(model, point)
    preparation = perf_counter() - started
    optimizer = ExplicitGAMS(config["executable"], config.get("gams_version"))
    options = solve_options("gams_ipopt", config["point_seconds"])
    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    record = {
        "grid_name": name,
        "point": list(point),
        "flat_index": point[0] * GRID_SIZE + point[1],
        "physical_point": [pyo.value(model.x), pyo.value(model.y)],
        "threads": 1,
        "solver": "gams_ipopt",
        "time_limit_s": config["point_seconds"],
        "original_free_variables": sum(
            not v.fixed for v in model.component_data_objects(pyo.Var)
        ),
        "preparation_wall_s": preparation,
        "accepted": False,
    }
    with tempfile.TemporaryDirectory(prefix="point_", dir=work_root) as temporary:
        work = Path(temporary)
        (work / "ipopt.opt").write_text(
            "\n".join(option_file_lines("gams_ipopt")) + "\n"
        )
        logfile = work / "ipopt.log"
        solve_started = perf_counter()
        try:
            result = optimizer.solve(
                model,
                load_solutions=False,
                keepfiles=True,
                tmpdir=str(work),
                logfile=str(logfile),
                tee=False,
                **options,
            )
            record["solver_call_wall_s"] = perf_counter() - solve_started
            statistics = read_gams_statistics(work / "resultsstat.dat")
            log = logfile.read_text(errors="replace") if logfile.exists() else ""
            verification_started = perf_counter()
            invoked = bool(re.search(r"Executing IPOPT\b|This is Ipopt version", log))
            if len(result.solution) and str(result.solver.status) not in {
                "error",
                "aborted",
            }:
                model.solutions.load_from(result)
            value = float(pyo.value(model.obj))
            expected = reference[tuple(point)]
            returned = statistics.get("OBJVAL")
            record.update(
                objective=value,
                csv_objective=expected,
                csv_abs_error=abs(value - expected),
                raw_objective=float(pyo.value(model.raw_objective)),
                termination=str(result.solver.termination_condition),
                solver_status=str(result.solver.status),
                gams_statistics=statistics,
                ipopt_invoked=invoked,
                gams_solve_s=statistics.get("ETSOLVE"),
            )
            match = re.search(r"Total seconds in IPOPT\s*=\s*([0-9.eE+-]+)", log)
            record["ipopt_reported_s"] = float(match[1]) if match else None
            record["accepted"] = bool(
                invoked
                and statistics.get("SOLVESTAT") == 1
                and statistics.get("MODELSTAT") in {1, 2}
                and returned is not None
                and abs(returned - value) <= 1e-7
                and abs(value - expected) <= CSV_ATOL
            )
            record["verification_wall_s"] = perf_counter() - verification_started
            record["point_wall_s"] = perf_counter() - started
            record["status"] = (
                "completed" if record["accepted"] else "invalid_solver_result"
            )
        except Exception as error:
            record.update(
                status="solver_error",
                message=f"{type(error).__name__}: {error}",
                solver_call_wall_s=perf_counter() - solve_started,
                point_wall_s=perf_counter() - started,
            )
            log = logfile.read_text(errors="replace") if logfile.exists() else ""
            # Failures keep their exact generated model/listing for diagnosis.
            diagnostic = (
                work_root.parent / f"failed_{record['flat_index']:04d}_{time_ns()}"
            )
            diagnostic.mkdir(exist_ok=True)
            import shutil

            for item in work.iterdir():
                if item.is_file():
                    shutil.copy2(item, diagnostic / item.name)
        if not record["accepted"] and (work / "output.lst").exists():
            (
                work_root.parent / f"failed_{record['flat_index']:04d}_{time_ns()}.lst"
            ).write_bytes((work / "output.lst").read_bytes())
        # Durable solver evidence is written outside the evaluation timer.
        record["solver_log_sha256"] = hashlib.sha256(log.encode()).hexdigest()
        with Path(log_path).open("a") as stream:
            stream.write(f"\n=== GRID {name} POINT {list(point)} ===\n{log}\n")
    record["recording_and_cleanup_wall_s"] = (
        perf_counter() - started - record["point_wall_s"]
    )
    return record


def grid_template(name):
    before = perf_counter()
    model, preparation = prepare_grid(name)
    from pyomo.contrib.fbbt.fbbt import fbbt

    fbbt(model)
    metadata = {
        "case": "grid",
        "instance_id": name,
        "grid_name": name,
        "cstr_size": None,
        "template_wall_s": perf_counter() - before,
        "grid_preparation": preparation,
        "physical_bounds": list(BOUNDS[name]),
    }
    return comparison.Template(model, metadata)


def check_grid_solution(template, directory, record):
    """Check the returned integer choices against the analytic model and CSV."""
    path = Path(directory) / "solution.json"
    if not path.exists():
        return record
    solution = json.loads(path.read_text())
    model = template.model.clone()
    for name, value in solution["variables"].items():
        component = model.find_component(name)
        if component is not None:
            component.set_value(value, skip_validation=True)
    choices = [
        [i for i in model.I if pyo.value(choice[i].binary_indicator_var) > 0.5]
        for choice in (model.Xchoice, model.Ychoice)
    ]
    if any(len(c) != 1 for c in choices):
        record.update(
            has_feasible_solution=False,
            global_optimality_certified=False,
            grid_validation="invalid selection",
        )
        return record
    point = [c[0] for c in choices]
    fixed = fix_grid_point(build_grid_gdp(model.grid_name, verify_csv=False), point)
    value = float(pyo.value(fixed.obj))
    reference, _ = _read_reference(GRID_DIR / f"{model.grid_name}.csv")
    error = abs(value - reference[tuple(point)])
    coordinate_error = max(
        abs(pyo.value(model.x) - pyo.value(fixed.x)),
        abs(pyo.value(model.y) - pyo.value(fixed.y)),
    )
    record.update(
        grid_point=point,
        snapped_objective=value,
        csv_objective=reference[tuple(point)],
        csv_abs_error=error,
        coordinate_abs_error=coordinate_error,
        normalized_gap_to_reference=value - min(reference.values()),
        target_hit=value - min(reference.values()) <= 1e-5,
    )
    if error > CSV_ATOL or coordinate_error > 1e-5:
        record.update(
            has_feasible_solution=False,
            global_optimality_certified=False,
            grid_validation="failed",
        )
    else:
        record["grid_validation"] = "passed"
    return record


def benchmark_worker(template, method, directory, config, deadline):
    """Run the exact process-comparison implementation on the grid template."""
    from grid_gdp_benchmark import process_identity
    from .grid_retry_fixes import corrected_gdpopt

    os.setsid()
    comparison.save_json(directory / "process.json", process_identity(os.getpid()))
    with (directory / "run.log").open("w", buffering=1) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        if config.get("retry_fix_profile"):
            template.metadata["retry_fix_profile"] = config["retry_fix_profile"]
        with corrected_gdpopt(config.get("retry_fix_profile"), template.model.grid_name, method) as fix_audit:
            report = comparison.solve_method(
                template, method, directory, method_config(config, method), deadline
            )
        if report is None:
            report = json.loads((directory / "result.json").read_text())
        report.update(fix_audit)
        report = check_grid_solution(template, directory, report)
        comparison.save_json(directory / "result.json", report)


def point_indices(text=None):
    if text is None:
        return list(range(GRID_SIZE**2))
    values = [int(v) for v in text.split(",")]
    if (
        not values
        or len(set(values)) != len(values)
        or any(not 0 <= v < GRID_SIZE**2 for v in values)
    ):
        raise ValueError("Point indices must be distinct integers in 0..960")
    return values


def quantile(values, fraction):
    data = sorted(values)
    index = (len(data) - 1) * fraction
    left = math.floor(index)
    return data[left] + (data[min(left + 1, len(data) - 1)] - data[left]) * (
        index - left
    )


def timing_summary(records, expected=961):
    accepted = [r for r in records if r["accepted"]]
    summary = {
        "attempted_points": len(records),
        "accepted_points": len(accepted),
        "expected_points": expected,
        "all_points_accepted": len(accepted) == expected,
    }
    if not accepted:
        return summary
    for field in (
        "preparation_wall_s",
        "solver_call_wall_s",
        "verification_wall_s",
        "point_wall_s",
        "gams_solve_s",
        "ipopt_reported_s",
    ):
        values = [r[field] for r in accepted if r.get(field) is not None]
        if values:
            summary[field] = {
                "n": len(values),
                "mean": sum(values) / len(values),
                "median": quantile(values, 0.5),
                "p95": quantile(values, 0.95),
                "p99": quantile(values, 0.99),
                "max": max(values),
                "sum": sum(values),
            }
    cost = summary["point_wall_s"]
    summary.update(
        projected_961_point_s=961 * cost["mean"],
        projection_only=len(accepted) != 961,
        suggested_timeout_s=max(1, math.ceil(2 * cost["max"])),
        timeout_policy="2 x observed max, rounded up; margin, not a measured requirement/guarantee",
        dfo_evaluation_cost_estimates_s={
            str(b): b * cost["mean"] for b in (10, 30, 50, 70, 100)
        },
    )
    return summary
