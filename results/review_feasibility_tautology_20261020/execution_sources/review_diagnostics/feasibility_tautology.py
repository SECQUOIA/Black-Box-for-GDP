"""Remove three proved fixed-Boolean identities, then allow one local NLP call."""

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import math
from numbers import Real
from pathlib import Path
import shutil
import subprocess
import sys
import time

from review_comparison.common import writecsv
from . import feasibility as f
from . import feasibility_followup as prior
from .common import ROOT, bounded, environment, read, save, sha

CANDIDATES = tuple(f"logic_to_linear.transformed_constraints[{i}]" for i in (16, 17, 18))
SOURCES = (*prior.SOURCE_PATHS, "review_diagnostics/feasibility_tautology.py")
OPTIONS = {
    "tol": 1e-10, "constr_viol_tol": 1e-10, "acceptable_iter": 0,
    "bound_relax_factor": 0.0, "honor_original_bounds": "yes",
    "nlp_scaling_method": "none", "max_cpu_time": 290, "max_iter": 3000,
}


def inventory(model):
    from gdp_models.comparison import pyo, DESCEND

    return {
        "variables": {v.name: {"value": v.value, "fixed": v.fixed, "lower": v.lb, "upper": v.ub, "domain": str(v.domain)} for v in model.component_data_objects(pyo.Var, descend_into=DESCEND)},
        "booleans": {v.name: {"value": v.value, "fixed": v.fixed} for v in model.component_data_objects(pyo.BooleanVar, descend_into=DESCEND)},
        "constraints": {c.name: {"active": c.active, "expression": str(c.expr), "equality": c.equality} for c in model.component_data_objects(pyo.Constraint, active=None, descend_into=DESCEND)},
        "logic": {c.name: {"active": c.active, "expression": str(c.expr)} for c in model.component_data_objects(pyo.LogicalConstraint, active=None, descend_into=DESCEND)},
        "objectives": {o.name: {"active": o.active, "sense": int(o.sense), "expression": str(o.expr)} for o in model.component_data_objects(pyo.Objective, active=None, descend_into=DESCEND)},
    }


def exact_value(expr):
    """Evaluate the supported arithmetic with rational constants, without tolerance."""
    from pyomo.core.expr.numeric_expr import SumExpression, ProductExpression, NegationExpression
    from gdp_models.comparison import pyo

    if isinstance(expr, Real):
        if not math.isfinite(expr):
            raise ValueError("Undefined/nonfinite exact constant")
        return Fraction(expr)
    if expr.is_variable_type():
        if not expr.fixed or expr.value not in (0, 1):
            raise ValueError("Variable is not fixed to exact 0 or 1: " + expr.name)
        return Fraction(expr.value)
    if isinstance(expr, SumExpression):
        return sum((exact_value(arg) for arg in expr.args), Fraction(0))
    if isinstance(expr, ProductExpression):
        return math.prod(exact_value(arg) for arg in expr.args)
    if isinstance(expr, NegationExpression):
        return -exact_value(expr.args[0])
    if expr.is_constant() or expr.is_parameter_type():
        return exact_value(pyo.value(expr))
    raise ValueError("Cannot prove exact identity for expression: " + str(expr))


