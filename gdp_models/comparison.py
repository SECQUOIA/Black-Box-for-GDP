"""Full GDP / MINLP comparisons with bounded GAMS calls and checked incumbents."""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
from time import monotonic

import pyomo.environ as pyo
from pyomo.core.plugins.transform.logical_to_linear import update_boolean_vars_from_binary
from pyomo.gdp import Disjunct, Disjunction
from pyomo.opt import SolverFactory, TerminationCondition as tc
from pyomo.solvers.plugins.solvers.GAMS import GAMSShell
from pyomo.repn.plugins.gams_writer import valid_solvers

from ._sources import provenance
from .models import MODELS, _initialize, build_gdp, dynamic_template
from .solvers import read_gams_statistics


METHODS = ("ric", "gloa", "bigm", "hull")
CASES = ("cstr", "column", "dynamic", "small_batch")
SOLVER_NAME = "_rbfopt_comparison_gams"
DESCEND = (pyo.Block, Disjunct)
CONTEXT = None
# Pyomo 6.10's static GAMS writer list predates GAMS/HiGHS. Register only
# documented linear model types; GAMS preflight still checks actual support.
valid_solvers.setdefault("HIGHS", {"LP", "MIP", "RMIP"})


class BudgetExpired(RuntimeError):
    pass


class IncompleteSubproblem(RuntimeError):
    def __init__(self, model, call):
        self.model, self.call = model, call
        super().__init__(f"GAMS/{call['solver']} subproblem did not prove optimality within "
                         f"the configured gap or infeasibility: {call.get('gams_statistics')}")


def solver_policy(config, method):
    baron = {"baron_lp_subsolver": config.get("baron_lp_solver", "cplex"),
             "baron_nlp_subsolver": "ipopt", "warmstart": False}
    if method in {"ric", "gloa"}:
        policy = {"nlp": config.get("nlp_solver", "ipopt"),
                  "mip": config.get("mip_solver", "cplex")}
        if policy["nlp"] == "baron":
            policy.update(baron)
        return policy
    return {"minlp": "baron", **baron}


def baron_options(config):
    lp = {"cplex": 3, "clp": 8}[config.get("baron_lp_solver", "cplex")]
    return (f"LPSol {lp}", "NLPSol 9")


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def subproblem_complete(call, relative_gap):
    """Accept a global solver's normal termination with a proven gap/infeasibility.

    GAMS can label a BARON NLP 'locallyOptimal' (MODELSTAT 2) when the
    *global* bound reaches optcr. Check the raw bound, not just that label.
    All benchmark objectives minimize; OBJEST is their lower bound.
    """
    stats = call.get("gams_statistics", {})
    if stats.get("SOLVESTAT") != 1:
        return False
    status = stats.get("MODELSTAT")
    if status in {1, 4, 10, 19}:
        return True
    allowed = {2, 8} if call["solver"] == "baron" else {8}
    value, bound = finite(stats.get("OBJVAL")), finite(stats.get("OBJEST"))
    if status not in allowed or value is None or bound is None:
        return False
    # Allow only output rounding and BARON's minimum absolute tolerance.
    slack = 1e-9 * max(1, abs(value), abs(bound))
    return -slack <= value - bound <= relative_gap * abs(value) + slack


