"""Independent original-GDP checks and at most two bounded W03 NLP polishes."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

from review_comparison.common import writecsv
from .common import ROOT, bounded, environment, outputs, read, save, sha


def restore(solution):
    from gdp_models.comparison import (
        DESCEND,
        build_template,
        pyo,
        update_boolean_vars_from_binary,
    )

    template = build_template("cstr", cstr_size=15)
    m = template.model
    logic = list(
        m.component_data_objects(
            pyo.LogicalConstraint, active=True, descend_into=DESCEND
        )
    )
    pyo.TransformationFactory("core.logical_to_linear").apply_to(m)
    for c in logic:
        c.activate()
    for var in m.component_data_objects(pyo.Var, descend_into=DESCEND):
        if not var.fixed:
            var.set_value(None)
    for name, value in solution["variables"].items():
        var = m.find_component(name)
        if var is None:
            raise ValueError("Saved variable absent from pinned GDP: " + name)
        var.set_value(value, skip_validation=True)
    update_boolean_vars_from_binary(m, integer_tolerance=1e-8)
    return m, template.metadata


def vector(model):
    from gdp_models.comparison import DESCEND, pyo

    return {
        "variables": {
            v.name: v.value
            for v in model.component_data_objects(pyo.Var, descend_into=DESCEND)
        },
        "booleans": {
            v.name: v.value
            for v in model.component_data_objects(pyo.BooleanVar, descend_into=DESCEND)
        },
    }


def configuration(model):
    from gdp_models.comparison import DESCEND, pyo

    return {
        v.name: v.value
        for v in model.component_data_objects(pyo.Var, descend_into=DESCEND)
        if v.is_integer()
    }


def independent_check(model, tolerance, expected_configuration=None):
    """Never use solver termination to decide numerical primal feasibility."""
    from gdp_models.comparison import pyo
    from pyomo.gdp import Disjunct, Disjunction

    constraints, bounds, integrality, logical, disjunctions, undefined = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    active_names = []

    def residual(expr, lo, hi, name, kind):
        v = pyo.value(expr, exception=False)
        if v is None or not math.isfinite(float(v)):
            undefined.append(name)
            return {
                "name": name,
                "kind": kind,
                "value": None,
                "lower": None,
                "upper": None,
                "violation": None,
            }
        lo = None if lo is None else float(pyo.value(lo))
        hi = None if hi is None else float(pyo.value(hi))
        return {
            "name": name,
            "kind": kind,
            "value": float(v),
            "lower": lo,
            "upper": hi,
            "violation": max(
                0.0, 0.0 if lo is None else lo - v, 0.0 if hi is None else v - hi
            ),
        }

    def walk(block):
        for v in block.component_data_objects(pyo.Var, active=True, descend_into=False):
            if v.value is not None:
                bounds.append(residual(v, v.lb, v.ub, v.name, "bound"))
                if v.is_integer():
                    integrality.append(
                        {
                            "name": v.name,
                            "value": v.value,
                            "violation": abs(v.value - round(v.value)),
                        }
                    )
        for c in block.component_data_objects(
            pyo.Constraint, active=True, descend_into=False
        ):
            constraints.append(residual(c.body, c.lower, c.upper, c.name, "constraint"))
            active_names.append(c.name)
        for c in block.component_data_objects(
            pyo.LogicalConstraint, active=True, descend_into=False
        ):
            try:
                valid = pyo.value(c.body, exception=False) is True
            except (ValueError, TypeError):
                valid = False
            logical.append({"name": c.name, "valid": valid})
        for d in block.component_data_objects(
            Disjunction, active=True, descend_into=False
        ):
            values = [v.binary_indicator_var.value for v in d.disjuncts]
            valid = all(v is not None and math.isfinite(v) for v in values)
            violation = (
                max(
                    abs(sum(values) - 1) if d.xor else max(0, 1 - sum(values)),
                    *(abs(v - round(v)) for v in values),
                )
                if valid
                else None
            )
            disjunctions.append(
                {"name": d.name, "indicator_values": values, "violation": violation}
            )
            if not valid:
                undefined.append(d.name)
        for child in block.component_data_objects(
            pyo.Block, active=True, descend_into=False
        ):
            walk(child)
        for child in block.component_data_objects(
            Disjunct, active=True, descend_into=False
        ):
            val = child.binary_indicator_var.value
            if val is None:
                undefined.append(child.name)
            elif val > 0.5:
                walk(child)

    walk(model)
    rows = constraints + bounds + integrality + disjunctions
    max_violation = max(
        [float(r["violation"]) for r in rows if r.get("violation") is not None] + [0.0]
    )
    objective = pyo.value(model.obj, exception=False)
    if objective is None or not math.isfinite(objective):
        objective = None
        undefined.append("objective")
    current = configuration(model)
    same = expected_configuration is None or current == expected_configuration
    logic_valid = all(r["valid"] for r in logical)
    passed = (
        objective is not None
        and not undefined
        and logic_valid
        and same
        and max_violation <= tolerance
    )
    return {
        "objective": objective,
        "maximum_unscaled_primal_violation": max_violation,
        "tolerance": tolerance,
        "numerically_feasible_under_stated_residual_test": passed,
        "configuration_matches": same,
        "discrete_configuration": current,
        "logic_valid": logic_valid,
        "undefined": undefined,
        "constraints": constraints,
        "bounds": bounds,
        "integrality": integrality,
        "disjunctions": disjunctions,
        "logic": logical,
        "active_constraint_names": sorted(active_names),
        "largest_residuals": sorted(
            constraints + bounds, key=lambda r: r["violation"] or 0, reverse=True
        )[:20],
    }


def prepare_fixed_nlp(reference):
    from gdp_models.comparison import pyo, DESCEND

    m = reference.clone()
    for v in m.component_data_objects(pyo.BooleanVar, descend_into=DESCEND):
        if v.value is not None:
            v.fix(v.value)
    for v in m.component_data_objects(pyo.Var, descend_into=DESCEND):
        if v.is_integer():
            if v.value is None or abs(v.value - round(v.value)) > 1e-8:
                raise ValueError("Missing/nonintegral discrete value: " + v.name)
            v.fix(round(v.value))
    # The equivalent algebraic logical_to_linear rows already exist.
    # Deactivate their Boolean originals BEFORE fixing disjuncts to avoid a second encoding.
    for c in m.component_objects(pyo.LogicalConstraint, descend_into=DESCEND):
        c.deactivate()
    pyo.TransformationFactory("gdp.fix_disjuncts").apply_to(m)
    if not any(
        not v.fixed and not v.is_integer()
        for v in m.component_data_objects(pyo.Var, descend_into=DESCEND)
    ):
        raise ValueError("No free continuous variables")
    before = set(independent_check(reference, 1e-5)["active_constraint_names"])
    after = {
        c.name
        for c in m.component_data_objects(
            pyo.Constraint, active=True, descend_into=True
        )
    }
    if before != after:
        raise ValueError(
            f"Fixed NLP changed active algebraic constraints: missing={before - after}, extra={after - before}"
        )
    return m


def verify_input(directory):
    s = read(directory / "selection.json")
    if (
        sha(directory / "selection.json")
        != read(directory / "manifest.json")["selection_sha256"]
    ):
        raise ValueError("Selection manifest changed")
    f = s["feasibility"]
    for path, digest in f["inputs_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError("Input changed: " + path)
    w = f["witness"]
    a = f["audit"]
    audit = ROOT / "reproduction/data/algebraic_audit"
    original = read(audit / w["solution_local_path"])
    if sha(audit / w["solution_local_path"]) != w["solution_sha256"]:
        raise ValueError("W03 hash mismatch")
    expected_archive = read(audit / "manifest.json")["sources"][w["source_alias"]][
        "sha256"
    ]
    if sha(ROOT / w["archive"]) != expected_archive:
        raise ValueError("Witness execution archive hash mismatch")
    m, metadata = restore(original)
    with zipfile.ZipFile(ROOT / w["archive"]) as z:
        root = w["result_archive_member"].split("/")[0]
        historical = json.loads(z.read(root + "/run.json"))
        expected = historical["runtime"]["templates"]["cstr_15"]["source"]
        if metadata["source"] != expected:
            raise ValueError("Pinned model source differs from witness execution")
        wrappers = {
            n: {
                "historical_sha256": hashlib.sha256(
                    z.read(root + "/source/" + n)
                ).hexdigest(),
                "current_sha256": sha(ROOT / n),
            }
            for n in (
                "gdp_models/models.py",
                "gdp_models/comparison.py",
                "gdp_models/_sources.py",
            )
        }
    from gdp_models.comparison import validate_original

    retained_check = validate_original(m)
    checked = independent_check(m, 1e-5)
    if (
        not checked["numerically_feasible_under_stated_residual_test"]
        or not retained_check["has_feasible_solution"]
    ):
        raise ValueError("Original witness recheck failed; solver calls prohibited")
    if not math.isclose(
        checked["objective"],
        float(w["reevaluated_objective"]),
        abs_tol=1e-12,
        rel_tol=1e-12,
    ):
        raise ValueError("Original objective differs from audit")
    if not math.isclose(
        checked["maximum_unscaled_primal_violation"],
        float(w["max_primal_violation"]),
        abs_tol=1e-12,
        rel_tol=1e-8,
    ):
        raise ValueError("Original residual differs from audit")
    return (
        m,
        checked,
        {
            "model": metadata["source"],
            "wrapper_source_comparison": wrappers,
            "original_validation": retained_check,
            "lower_bound": float(a["reported_lower_bound"]),
            "historical_audit_tolerance": float(a["tolerance"]),
            "original_solution_sha256": w["solution_sha256"],
        },
    )


def polish_worker(directory, attempt, executable):
    from gdp_models.comparison import pyo, DESCEND, transfer_values

    dest = directory / "feasibility" / f"attempt_{attempt}"
    if (dest / "solver_call.json").exists():
        raise FileExistsError("This solver attempt was already invoked")
    if attempt == 2:
        first = read(directory / "feasibility/attempt_1/result.json")
        if (
            first["error"]
            or not first["solution_loaded"]
            or first["new_witness_available"]
        ):
            raise ValueError(
                "A second call requires a returned point that failed the residual target"
            )
    reference, before, provenance = verify_input(directory)
    # Second attempt starts from the first returned continuous point, with W03's discrete configuration.
    if attempt == 2:
        path = directory / "feasibility/attempt_1/solution.json"
        if path.exists():
            reference, _ = restore(read(path))
    nlp = prepare_fixed_nlp(reference)
    target = 1e-8 if attempt == 1 else 1e-10
    solver_tolerance = 1e-10 if attempt == 1 else 1e-12
    options = {
        "tol": solver_tolerance,
        "constr_viol_tol": solver_tolerance,
        "acceptable_iter": 0,
        "bound_relax_factor": 0.0,
        "honor_original_bounds": "yes",
        "nlp_scaling_method": "none",
        "max_cpu_time": 290,
        "max_iter": 3000,
    }
    # Older AMPL drivers expose only a subset of IPOPT options as command keywords.
    # The native options file accepts acceptable_iter without that driver restriction.
    option_file = (dest / "ipopt.opt").resolve()
    option_file.write_text(
        "".join(f"{key} {value}\n" for key, value in options.items())
    )
    interface_options = {"option_file_name": str(option_file)}
    save(
        dest / "settings.json",
        {
            "target_original_unscaled_violation": target,
            "solver_options": options,
            "interface_options": interface_options,
            "option_file_sha256": sha(option_file),
            "objective": "unchanged original CSTR objective",
            "continuous_start": "W03"
            if attempt == 1
            else "attempt 1 returned point, otherwise W03",
            "fixed_discrete": configuration(reference),
            "free_continuous_variables": sum(
                not v.fixed and not v.is_integer()
                for v in nlp.component_data_objects(pyo.Var, descend_into=DESCEND)
            ),
            "active_constraint_set_preserved": True,
        },
    )
    # Record intent immediately before the single allowed solver call in this worker.
    save(
        dest / "solver_call.json",
        {
            "solver": "ipopt",
            "call_started": True,
            "executable": executable,
            "sha256": sha(executable),
            "options": options,
            "interface_options": interface_options,
        },
    )
    start = time.monotonic()
    termination, status, error, loaded = None, None, None, False
    try:
        result = pyo.SolverFactory("ipopt", executable=executable).solve(
            nlp,
            options=interface_options,
            tee=True,
            load_solutions=False,
            logfile=str(dest / "ipopt.log"),
        )
        termination = str(result.solver.termination_condition)
        status = str(result.solver.status)
        if len(result.solution):
            nlp.solutions.load_from(result)
            loaded = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - start
    transfer_values(nlp, reference)
    checked = independent_check(
        reference, target, expected_configuration=before["discrete_configuration"]
    )
    save(
        dest / "solution.json", {"objective": checked["objective"], **vector(reference)}
    )
    save(dest / "residuals.json", checked)
    save(
        dest / "result.json",
        {
            "solver_status": status,
            "termination": termination,
            "error": error,
            "solution_loaded": loaded,
            "solve_wall_s": elapsed,
            "independent_residual_check": checked[
                "numerically_feasible_under_stated_residual_test"
            ],
            "new_witness_available": loaded
            and checked["numerically_feasible_under_stated_residual_test"],
            "objective": checked["objective"],
            "maximum_unscaled_primal_violation": checked[
                "maximum_unscaled_primal_violation"
            ],
            "target": target,
            "lower_bound": provenance["lower_bound"],
            "lower_bound_minus_original_objective": None
            if checked["objective"] is None
            else provenance["lower_bound"] - checked["objective"],
        },
    )


def run(directory, executable):
    output = directory / "feasibility"
    output.mkdir(exist_ok=False)
    m, before, provenance = verify_input(directory)
    save(
        output / "before_solution.json", {"objective": before["objective"], **vector(m)}
    )
    save(output / "before_residuals.json", before)
    save(output / "provenance.json", {"environment": environment(), **provenance})
    rows = []

    def row(
        label, obj, residual, target, available, solver_status=None, termination=None
    ):
        gap = provenance["lower_bound"] - obj if obj is not None else None
        tolerance = 1e-5 * max(1, abs(obj)) if obj is not None else None
        return {
            "witness": label,
            "original_objective": obj,
            "maximum_unscaled_primal_violation": residual,
            "residual_target": target,
            "numerically_feasible_under_stated_residual_test": available,
            "reported_gloa_lower_bound": provenance["lower_bound"],
            "bound_minus_witness": gap,
            "original_audit_tolerance": tolerance,
            "bound_gap_over_tolerance": gap / tolerance if gap is not None else None,
            "original_audit_conflict": gap > tolerance if gap is not None else None,
            "solver_status": solver_status,
            "termination": termination,
        }

    rows.append(
        row(
            "original_W03",
            before["objective"],
            before["maximum_unscaled_primal_violation"],
            1e-5,
            True,
        )
    )
    calls = []
    solver = shutil.which(executable) if executable else shutil.which("ipopt")
    if solver:
        solver = str(Path(solver).resolve())
        version = subprocess.run(
            [solver, "-v"], text=True, capture_output=True, timeout=10
        )
        save(
            output / "solver_version.json",
            {
                "path": solver,
                "sha256": sha(solver),
                "stdout": version.stdout,
                "stderr": version.stderr,
                "returncode": version.returncode,
            },
        )
        for attempt in (1, 2):
            dest = output / f"attempt_{attempt}"
            dest.mkdir()
            command = [
                sys.executable,
                "-m",
                "review_diagnostics.feasibility",
                "--directory",
                str(directory),
                "--worker",
                "--attempt",
                str(attempt),
                "--ipopt",
                solver,
            ]
            result = bounded(command, dest / "worker.log", 300)
            calls.append(result)
            save(dest / "execution.json", result)
            if (dest / "result.json").exists():
                r = read(dest / "result.json")
                rows.append(
                    row(
                        f"polished_attempt_{attempt}",
                        r["objective"],
                        r["maximum_unscaled_primal_violation"],
                        r["target"],
                        r["new_witness_available"],
                        r["solver_status"],
                        r["termination"],
                    )
                )
                if r["new_witness_available"]:
                    break
            # Do not repeat an environment/setup error or a timed-out call automatically.
            if (
                result["timed_out"]
                or not (dest / "solver_call.json").exists()
                or not (dest / "result.json").exists()
                or r["error"] is not None
                or not r["solution_loaded"]
            ):
                break
    writecsv(output / "before_after.csv", rows)
    save(
        output / "manifest.json",
        {
            "status": "completed"
            if len(rows) > 1
            and rows[-1]["numerically_feasible_under_stated_residual_test"]
            else "incomplete",
            "selection_sha256": sha(directory / "selection.json"),
            "nlp_calls": sum(
                (output / f"attempt_{i}/solver_call.json").exists() for i in (1, 2)
            ),
            "executions": calls,
            "reason_if_not_run": None if solver else "No IPOPT executable found",
            "interpretation": "Numerically feasible under the stated residual test only; no exact-feasibility, global-optimality or mathematical bound-invalidity proof.",
            "environment": environment(),
            "outputs_sha256": outputs(output),
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", required=True, type=Path)
    p.add_argument("--ipopt", default="ipopt")
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--attempt", type=int, choices=(1, 2), default=1)
    args = p.parse_args()
    if args.worker:
        polish_worker(args.directory.resolve(), args.attempt, args.ipopt)
    else:
        run(args.directory.resolve(), args.ipopt)


if __name__ == "__main__":
    main()
