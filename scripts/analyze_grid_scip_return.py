"""Audit the October 23 SCIP returns without invoking optimization solvers."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import statistics
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyomo.environ as pyo  # noqa: E402
from pyomo.gdp import Disjunct  # noqa: E402
from gdp_models.grid import build_grid_gdp, GRID_NAMES  # noqa: E402

ARCHIVES = {
    "grid_scip_minlp_20261023_143526_ce02ov4c.zip": "c7ace16f230094051c0df4681294832c559b79a63fe40ef67875f5a2bf762180",
    "grid_scip_gloa_20261023_143538_k3722s6a.zip": "579280dfe0ff8344471203901db3cf3197714d8a737ee05c94542ade8042cb86",
    "grid_scip_loa_20261023_143545_30_v346o.zip": "2914cb6e0c94b8dc90bdd573d7589862e760586ee1e094c4252bda7514b452fd",
    "grid_scip_ric_20261023_143553_new9tgw4.zip": "6d0adbbd2be4226fe5b79c36c0a6e800088d7ceb586ce9a3f338069e6c4acdce",
}
DIAGNOSTIC_SHA = "424b615ca564bac6a7a9c4e05b9f19e98e307d1982d9e15e2617519e8c2a28e6"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(archive, name):
    return json.loads(archive.read(name))


def journal(archive, name):
    return [json.loads(line) for line in archive.read(name).decode().splitlines()]


def checksums(archive, prefix, name="SHA256SUMS"):
    rows = archive.read(prefix + name).decode().splitlines()
    for row in rows:
        sha, path = row.split("  ", 1)
        require(digest(archive.read(prefix + path)) == sha, f"Checksum mismatch: {path}")
    return len(rows)


def verify_solution(name, solution, result):
    """Reload every original variable; check XOR, integrality, bounds, branches.

    Do not trust the runner's feasibility flag, snapped point, or saved objective.
    All 961 analytic values are checked against the CSV by build_grid_gdp.
    """
    model = build_grid_gdp(name)
    values = solution["variables"]
    variables = list(model.component_data_objects(pyo.Var, descend_into=(pyo.Block, Disjunct)))
    missing = [v.name for v in variables if v.name not in values]
    require(not missing, f"Missing original variables: {missing}")
    violation = 0.0
    for var in variables:
        value = values[var.name]
        require(isinstance(value, (float, int)) and math.isfinite(value), f"Invalid {var.name}")
        var.set_value(value, skip_validation=True)
        violation = max(violation, var.lb-value if var.has_lb() else 0,
                        value-var.ub if var.has_ub() else 0)
        if var.is_integer():
            violation = max(violation, abs(value-round(value)))
    point = []
    for choices in (model.Xchoice, model.Ychoice):
        selected = [i for i in model.I if choices[i].binary_indicator_var.value > .5]
        require(len(selected) == 1, f"Invalid XOR: {name}")
        violation = max(violation, abs(sum(choices[i].binary_indicator_var.value for i in model.I)-1))
        point.append(int(selected[0]))
        for constraint in choices[selected[0]].component_data_objects(pyo.Constraint, active=True):
            body = float(pyo.value(constraint.body))
            violation = max(violation, pyo.value(constraint.lower)-body if constraint.has_lb() else 0,
                            body-pyo.value(constraint.upper) if constraint.has_ub() else 0)
    objective = float(pyo.value(model.obj))
    require(math.isfinite(objective), "Nonfinite analytic objective")
    objective_error = max(abs(objective-solution["objective"]), abs(objective-result["objective"]))
    require(violation <= 1e-5 and objective_error <= 1e-8, f"Invalid original GDP solution: {name}")
    reference = list(csv.DictReader((ROOT / "benchmark_grids" / f"{name}.csv").open()))
    table = {(int(r["x"]), int(r["y"])): float(r["z_norm"]) for r in reference}
    optimum = min(table.values())
    gap = table[tuple(point)]-optimum
    target = gap <= 1e-5
    require(point == result["grid_point"], "Recorded coordinates disagree with solution vector")
    require(target == result["target_hit"], "Recorded target flag disagrees with reference")
    return {
        "grid_point": point, "physical_point": [float(pyo.value(model.x)), float(pyo.value(model.y))],
        "returned_original_variables": len(variables), "original_gdp_feasible": True,
        "max_original_violation": violation, "objective_recomputed": objective,
        "saved_objective_abs_error": objective_error, "csv_objective": table[tuple(point)],
        "reference_minimum": optimum, "normalized_gap": gap, "target_hit_verified": target,
        "reference_minimizers": [list(k) for k,v in table.items() if v == optimum],
        "analytic_grid_points_checked": model.grid_audit["points_checked"],
        "analytic_grid_max_csv_error": model.grid_audit["max_abs_error"],
    }


def audit_archive(path, expected):
    require(digest(path.read_bytes()) == expected, f"Archive identity mismatch: {path}")
    sidecar = path.with_suffix(".zip.sha256").read_text().strip().split()
    require(sidecar == [expected, path.name], f"Archive sidecar mismatch: {path}")
    rows = []
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "CRC failure")
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate archive members")
        prefix = names[0].split("/")[0] + "/"
        count = checksums(archive, prefix)
        run = read_json(archive, prefix + "run.json")
        for name, sha in run["source_sha256"].items():
            require(digest(archive.read(prefix + "source/" + name)) == sha, f"Source mismatch: {name}")
        for name in ["gdp_models/grid.py", *[f"benchmark_grids/{n}.csv" for n in GRID_NAMES]]:
            require(archive.read(prefix + "source/" + name) == (ROOT / name).read_bytes(),
                    f"Audit model/input differs from executed source: {name}")
        config = run["config"]
        expected_pairs = {(g,m) for g in config["grids"] for m in config["methods"]}
        observed = set()
        for name in sorted(names):
            if "/benchmark/" not in name or not name.endswith("/result.json"):
                continue
            job = name.rsplit("/", 1)[0] + "/"
            result = read_json(archive, name)
            grid, method = result["grid_name"], result["method"]
            require((grid,method) not in observed, "Duplicate job")
            observed.add((grid,method))
            terminal = read_json(archive, job + "terminal.json")
            for member, sha in terminal["files_sha256"].items():
                require(digest(archive.read(job + member)) == sha, f"Job seal mismatch: {job}{member}")
            solution = read_json(archive, job + "solution.json")
            checked = verify_solution(grid, solution, result)
            calls = journal(archive, job + "solver_calls.jsonl")
            trace = journal(archive, job + "grid_path.jsonl") if job + "grid_path.jsonl" in names else []
            before = [e for e in trace if e["event"] == "before_subproblem"]
            after = [e for e in trace if e["event"] == "after_subproblem"]
            visited = {tuple(e["grid_point"]) for e in before if e.get("grid_point") is not None}
            solver_counts = dict(Counter(c["solver"] for c in calls))
            require(len(calls) == result["solver_calls"], "Solver call count mismatch")
            require(all(c["threads"] == 1 for c in calls), "Unexpected threading")
            raw = result.get("gams_statistics", {})
            rows.append({
                "grid_name": grid, "method": method, "archive": path.name,
                "solution_member": job + "solution.json", "result_member": name,
                "status": result["status"], "termination": result["termination"],
                "solution_returned": True, **checked,
                "reported_optimal_but_misses_target": result["termination"] == "optimal" and not checked["target_hit_verified"],
                "runner_global_certificate": result["global_optimality_certified"],
                "raw_gams_modelstat": raw.get("MODELSTAT"), "raw_gams_solvestat": raw.get("SOLVESTAT"),
                "reported_lower_bound": result.get("reported_lower_bound"),
                "reported_upper_bound": result.get("reported_upper_bound"),
                "method_wall_s": result["method_wall_s"], "worker_wall_s": result["worker_wall_s"],
                "gdpopt_iterations": result.get("gdpopt_iterations"),
                "solver_calls": len(calls), "actual_solver_counts": solver_counts,
                "before_subproblem_callbacks": len(before), "after_subproblem_callbacks": len(after),
                "distinct_callback_points": len(visited),
                "exact_reference_minimizer_seen_in_callbacks": any(tuple(p) in visited for p in checked["reference_minimizers"]),
                "coordinate_sequence_sha256": digest(json.dumps([e.get("grid_point") for e in before]).encode()),
                "solver_policy": result["solver_policy"], "retry_fix_profile": result.get("retry_fix_profile"),
            })
        require(observed == expected_pairs, "Missing or unplanned jobs")
        preflight = Counter()
        for name in names:
            if "/preflight/" in name and name.endswith("/solver_calls.jsonl"):
                preflight.update(c["solver"] for c in journal(archive, name))
        inventory = {"archive": path.name, "sha256": expected, "bytes": path.stat().st_size,
                     "internal_checksums_verified": count, "source_files_verified": len(run["source_sha256"]),
                     "sealed_jobs": len(rows), "config": config, "runtime": run["runtime"],
                     "preflight_solver_calls": dict(preflight)}
    return rows, inventory


def audit_diagnostics(directory):
    archive_path = directory / "dantzig_package.zip"
    require(digest(archive_path.read_bytes()) == DIAGNOSTIC_SHA, "Diagnostic ZIP mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        require(archive.testzip() is None, "Diagnostic CRC mismatch")
        prefix = "gdpopt_20261023/"
        count = checksums(archive, prefix, "PACKAGE_SHA256SUMS")
        manifest = json.loads((directory / "package_manifest.json").read_text())
        for name, sha in manifest["member_sha256"].items():
            require(digest(archive.read(prefix+name)) == sha, f"Diagnostic manifest mismatch: {name}")
        external = (directory / "SHA256SUMS").read_text().splitlines()
        for line in external:
            sha, name = line.split("  ", 1)
            data = archive.read(prefix+name) if prefix+name in archive.namelist() else (directory/name).read_bytes()
            require(digest(data) == sha, f"Diagnostic evidence mismatch: {name}")
        accounting = read_json(archive, prefix + "execution_accounting.json")
        probe = read_json(archive, prefix + "cstr_probe.json")
        return {
            "sha256": DIAGNOSTIC_SHA, "package_checksums_verified": count,
            "external_checksums_verified": len(external), "full_gdpopt_runs": accounting["GDPopt_full_runs"],
            "optimization_solver_calls": accounting["GDPopt_internal_solver_calls"],
            "diagnostic_is_a_solver_free_analysis_and_unexecuted_runner": True,
            "cstr_original_violating_cuts": sum(c["applicable_to_W03"] and c["violation"] > 1e-8 for c in probe[0]["cuts"]),
            "cstr_max_applicable_cut_violation": max(c["violation"] for c in probe[0]["cuts"] if c["applicable_to_W03"]),
            "cstr_corrected_transformed_violations": probe[1]["transformed_witness_violations"],
        }


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def save_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows, archives = [], []
    for name, sha in ARCHIVES.items():
        jobs, inventory = audit_archive(ROOT / "results/archives" / name, sha)
        rows.extend(jobs)
        archives.append(inventory)
    summary = []
    for method in ("bigm", "hull", "gloa", "loa", "ric"):
        selected = [r for r in rows if r["method"] == method]
        calls = Counter()
        for row in selected:
            calls.update(row["actual_solver_counts"])
        summary.append({
            "method": method, "jobs": len(selected),
            "returned_feasible_solutions": sum(r["original_gdp_feasible"] for r in selected),
            "target_hits": sum(r["target_hit_verified"] for r in selected),
            "optimal_terminations": sum(r["termination"] == "optimal" for r in selected),
            "time_limit_terminations": sum(r["termination"] == "maxTimeLimit" for r in selected),
            "optimal_but_misses_target": sum(r["reported_optimal_but_misses_target"] for r in selected),
            "runner_global_certificates": sum(r["runner_global_certificate"] for r in selected),
            "method_wall_s_sum": sum(r["method_wall_s"] for r in selected),
            "method_wall_s_median": statistics.median(r["method_wall_s"] for r in selected),
            "actual_solver_counts": dict(calls),
        })
    save_json(args.output / "jobs.json", rows)
    save_csv(args.output / "jobs.csv", rows)
    save_json(args.output / "summary.json", summary)
    save_csv(args.output / "summary.csv", summary)
    save_json(args.output / "audit.json", {
        "archives": archives, "diagnostic": audit_diagnostics(ROOT / "diagnostics/gdpopt_20261023"),
        "jobs": len(rows), "returned_solutions_independently_verified": sum(r["original_gdp_feasible"] for r in rows),
        "maximum_original_gdp_violation": max(r["max_original_violation"] for r in rows),
        "maximum_saved_objective_abs_error": max(r["saved_objective_abs_error"] for r in rows),
        "optimization_solver_calls_during_analysis": 0,
        "analysis_pyomo_version": importlib.metadata.version("pyomo"),
        "analysis_source_sha256": digest(Path(__file__).read_bytes()),
    })
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