def prove_identities(model):
    from gdp_models.comparison import pyo, DESCEND
    from pyomo.core.expr.visitor import identify_variables

    booleans = {id(b.get_associated_binary()): b for b in model.component_data_objects(pyo.BooleanVar, descend_into=DESCEND) if b.get_associated_binary() is not None}
    proofs = []
    for name in CANDIDATES:
        constraint = model.find_component(name)
        if constraint is None or not constraint.active or not constraint.equality:
            raise ValueError("Expected active equality: " + name)
        variables = list(identify_variables(constraint.expr, include_fixed=True))
        if not variables:
            raise ValueError("Expected associated fixed Boolean variables: " + name)
        records = []
        for v in variables:
            boolean = booleans.get(id(v))
            if (
                not v.is_binary() or not v.fixed or v.value not in (0, 1)
                or boolean is None or not boolean.fixed
                or boolean.value not in (True, False)
                or int(boolean.value) != v.value
            ):
                raise ValueError("Not an exact fixed associated Boolean: " + v.name)
            records.append({"binary": v.name, "binary_fixed": v.fixed, "binary_value": v.value, "boolean": boolean.name, "boolean_fixed": boolean.fixed, "boolean_value": boolean.value})
        lower, body, upper = (exact_value(e) for e in (constraint.lower, constraint.body, constraint.upper))
        if (lower, body, upper) != (Fraction(1), Fraction(1), Fraction(1)):
            raise ValueError("Not exactly 1=1; false or tolerance-only equality: " + name)
        proofs.append({"name": name, "expression": str(constraint.expr), "variables": records, "exact_lower": str(lower), "exact_body": str(body), "exact_upper": str(upper), "tolerance_used": 0})
    return proofs


def preprocess(reference):
    """Keep the original GDP untouched; deactivate exactly the three proved rows."""
    original = inventory(reference)
    nlp = f.prepare_fixed_nlp(reference)
    before = inventory(nlp)
    proofs = prove_identities(nlp)  # Check all candidates before mutating anything.
    for name in CANDIDATES:
        nlp.find_component(name).deactivate()
    after = inventory(nlp)
    expected = {**before, "constraints": {name: {**row, "active": False} if name in CANDIDATES else row for name, row in before["constraints"].items()}}
    if after != expected or inventory(reference) != original:
        raise ValueError("Preprocessing changed more than the three proved identities")
    return nlp, {"original_GDP_unchanged": True, "original_GDP_inventory": original, "before": before, "after": after, "omitted_identities": proofs, "remaining_constraints_identical": True, "variables_bounds_starts_fixing_and_objective_identical": True, "active_constraint_sets_identical": False}


def nl_info(path):
    lines = path.read_text().splitlines()
    values = [int(x) for x in lines[1].split("#")[0].split()]
    return {"variables": values[0], "constraints": values[1], "objectives": values[2], "equalities": values[4], "rows": path.with_suffix(".row").read_text().splitlines(), "columns": path.with_suffix(".col").read_text().splitlines(), "sha256": sha(path)}