def save_json(path, obj):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def append_event(path, event):
    with path.open("a") as stream:
        stream.write(json.dumps(event, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


@dataclass
class SolveContext:
    executable: str
    directory: Path
    deadline: float
    relative_gap: float = 1e-5
    calls: list = field(default_factory=list)
    baron_options: tuple = ("LPSol 3", "NLPSol 9")
    strict_subproblems: bool = False

    def remaining(self):
        # Leave a small part of the worker budget for reading/checking results.
        left = self.deadline - monotonic()
        reserve = min(10.0, max(0.2, left * 0.05))
        if left <= reserve + 0.05:
            raise BudgetExpired("No remaining job budget for another solver call")
        return left - reserve


@SolverFactory.register(SOLVER_NAME, doc="Budgeted single-thread GAMS for GDP comparison")
class TimedGAMS(GAMSShell):
    """Respect the executable and a shared deadline, including GDPopt subsolves.

    Pyomo 6.10's GAMSShell ignores constructor executable=; override its method
    instead. Actual solver/license checks are performed by the runner preflight.
    """

    def executable(self):
        if CONTEXT is None:
            raise RuntimeError("Comparison solver context was not initialized")
        return CONTEXT.executable

    def available(self, exception_flag=True):
        available = CONTEXT is not None and os.access(CONTEXT.executable, os.X_OK)
        if not available and exception_flag:
            raise RuntimeError("Configured GAMS executable is unavailable")
        return available

    def solve(self, model, **kwargs):
        context = CONTEXT
        seconds = context.remaining()
        solver = kwargs.pop("solver")
        if solver not in {"ipopt", "cplex", "highs", "baron"}:
            raise ValueError(f"Unsupported comparison solver: {solver}")
        load = kwargs.pop("load_solutions", True)
        call = {"index": len(context.calls) + 1, "solver": solver, "mtype": kwargs.get("mtype"),
                "limit_s": seconds, "threads": 1, "status": "running"}
        started = monotonic()
        with tempfile.TemporaryDirectory(prefix="gams-", dir=context.directory) as tmp:
            path = Path(tmp)
            opts = [f"option reslim={seconds};", "option threads=1;",
                    f"option optcr={context.relative_gap};", "option optca=0;"]
            if solver == "ipopt":
                (path / "ipopt.opt").write_text(
                    "tol 1e-8\nbound_relax_factor 0\nmax_iter 10000\n"
                    "linear_solver mumps\nwarm_start_init_point no\n")
                opts.append("GAMS_MODEL.optfile=1;")
            elif solver == "baron":
                # Avoid platform-dependent automatic subsolver switching.
                (path / "baron.opt").write_text("\n".join(context.baron_options) + "\n")
                opts.append("GAMS_MODEL.optfile=1;")
            option_file = path / f"{solver}.opt"
            call["solver_option_file"] = option_file.read_text().splitlines() if option_file.exists() else []
            try:
                result = super().solve(
                    model, solver=solver, load_solutions=False, keepfiles=True,
                    tmpdir=str(path), warmstart=(solver != "baron"), tee=True,
                    io_options={"put_results_format": "dat"}, add_options=opts, **kwargs)
                stats = read_gams_statistics(path / "resultsstat.dat")
                if not {"MODELSTAT", "SOLVESTAT"} <= stats.keys():
                    raise RuntimeError("Missing raw GAMS status records")
                call["gams_statistics"] = stats
                if solver == "baron" and stats["MODELSTAT"] not in {1, 2, 8}:
                    listing = path / "output.lst"
                    if listing.exists():
                        (context.directory / f"call_{call['index']:05d}_diagnostic.lst").write_bytes(listing.read_bytes())
                # GAMS model status may overwrite a resource-limit termination in
                # Pyomo. Preserve the actual limit in the result used by GDPopt.
                limited = {2: tc.maxIterations, 3: tc.maxTimeLimit, 4: tc.internalSolverError,
                           5: tc.maxEvaluations, 6: tc.error, 8: tc.userInterrupt,
                           9: tc.solverFailure, 10: tc.solverFailure, 11: tc.error,
                           12: tc.error, 13: tc.error}
                if stats["SOLVESTAT"] in limited:
                    result.solver.termination_condition = limited[stats["SOLVESTAT"]]
                if stats["SOLVESTAT"] == 7:
                    raise RuntimeError(f"GAMS/{solver} license failure")
                if load and len(result.solution) and str(result.solver.status) not in {"error", "aborted"}:
                    model.solutions.load_from(result)
                call.update(status="returned", termination=str(result.solver.termination_condition),
                            solver_status=str(result.solver.status),
                            lower_bound=finite(result.problem.lower_bound),
                            upper_bound=finite(result.problem.upper_bound))
                if context.strict_subproblems:
                    call["global_subproblem_complete"] = subproblem_complete(call, context.relative_gap)
            except BaseException as error:
                call.update(status="error", message=f"{type(error).__name__}: {error}")
                if (path / "output.lst").exists():
                    # Preserve diagnostic listings for failed calls only.
                    (context.directory / f"call_{call['index']:05d}_error.lst").write_bytes(
                        (path / "output.lst").read_bytes())
                raise
            finally:
                call["wall_s"] = monotonic() - started
                context.calls.append(call)
                append_event(context.directory / "solver_calls.jsonl", call)
        if context.strict_subproblems:
            # GDPopt accepts local/incomplete NLPs and can cut their discrete
            # configuration off. Stop before that happens in the BARON run.
            if not call["global_subproblem_complete"]:
                candidate = model if solver == "baron" and load and len(result.solution) else None
                raise IncompleteSubproblem(candidate, call)
        return result


@dataclass
class Template:
    model: object
    metadata: dict


def build_template(case, *, cstr_size=30, instance_id=None):
    started = monotonic()
    if case == "dynamic":
        dynamic = dynamic_template()
        model = dynamic.model.clone()
        preparation = dynamic.preparation
    else:
        model = build_gdp(case, cstr_size=cstr_size)
        preparation = None
    initialization, files = _initialize(model, case, cstr_size, "auto")
    # Only globally active constraints are tightened; inactive disjuncts must
    # never be intersected. This derives finite Small Batch exponential bounds
    # instead of letting MC++ substitute its arbitrary missing-bound default.
    from pyomo.contrib.fbbt.fbbt import fbbt
    before_bounds = {v.name: (v.lb, v.ub) for v in model.component_data_objects(pyo.Var, descend_into=DESCEND)}
    tightened_started = monotonic()
    fbbt(model)
    tightened = {v.name: {"before": list(before_bounds[v.name]), "after": [v.lb, v.ub]}
                 for v in model.component_data_objects(pyo.Var, descend_into=DESCEND)
                 if before_bounds[v.name] != (v.lb, v.ub)}
    source, relative, _ = MODELS[case]
    metadata = {"case": case, "cstr_size": cstr_size if case == "cstr" else None,
                "instance_id": instance_id or (f"cstr_{cstr_size}" if case == "cstr" else case),
                "source": provenance(source, [relative, *files]),
                "initialization": initialization, "dynamic_preparation": preparation,
                "global_fbbt_wall_s": monotonic() - tightened_started,
                "globally_implied_bounds": tightened,
                "template_wall_s": monotonic() - started,
                "template_policy": "built once, independent unsolved clone per method"}
    return Template(model, metadata)


def reformulate(model, method):
    pyo.TransformationFactory("core.logical_to_linear").apply_to(model)
    if method in {"bigm", "hull"}:
        # Derive M from the original finite expression bounds, never an arbitrary M.
        pyo.TransformationFactory("gdp." + method).apply_to(model)


def transfer_values(source, target):
    for var in target.component_data_objects(pyo.Var, descend_into=DESCEND):
        other = source.find_component(var.name)
        if other is not None and other.value is not None:
            var.set_value(other.value, skip_validation=True)
        elif not var.fixed:
            var.set_value(None)
    update_boolean_vars_from_binary(target, integer_tolerance=1e-5)


def validate_original(model, tolerance=1e-5):
    """Validate active original GDP constraints, logic, integrality and bounds."""
    violation, undefined = 0.0, []
    selected = []

    def residual(expression, lower, upper, name):
        nonlocal violation
        value = finite(pyo.value(expression, exception=False))
        if value is None:
            undefined.append(name)
            return
        if lower is not None:
            violation = max(violation, pyo.value(lower) - value)
        if upper is not None:
            violation = max(violation, value - pyo.value(upper))

    def walk(block):
        nonlocal violation
        for var in block.component_data_objects(pyo.Var, active=True, descend_into=False):
            if var.value is None:
                continue  # Unused variables need not have values; expressions are checked.
            residual(var, var.lb, var.ub, var.name)
            if var.is_integer() and finite(var.value) is not None:
                violation = max(violation, abs(var.value - round(var.value)))
        for constraint in block.component_data_objects(pyo.Constraint, active=True, descend_into=False):
            residual(constraint.body, constraint.lower, constraint.upper, constraint.name)
        for logic in block.component_data_objects(pyo.LogicalConstraint, active=True, descend_into=False):
            try:
                valid = pyo.value(logic.body, exception=False) is True
            except (ValueError, TypeError):
                valid = False
            if not valid:
                undefined.append(logic.name)
        for disjunction in block.component_data_objects(Disjunction, active=True, descend_into=False):
            values = [finite(d.binary_indicator_var.value) for d in disjunction.disjuncts]
            if any(v is None for v in values):
                undefined.append(disjunction.name)
            else:
                violation = max(violation, abs(sum(values) - 1) if disjunction.xor else 1 - sum(values),
                                *(abs(v - round(v)) for v in values))
        for child in block.component_data_objects(pyo.Block, active=True, descend_into=False):
            walk(child)
        for child in block.component_data_objects(Disjunct, active=True, descend_into=False):
            value = finite(child.binary_indicator_var.value)
            if value is None:
                undefined.append(child.name)
            elif value > 0.5:
                selected.append(child.name)
                walk(child)

    walk(model)
    objective = finite(pyo.value(model.obj, exception=False))
    booleans = [v.name for v in model.component_data_objects(pyo.BooleanVar, descend_into=DESCEND)
                if v.value is True and not v.name.endswith(".indicator_var")]
    return {"has_feasible_solution": objective is not None and not undefined and violation <= tolerance,
            "candidate_objective": objective, "max_primal_violation": violation,
            "invalid_or_undefined": undefined[:20], "selected_disjuncts": selected,
            "selected_booleans": booleans}


def solve_method(template, method, directory, config, deadline):
    global CONTEXT
    directory = Path(directory)
    started = monotonic()
    policy = solver_policy(config, method)
    CONTEXT = SolveContext(config["executable"], directory, deadline, config["relative_gap"],
                           baron_options=baron_options(config),
                           strict_subproblems=policy.get("nlp") == "baron")
    if template.metadata["case"] == "column" and method == "hull":
        # BARON's linear range reduction falsely rejected a feasible Column Hull
        # model in local validation. Keep the model unchanged and record this
        # explicit numerical workaround; the CLI permits the stock setting too.
        CONTEXT.baron_options += (f"LBTTDo {config.get('baron_column_hull_lbtt', 0)}",)
    report = {**template.metadata, "method": method, "time_limit_s": config["time_limit"],
              "threads": 1, "status": "running", "objective": None,
              "has_feasible_solution": False, "global_optimality_certified": False,
              "global_bound_valid": method in {"bigm", "hull"},
              "solver_policy": {**policy, **({"options": list(CONTEXT.baron_options)}
                                  if "baron" in policy.values() else {})},
              "certificate_note": "Local IPOPT subproblems: GDPopt bounds/termination do not certify global optimality."
                                  if policy.get("nlp") == "ipopt" else
                                  "BARON subproblems: GDPopt bounds and global certificate require a separate audit."
                                  if method in {"ric", "gloa"} else
                                  "Certificate requires BARON optimal termination and original GDP feasibility."}
    report_path = directory / "result.json"
    save_json(report_path, report)
    reference = template.model.clone()
    original_logic = list(reference.component_data_objects(
        pyo.LogicalConstraint, active=True, descend_into=DESCEND))
    # Materialize associated binaries on the validation copy too, without fixing them.
    pyo.TransformationFactory("core.logical_to_linear").apply_to(reference)
    # Keep original logical constraints available for independent validation.
    for c in original_logic:
        c.activate()
    model = template.model.clone()

    def record_incumbent(candidate, event, iteration=None):
        transfer_values(candidate, reference)
        checked = validate_original(reference)
        event_record = {"event": event, "iteration": iteration, "elapsed_s": monotonic() - started,
                        **checked}
        append_event(directory / "incumbents.jsonl", event_record)
        if checked["has_feasible_solution"] and (
                report["objective"] is None or checked["candidate_objective"] < report["objective"]):
            report.update(checked, objective=checked["candidate_objective"],
                          incumbent_elapsed_s=event_record["elapsed_s"])
            values = {v.name: v.value for v in reference.component_data_objects(pyo.Var, descend_into=DESCEND)
                      if finite(v.value) is not None}
            save_json(directory / "solution.json", {"objective": report["objective"], "variables": values,
                                                     "validation": checked})
            save_json(report_path, report)

    try:
        before = monotonic()
        reformulate(model, method)
        report["reformulation_wall_s"] = monotonic() - before
        report["model_variables"] = sum(1 for _ in model.component_data_objects(pyo.Var, descend_into=DESCEND))
        report["model_constraints"] = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True, descend_into=DESCEND))
        solve_started = monotonic()
        if method in {"bigm", "hull"}:
            result = TimedGAMS().solve(model, solver="baron", mtype="minlp")
        else:
            def feasible(solver, subproblem, util):
                record_incumbent(subproblem, "gdpopt_feasible_subproblem", solver.iteration)

            algorithm = pyo.SolverFactory("gdpopt." + method)
            result = algorithm.solve(
                model, time_limit=max(1, int(CONTEXT.remaining())), tee=True,
                mip_solver=SOLVER_NAME, nlp_solver=SOLVER_NAME,
                mip_solver_args={"solver": policy["mip"], "mtype": "mip"},
                nlp_solver_args={"solver": policy["nlp"], "mtype": "nlp"},
                force_subproblem_nlp=True, init_algorithm="set_covering",
                bound_tolerance=config["relative_gap"],
                call_after_subproblem_feasible=feasible)
            report["gdpopt_iterations"] = algorithm.iteration
        report["solve_wall_s"] = monotonic() - solve_started
        record_incumbent(model, "final_model")
        termination = str(result.solver.termination_condition)
        report.update(status="finished", termination=termination,
                      solver_status=str(result.solver.status),
                      reported_lower_bound=finite(result.problem.lower_bound),
                      reported_upper_bound=finite(result.problem.upper_bound))
        if method in {"bigm", "hull"} and CONTEXT.calls:
            stats = CONTEXT.calls[-1].get("gams_statistics", {})
            report["gams_statistics"] = stats
            report["global_optimality_certified"] = bool(
                report["has_feasible_solution"] and stats.get("SOLVESTAT") == 1 and stats.get("MODELSTAT") == 1)
    except IncompleteSubproblem as error:
        if error.model is not None:
            record_incumbent(error.model, "incomplete_subproblem")
        report.update(status="time_limit" if error.call["termination"] == "maxTimeLimit"
                      else "subproblem_incomplete", termination=error.call["termination"],
                      incomplete_subproblem_call=error.call["index"], message=str(error))
    except BudgetExpired as error:
        report.update(status="time_limit", termination="maxTimeLimit", message=str(error))
    except Exception as error:
        import traceback
        traceback.print_exc()
        report.update(status="error", termination="error", message=f"{type(error).__name__}: {error}")
    finally:
        if "solve_started" in locals():
            report.setdefault("solve_wall_s", monotonic() - solve_started)
        report.update(method_wall_s=monotonic() - started, solver_calls=len(CONTEXT.calls),
                      sum_solver_call_wall_s=sum(c["wall_s"] for c in CONTEXT.calls))
        save_json(report_path, report)
    return report


