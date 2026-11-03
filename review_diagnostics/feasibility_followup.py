"""A separately authorized, at-most-two-call CSTR15 follow-up and solver-free replay."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
from pathlib import Path
import shutil
import subprocess
import sys

from review_comparison.common import writecsv
from . import feasibility as f
from .common import ROOT, bounded, environment, read, save, sha
from .replay import DEPENDENCIES, equivalent, residuals_match, sources_match

PRIOR = ROOT / "results/review_diagnostics_20261020"
SOURCE_PATHS = (
    *DEPENDENCIES,
    "review_diagnostics/feasibility_followup.py",
    "review_diagnostics/feasibility.py",
    "review_diagnostics/common.py",
    "review_comparison/common.py",
    "gdp_models/models.py",
    "gdp_models/comparison.py",
    "gdp_models/_sources.py",
)


def file_hashes(directory):
    return {
        str(p.relative_to(directory)): sha(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p != directory / "manifest.json"
    }


def fixed_model_check(reference, before):
    """Assert that only discrete fixing/GDP selection changes the NLP."""
    from gdp_models.comparison import DESCEND, pyo

    nlp = f.prepare_fixed_nlp(reference)
    variables = list(nlp.component_data_objects(pyo.Var, descend_into=DESCEND))
    for var in variables:
        original = reference.find_component(var.name)
        if (var.lb, var.ub) != (original.lb, original.ub):
            raise ValueError("Variable bounds changed: " + var.name)
        if var.is_integer():
            if not var.fixed or var.value != original.value:
                raise ValueError("Discrete configuration changed: " + var.name)
        elif var.fixed != original.fixed or var.value != original.value:
            raise ValueError("Continuous start/fixing changed: " + var.name)
    if str(nlp.obj.expr) != str(reference.obj.expr):
        raise ValueError("Original objective changed")
    return {
        "objective_preserved": True,
        "bounds_preserved": True,
        "continuous_start_and_fixing_preserved": True,
        "active_algebraic_constraints_preserved": True,
        "active_constraint_count": len(before["active_constraint_names"]),
        "free_continuous_variables": sum(
            not v.fixed and not v.is_integer() for v in variables
        ),
        "fixed_discrete_variables": sum(v.is_integer() for v in variables),
    }


def comparison_row(label, check, lower, returned, target, **extra):
    objective = check["objective"] if check else None
    gap = lower - objective if objective is not None else None
    tolerance = 1e-5 * max(1, abs(objective)) if objective is not None else None
    passed = bool(
        returned and check and check["numerically_feasible_under_stated_residual_test"]
    )
    return {
        "record": label,
        "returned_solution": returned,
        "objective": objective,
        "maximum_unscaled_primal_violation": check[
            "maximum_unscaled_primal_violation"
        ] if check else None,
        "worst_constraint": next(
            (r["name"] for r in check["largest_residuals"] if r["kind"] == "constraint"),
            None,
        ) if check else None,
        "residual_target": target,
        "numerically_feasible_under_stated_residual_test": passed,
        "tightened_feasibility_passed": passed and target <= 1e-8,
        "reported_gloa_lower_bound": lower,
        "bound_minus_witness": gap,
        "audit_tolerance": tolerance,
        "bound_gap_over_tolerance": gap / tolerance if gap is not None else None,
        "bound_difference_exceeds_audit_tolerance": gap > tolerance if gap is not None else None,
        # No qualified point means that persistence has not been established.
        "bound_discrepancy_persists": gap > tolerance if passed else None,
        "configuration_matches": check["configuration_matches"] if check else None,
        "logic_valid": check["logic_valid"] if check else None,
        **extra,
    }


def retry_allowed(execution, result, checked):
    return bool(
        not execution["timed_out"]
        and execution["returncode"] == 0
        and result
        and result["error"] is None
        and result["solution_loaded"]
        and result["termination"] not in {"maxTimeLimit", "maxTime", "resourceInterrupt"}
        and checked
        and not checked["numerically_feasible_under_stated_residual_test"]
    )


def prepare(directory, executable):
    directory.mkdir(parents=True, exist_ok=False)
    original, before, provenance = f.verify_input(PRIOR)
    model_check = fixed_model_check(original, before)
    previous = read(PRIOR / "selection.json")["feasibility"]
    raw_audit = read(ROOT / "reproduction/data/algebraic_audit" / previous["audit"]["result_local_path"])
    if raw_audit["reported_lower_bound"] != provenance["lower_bound"]:
        raise ValueError("A12 raw lower bound differs from audit")
    solver = Path(executable).resolve(strict=True)
    version = subprocess.run([str(solver), "-v"], capture_output=True, text=True, timeout=10, check=True)
    source_hashes = {name: sha(ROOT / name) for name in SOURCE_PATHS}
    selection = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "feasibility": previous,
        "prior_selection_sha256": sha(PRIOR / "selection.json"),
        "allocation": "New local CSTR15-only allocation, separate from the two previous option-rejected calls",
        "maximum_new_NLP_calls": 2,
        "external_wall_limit_s_per_call": 300,
        "retry_rule": "Only a returned point failing independent residual validation; no retry after timeout, interface/environment error or no returned solution",
        "targets": [1e-8, 1e-10],
        "audit_tolerance_formula": "1e-5 * max(1, abs(checked_original_objective))",
        "execution_source_sha256": source_hashes,
        "environment": environment(),
        "additional_versions": {n: importlib.metadata.version(n) for n in ("networkx", "matplotlib")},
        "solver": {"path": str(solver), "sha256": sha(solver), "version_stdout": version.stdout, "version_stderr": version.stderr},
        "original_execution_provider_revision": "38d917ef75ef6767c2a9f238d88be19bf0b89160",
    }
    for name in SOURCE_PATHS:
        dest = directory / "execution_sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    save(directory / "selection.json", selection)
    save(directory / "manifest.json", {"selection_sha256": sha(directory / "selection.json"), "status": "prepared_before_NLP_calls"})
    save(directory / "before_solution.json", {"objective": before["objective"], **f.vector(original)})
    save(directory / "before_residuals.json", before)
    save(directory / "model_equivalence.json", model_check)
    save(directory / "provenance.json", provenance)
    return before, provenance, str(solver)


def run(directory, executable):
    before, provenance, solver = prepare(directory, executable)
    rows = [comparison_row("original_W03", before, provenance["lower_bound"], True, 1e-5)]
    attempts = []
    for attempt, target in enumerate((1e-8, 1e-10), 1):
        dest = directory / "feasibility" / f"attempt_{attempt}"
        dest.mkdir(parents=True)
        command = [sys.executable, "-m", "review_diagnostics.feasibility", "--directory", str(directory), "--worker", "--attempt", str(attempt), "--ipopt", solver]
        execution = bounded(command, dest / "worker.log", 300)
        save(dest / "execution.json", execution)
        result = read(dest / "result.json") if (dest / "result.json").exists() else None
        loaded = bool(result and result["solution_loaded"])
        checked = None
        if loaded:
            # Use a newly built original GDP, not the fixed NLP's solver residuals.
            restored, _ = f.restore(read(dest / "solution.json"))
            checked = f.independent_check(restored, target, before["discrete_configuration"])
            if checked != read(dest / "residuals.json"):
                raise ValueError("Fresh GDP restoration differs from worker validation")
            save(dest / "independent_recheck.json", checked)
        elif (dest / "solution.json").exists():
            (dest / "solution.json").rename(dest / "unreturned_state.json")
        row = comparison_row(
            f"attempt_{attempt}", checked, provenance["lower_bound"], loaded, target,
            solver_status=result["solver_status"] if result else None,
            termination=result["termination"] if result else None,
            error=result["error"] if result else "Worker did not produce a result",
            timed_out=execution["timed_out"],
            solve_wall_s=result["solve_wall_s"] if result else None,
            worker_wall_s=execution["wall_s"],
            NLP_invoked=(dest / "solver_call.json").exists(),
        )
        attempts.append(row)
        rows.append(row)
        save(dest / "assessment.json", row)
        writecsv(directory / "before_after.csv", rows)
        if row["tightened_feasibility_passed"] or not retry_allowed(execution, result, checked):
            break
    latest = attempts[-1]
    summary = {
        "actual_new_NLP_calls": sum(a["NLP_invoked"] for a in attempts),
        "returned_solutions": sum(a["returned_solution"] for a in attempts),
        "previous_option_rejected_calls": 2,
        "previous_calls_charged_to_this_allocation": False,
        "tightened_feasibility_passed": latest["tightened_feasibility_passed"],
        "bound_discrepancy_persists": latest["bound_discrepancy_persists"],
        "final_assessment": latest,
        "attempts": attempts,
        "FMQA_fits": 0, "SA_calls": 0, "benchmark_reruns": 0,
        "interpretation": "Numerically feasible under the stated residual test only; no proof of exact feasibility, global optimality or mathematical invalidity of the reported bound.",
    }
    save(directory / "summary.json", summary)
    seal(directory)
    return summary


def seal(directory):
    manifest = read(directory / "manifest.json")
    manifest.update({
        "status": "completed" if read(directory / "summary.json")["tightened_feasibility_passed"] else "incomplete",
        "outputs_sha256": file_hashes(directory),
        "replay_command": f"python -m review_diagnostics.feasibility_followup verify --directory {directory.relative_to(ROOT) if directory.is_relative_to(ROOT) else directory} --output <new-json-path>",
    })
    save(directory / "manifest.json", manifest)


def verify(directory):
    manifest = read(directory / "manifest.json")
    for name, digest in manifest["outputs_sha256"].items():
        if sha(directory / name) != digest:
            raise ValueError("Saved output changed: " + name)
    selection = read(directory / "selection.json")
    if not sources_match({name: sha(ROOT / name) for name in SOURCE_PATHS},
                         selection["execution_source_sha256"]):
        raise ValueError("Current verification source differs from published source")
    for name, digest in selection["execution_source_sha256"].items():
        if sha(directory / "execution_sources" / name) != digest:
            raise ValueError("Execution source changed: " + name)
    original, before, provenance = f.verify_input(directory)
    if not residuals_match(before, read(directory / "before_residuals.json")):
        raise ValueError("Original W03 recheck changed")
    restored_before, _ = f.restore(read(directory / "before_solution.json"))
    if not residuals_match(f.independent_check(restored_before, 1e-5), before):
        raise ValueError("Saved original vector differs from W03")
    if fixed_model_check(original, before) != read(directory / "model_equivalence.json"):
        raise ValueError("Fixed NLP equivalence changed")
    summary = read(directory / "summary.json")
    markers = list(directory.glob("feasibility/attempt_*/solver_call.json"))
    if len(markers) != summary["actual_new_NLP_calls"] or len(markers) > 2:
        raise ValueError("Solver call ledger mismatch")
    rechecked = []
    for row in summary["attempts"]:
        dest = directory / "feasibility" / row["record"]
        execution = read(dest / "execution.json")
        if execution["external_wall_limit_s"] != 300:
            raise ValueError("External time limit differs from allocation")
        if row["returned_solution"]:
            model, _ = f.restore(read(dest / "solution.json"))
            check = f.independent_check(model, row["residual_target"], before["discrete_configuration"])
            if not residuals_match(check, read(dest / "independent_recheck.json")):
                raise ValueError("Saved returned point recheck changed")
            assessed = comparison_row(row["record"], check, provenance["lower_bound"], True, row["residual_target"])
            if not equivalent({k: row[k] for k in assessed}, assessed):
                raise ValueError("Assessment differs from fresh original-GDP validation")
            rechecked.append(row["record"])
        elif (dest / "solution.json").exists():
            raise ValueError("Unreturned state must not be labeled solution.json")
    if summary["final_assessment"] != summary["attempts"][-1]:
        raise ValueError("Final assessment does not match last attempt")
    for name in ("tightened_feasibility_passed", "bound_discrepancy_persists"):
        if summary[name] != summary["final_assessment"][name]:
            raise ValueError("Summary does not match final assessment")
    return {"verified": True, "new_solver_calls": 0, "original_W03_rechecked": True, "returned_vectors_rechecked": rechecked, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "verify", "seal"))
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--ipopt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == "run":
        if args.ipopt is None:
            parser.error("run requires --ipopt")
        run(directory, args.ipopt)
    elif args.action == "verify":
        if args.output is None or args.output.exists():
            parser.error("verify requires a new --output path")
        save(args.output, verify(directory))
    else:
        seal(directory)


if __name__ == "__main__":
    main()