def write_nl(model, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Disable generic presolve/trivial-row removal: only our three rows may disappear.
    _, smap = model.write(str(path), format="nl", io_options={"symbolic_solver_labels": True, "skip_trivial_constraints": False, "linear_presolve": False})
    return smap, nl_info(path)


def check_nl_change(before, after):
    if (before["variables"], before["equalities"], after["variables"], after["equalities"]) != (156, 158, 156, 155):
        raise ValueError("Unexpected NL counts; solver invocation prohibited")
    if before["columns"] != after["columns"]:
        raise ValueError("NL variable ordering changed")
    if set(before["rows"]) - set(after["rows"]) != set(CANDIDATES) or set(after["rows"]) - set(before["rows"]):
        raise ValueError("NL row difference is not exactly the three identities")
    if before["constraints"] - after["constraints"] != len(CANDIDATES):
        raise ValueError("Additional NL rows were removed")


def original_check(nlp, expected_configuration):
    restored, _ = f.restore(f.vector(nlp))
    check = f.independent_check(restored, 1e-8, expected_configuration)
    omitted = []
    for name in CANDIDATES:
        row = next((r for r in check["constraints"] if r["name"] == name), None)
        constraint = restored.find_component(name)
        omitted.append({"name": name, "active_on_original_GDP": bool(constraint is not None and constraint.active), "independently_checked": row is not None, "violation": row["violation"] if row else None})
    if not all(r["active_on_original_GDP"] and r["independently_checked"] and r["violation"] == 0 for r in omitted):
        check["numerically_feasible_under_stated_residual_test"] = False
    check["omitted_identities_rechecked_on_original_GDP"] = omitted
    return restored, check


def load_returned(model, result, symbol_map_id):
    """Load only a complete actual solver vector using the prewritten NL symbol map."""
    if not len(result.solution):
        return False
    symbol_map = model.solutions.symbol_map[symbol_map_id]
    expected = {label for label, obj in symbol_map.bySymbol.items() if obj.is_variable_type() and not obj.fixed}
    values = result.solution(0).variable
    if not expected.issubset(values) or any(not math.isfinite(values[label]["Value"]) for label in expected):
        raise ValueError("Incomplete/nonfinite returned solver vector")
    # This is the same mapping used by Pyomo when solve() receives a model.
    result._smap_id = symbol_map_id
    model.solutions.load_from(result)
    return True


def source_hashes():
    return {name: sha(ROOT / name) for name in SOURCES}


def prepare(input_directory, output, executable):
    output.mkdir(parents=True, exist_ok=False)
    prior_report = prior.verify(input_directory)
    reference, before, provenance = f.verify_input(input_directory)
    selection = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "feasibility": read(input_directory / "selection.json")["feasibility"],
        "prior_directory": str(input_directory), "prior_manifest_sha256": sha(input_directory / "manifest.json"),
        "new_NLP_call_limit": 1, "external_wall_limit_s": 300,
        "target_original_GDP_unscaled_violation": 1e-8,
        "candidate_identities": list(CANDIDATES), "solver_options": OPTIONS,
        "source_sha256": source_hashes(), "environment": environment(),
        "historical_execution_provider_revision": read(input_directory / "selection.json")["original_execution_provider_revision"],
    }
    solver = Path(executable).resolve(strict=True)
    prior_solver = read(input_directory / "selection.json")["solver"]
    if sha(solver) != prior_solver["sha256"]:
        raise ValueError("Solver binary differs from previous local invocation")
    version = subprocess.run([str(solver), "-v"], text=True, capture_output=True, timeout=10, check=True)
    selection["solver"] = {"path": str(solver), "sha256": sha(solver), "version": version.stdout}
    save(output / "selection.json", selection)
    save(output / "manifest.json", {"selection_sha256": sha(output / "selection.json"), "status": "preflight"})
    for name in SOURCES:
        dest = output / "execution_sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    save(output / "prior_reverification.json", prior_report)
    save(output / "before_solution.json", {"objective": before["objective"], **f.vector(reference)})
    save(output / "before_residuals.json", before)
    save(output / "provenance.json", provenance)
    nlp, proof = preprocess(reference)
    save(output / "preprocessing.json", proof)
    _, before_nl = write_nl(f.prepare_fixed_nlp(reference), output / "nl_before/model.nl")
    _, after_nl = write_nl(nlp, output / "nl_after/model.nl")
    check_nl_change(before_nl, after_nl)
    save(output / "nl_comparison.json", {"before": before_nl, "after": after_nl, "exactly_three_rows_removed": True})
    options_file = output / "ipopt.opt"
    options_file.write_text("".join(f"{key} {value}\n" for key, value in OPTIONS.items()))
    if options_file.read_bytes() != (input_directory / "feasibility/attempt_1/ipopt.opt").read_bytes():
        raise ValueError("Native options differ from previous attempt")
    save(output / "preflight.json", {"passed": True, "NLP_calls": 0, "selection_sha256": sha(output / "selection.json"), "options_sha256": sha(options_file), "NL_files_sha256": {str(p.relative_to(output)): sha(p) for folder in ("nl_before", "nl_after") for p in (output / folder).iterdir()}})
    return str(solver)