def smoke_solvers(executable, directory, solvers=("ipopt", "cplex", "baron"), *, config=None):
    """Actual tiny MIP/NLP/MINLP solves; version/availability alone are insufficient."""
    global CONTEXT
    output = {}
    for name in solvers:
        path = Path(directory) / name
        path.mkdir(parents=True, exist_ok=True)
        CONTEXT = SolveContext(executable, path, monotonic() + 30,
                               baron_options=baron_options(config or {}))
        model = pyo.ConcreteModel()
        model.x = pyo.Var(bounds=(0, 3), initialize=0.5)
        if name == "baron_nlp":
            # Boundary local minimum x=0 (f=0), global minimum
            # x=(3+sqrt(3))/2. Test actual nonconvex continuous NLP support.
            model.obj = pyo.Objective(expr=model.x**4 - 4*model.x**3 + 3*model.x**2)
        elif name == "ipopt":
            model.obj = pyo.Objective(expr=(model.x - 1) ** 2)
        else:
            model.y = pyo.Var(domain=pyo.Binary)
            model.c = pyo.Constraint(expr=model.x >= 1 + model.y)
            model.obj = pyo.Objective(expr=model.x + model.y if name in {"cplex", "highs"} else model.x**2 + model.y)
        result = TimedGAMS().solve(model, solver="baron" if name == "baron_nlp" else name,
                                  mtype={"ipopt": "nlp", "baron_nlp": "nlp", "cplex": "mip",
                                         "highs": "mip", "baron": "minlp"}[name])
        expected = 0 if name == "ipopt" else 1
        if name == "baron_nlp":
            x = (3 + math.sqrt(3)) / 2
            expected = x**4 - 4*x**3 + 3*x**2
        stats = CONTEXT.calls[-1].get("gams_statistics", {})
        complete = subproblem_complete(CONTEXT.calls[-1], CONTEXT.relative_gap) if name.startswith("baron") else (
            stats.get("SOLVESTAT") == 1 and stats.get("MODELSTAT") in {1, 2})
        if not complete or abs(pyo.value(model.obj)-expected) > 1e-5:
            raise RuntimeError(f"GAMS/{name} execution/license test failed: {result.solver}")
        output[name] = CONTEXT.calls[-1]
    return output