def worker(directory):
    from gdp_models.comparison import pyo

    marker = directory / "solver_call.json"
    if marker.exists():
        raise FileExistsError("This allocation already has a solver call")
    selection = read(directory / "selection.json")
    if source_hashes() != selection["source_sha256"]:
        raise ValueError("Execution source changed after preflight")
    preflight = read(directory / "preflight.json")
    if sha(directory / "ipopt.opt") != preflight["options_sha256"]:
        raise ValueError("Native options changed after preflight")
    for path, digest in preflight["NL_files_sha256"].items():
        if sha(directory / path) != digest:
            raise ValueError("Preflight NL file changed")
    reference, before, provenance = f.verify_input(directory)
    nlp, proof = preprocess(reference)
    if proof != read(directory / "preprocessing.json"):
        raise ValueError("Preprocessing differs from frozen proof")
    actual_file = directory / "solver_input/model.nl"
    smap, actual_nl = write_nl(nlp, actual_file)
    if actual_nl != read(directory / "nl_comparison.json")["after"]:
        raise ValueError("Actual solver input differs from verified NL")
    solver = selection["solver"]["path"]
    if sha(solver) != selection["solver"]["sha256"]:
        raise ValueError("Solver binary changed")
    interface_options = {"option_file_name": str((directory / "ipopt.opt").resolve())}
    call = {"started_utc": datetime.now(timezone.utc).isoformat(), "maximum_calls": 1, "source_sha256": source_hashes(), "selection_sha256": sha(directory / "selection.json"), "solver_sha256": sha(solver), "NL_sha256": sha(actual_file), "option_file_sha256": sha(directory / "ipopt.opt"), "interface_options": interface_options, "solver": solver, "NL_file": str(actual_file), "external_wall_limit_s": 300}
    # Exclusive creation makes duplicate worker invocations fail before solving.
    import json
    with marker.open("x") as stream:
        json.dump(call, stream, indent=2)
        stream.write("\n")
    start = time.monotonic()
    status = termination = message = error = None
    present = loaded = False
    check = None
    try:
        result = pyo.SolverFactory("ipopt", executable=solver).solve(
            str(actual_file), options=interface_options, load_solutions=False,
            tee=True, keepfiles=True, logfile=str(directory / "ipopt.log"),
        )
        status, termination, message = str(result.solver.status), str(result.solver.termination_condition), str(result.solver.message)
        present = bool(len(result.solution))
        loaded = load_returned(nlp, result, smap)
        if loaded:
            restored, check = original_check(nlp, before["discrete_configuration"])
            save(directory / "solution.json", {"objective": check["objective"], **f.vector(restored)})
            save(directory / "residuals.json", check)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    save(directory / "worker_result.json", {"solver_status": status, "termination": termination, "solver_message": message, "error": error, "returned_vector_present": present, "solution_loaded": loaded, "solve_and_check_wall_s": time.monotonic() - start, "lower_bound": provenance["lower_bound"], "independent_check_available": check is not None})


def assess(directory):
    provenance = read(directory / "provenance.json")
    before = read(directory / "before_residuals.json")
    result = read(directory / "worker_result.json") if (directory / "worker_result.json").exists() else {}
    check = read(directory / "residuals.json") if result.get("solution_loaded") and (directory / "residuals.json").exists() else None
    row = prior.comparison_row("tautology_followup", check, provenance["lower_bound"], bool(result.get("solution_loaded")), 1e-8, solver_status=result.get("solver_status"), termination=result.get("termination"), error=result.get("error"))
    summary = {"new_NLP_calls": int((directory / "solver_call.json").exists()), "previous_NLP_calls": 3, "new_call_limit": 1, "returned_solution": row["returned_solution"], "tightened_feasibility_passed": row["tightened_feasibility_passed"], "bound_discrepancy_persists": row["bound_discrepancy_persists"], "assessment": row, "execution": read(directory / "execution.json") if (directory / "execution.json").exists() else None, "new_FMQA_fits": 0, "new_SA_calls": 0, "benchmark_reruns": 0, "manuscript_modified": False}
    save(directory / "summary.json", summary)
    writecsv(directory / "before_after.csv", [prior.comparison_row("original_W03", before, provenance["lower_bound"], True, 1e-5), row])
    return summary


def seal(directory):
    manifest = read(directory / "manifest.json")
    manifest["outputs_sha256"] = prior.file_hashes(directory)
    manifest["status"] = "completed" if read(directory / "summary.json")["tightened_feasibility_passed"] else "incomplete"
    save(directory / "manifest.json", manifest)


def run(input_directory, output, executable):
    try:
        prepare(input_directory, output, executable)
    except FileExistsError:
        raise
    except Exception as exc:
        if output.exists():
            save(output / "preflight_failure.json", {"error": f"{type(exc).__name__}: {exc}", "new_NLP_calls": 0})
        raise
    execution = bounded([sys.executable, "-m", "review_diagnostics.feasibility_tautology", "worker", "--directory", str(output)], output / "worker.log", 300)
    save(output / "execution.json", execution)
    assess(output)
    seal(output)


def verify(directory):
    manifest = read(directory / "manifest.json")
    for path, digest in manifest["outputs_sha256"].items():
        if sha(directory / path) != digest:
            raise ValueError("Output hash mismatch: " + path)
    selection = read(directory / "selection.json")
    if source_hashes() != selection["source_sha256"]:
        raise ValueError("Current source differs from executed source")
    for path, digest in selection["source_sha256"].items():
        if sha(directory / "execution_sources" / path) != digest:
            raise ValueError("Execution source snapshot mismatch")
    prior_directory = Path(selection["prior_directory"])
    if sha(prior_directory / "manifest.json") != selection["prior_manifest_sha256"]:
        raise ValueError("Prior result manifest changed")
    prior.verify(prior_directory)
    reference, before, provenance = f.verify_input(directory)
    if before != read(directory / "before_residuals.json"):
        raise ValueError("Original W03 no longer reproduces")
    nlp, proof = preprocess(reference)
    if proof != read(directory / "preprocessing.json"):
        raise ValueError("Tautology proof or remaining constraints changed")
    info = read(directory / "nl_comparison.json")
    check_nl_change(nl_info(directory / "nl_before/model.nl"), nl_info(directory / "nl_after/model.nl"))
    if nl_info(directory / "solver_input/model.nl") != info["after"]:
        raise ValueError("Solver input differs from checked NL")
    summary = read(directory / "summary.json")
    if summary["new_NLP_calls"] != int((directory / "solver_call.json").exists()) or summary["new_NLP_calls"] > 1:
        raise ValueError("Call ledger mismatch")
    result = read(directory / "worker_result.json") if (directory / "worker_result.json").exists() else {}
    if summary["returned_solution"] != bool(result.get("solution_loaded")):
        raise ValueError("Loaded-solution flag mismatch")
    check = None
    if summary["returned_solution"]:
        restored, _ = f.restore(read(directory / "solution.json"))
        _, check = original_check(restored, before["discrete_configuration"])
        if check != read(directory / "residuals.json"):
            raise ValueError("Returned solution failed independent replay")
    elif (directory / "solution.json").exists():
        raise ValueError("No returned vector may be labeled a solution")
    row = prior.comparison_row("tautology_followup", check, provenance["lower_bound"], summary["returned_solution"], 1e-8)
    if any(summary["assessment"][k] != v for k, v in row.items()):
        raise ValueError("Assessment does not match independent validation")
    return {"verified": True, "new_solver_calls": 0, "original_and_previous_records_rechecked": True, "equivalence_proof_rechecked": True, "returned_point_rechecked": summary["returned_solution"], "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker", "verify", "seal"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--ipopt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == "run":
        if args.input is None or args.ipopt is None:
            parser.error("run requires --input and --ipopt")
        run(args.input.resolve(), directory, args.ipopt)
    elif args.action == "worker":
        worker(directory)
    elif args.action == "verify":
        if args.output is None or args.output.exists():
            parser.error("verify requires a new --output path")
        save(args.output, verify(directory))
    else:
        seal(directory)


if __name__ == "__main__":
    main()
