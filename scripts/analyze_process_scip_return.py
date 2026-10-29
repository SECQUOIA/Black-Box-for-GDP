"""Reproduce the October 25 Process SCIP return audit without solving."""
import argparse
from collections import Counter
from contextlib import contextmanager
import csv
import hashlib
import json
import logging
import math
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "process_gdpopt_scip_20261025_003203_eqiw7649.zip"
ARCHIVE_SHA = "8f4fe4ecddb0e448ff667f80f7b32df2c26f6bfca12656e9ed3ebea87d0fe8d8"
BASE_REVISION = "44ed72156a03017d7021f3fac6744bae4366dbfb"
METHODS = ("gloa", "loa", "ric")
INSTANCES = tuple(f"cstr_{n}" for n in range(5, 31, 5)) + ("column", "small_batch", "dynamic")
TOLERANCE = 1e-5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def save_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def journal(archive, name):
    return [json.loads(line) for line in archive.read(name).decode().splitlines()]


def hit(value, target):
    return value is not None and math.isfinite(value) and abs(value-target) <= TOLERANCE * max(1, abs(target))


def attained(value, target):
    return value is not None and math.isfinite(value) and value <= target + TOLERANCE * max(1, abs(target))


def verify_archive(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), "Duplicate archive member")
    require(archive.testzip() is None, "ZIP CRC failure")
    prefix = ARCHIVE.removesuffix(".zip") + "/"
    require(all(n.startswith(prefix) and ".." not in PurePosixPath(n).parts for n in names), "Unsafe archive path")
    checked = {}
    for line in archive.read(prefix + "SHA256SUMS").decode().splitlines():
        sha, name = line.split("  ", 1)
        require(name not in checked, "Duplicate checksum entry")
        require(digest(archive.read(prefix + name)) == sha, f"Checksum mismatch: {name}")
        checked[name] = sha
    require(set(checked) == {n[len(prefix):] for n in names if not n.endswith("/")} - {"SHA256SUMS"},
            "Incomplete checksum coverage")
    run = json.loads(archive.read(prefix + "run.json"))
    for name, sha in run["source_sha256"].items():
        require(digest(archive.read(prefix + "source/" + name)) == sha, f"Run source mismatch: {name}")
    package = json.loads(archive.read(prefix + "source/PACKAGE_MANIFEST.json"))
    for row in package["files"]:
        require(digest(archive.read(prefix + "source/" + row["path"])) == row["sha256"],
                f"Package source mismatch: {row['path']}")
    return prefix, run, package, checked


@contextmanager
def frozen_models(archive, prefix):
    """Load only the returned source, with exact embedded upstream identities."""
    require(not any(n == "gdp_models" or n.startswith("gdp_models.") for n in sys.modules),
            "Run this audit in a fresh process; gdp_models was already imported")
    with tempfile.TemporaryDirectory(prefix="process-scip-audit-") as temp:
        source = Path(temp)
        for name in archive.namelist():
            if name.startswith(prefix + "source/") and not name.endswith("/"):
                path = source / name[len(prefix + "source/"):]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
        sys.path.insert(0, str(source))
        try:
            from gdp_models.models import build_gdp, _discretize_dynamic, _initialize
            import pyomo.environ as pyo
            import pyomo
            require(pyomo.__version__ == "6.10.0", "Audit requires the recorded Pyomo 6.10.0")
            with patch.object(type(pyo.SolverFactory), "__call__", side_effect=AssertionError("No solver allowed in audit")):
                def build(result):
                    model = build_gdp(result["case"], cstr_size=result["cstr_size"] or 5)
                    if result["case"] == "dynamic":
                        _discretize_dynamic(model)
                    _initialize(model, result["case"], result["cstr_size"] or 5, "auto")
                    return model
                yield build
        finally:
            sys.path.remove(str(source))
            for name in list(sys.modules):
                if name == "gdp_models" or name.startswith("gdp_models."):
                    del sys.modules[name]


def verify_solution(model, solution, result):
    """Evaluate the complete returned vector in the original GDP, without FBBT.

    Check fixed values, bounds, integrality, XOR/OR, original Boolean logic,
    all global constraints, and only the selected disjunct constraints.
    Missing values must never fall back to constructor or saved initialization.
    """
    import pyomo.environ as pyo
    from pyomo.gdp import Disjunct, Disjunction
    from pyomo.core.plugins.transform.logical_to_linear import update_boolean_vars_from_binary
    descend = (pyo.Block, Disjunct)
    logic = list(model.component_data_objects(pyo.LogicalConstraint, active=True, descend_into=descend))
    fixed_booleans = [(v, pyo.value(v)) for v in model.component_data_objects(pyo.BooleanVar, descend_into=descend) if v.fixed]
    pyo.TransformationFactory("core.logical_to_linear").apply_to(model)
    for constraint in logic:
        constraint.activate()
    variables = list(model.component_data_objects(pyo.Var, descend_into=descend))
    values = solution["variables"]
    missing = [v.name for v in variables if v.name not in values]
    require(set(values) <= {v.name for v in variables}, "Unexpected serialized variable")
    maxima = {"bounds": 0., "integrality": 0., "fixed_values": 0., "constraints": 0., "disjunctions": 0.}
    worst = {k: None for k in maxima}
    counts = Counter()

    def observe(kind, value, name):
        if value > maxima[kind]:
            maxima[kind], worst[kind] = value, name

    for var in variables:
        if var.name not in values:
            require(not var.fixed, f"Missing fixed variable: {var.name}")
            var.set_value(None)
            continue
        value = values[var.name]
        require(isinstance(value, (float, int)) and math.isfinite(value), f"Invalid numeric value: {var.name}")
        if var.fixed:
            observe("fixed_values", abs(value-pyo.value(var)), var.name)
        var.set_value(value, skip_validation=True)
        observe("bounds", max(0., pyo.value(var.lb)-value if var.has_lb() else 0.,
                              value-pyo.value(var.ub) if var.has_ub() else 0.), var.name)
        if var.is_integer():
            counts["integer_variables"] += 1
            observe("integrality", abs(value-round(value)), var.name)
    update_boolean_vars_from_binary(model, integer_tolerance=TOLERANCE)
    require(all(pyo.value(v) == val for v, val in fixed_booleans), "Fixed Boolean changed")
    selected = []

    def walk(block):
        for constraint in block.component_data_objects(pyo.Constraint, active=True, descend_into=False):
            body = pyo.value(constraint.body, exception=False)
            require(body is not None and math.isfinite(body), f"Undefined constraint: {constraint.name}")
            counts["constraints"] += 1
            observe("constraints", max(0., pyo.value(constraint.lower)-body if constraint.has_lb() else 0.,
                                       body-pyo.value(constraint.upper) if constraint.has_ub() else 0.), constraint.name)
        for constraint in block.component_data_objects(pyo.LogicalConstraint, active=True, descend_into=False):
            counts["logical_constraints"] += 1
            require(pyo.value(constraint.body, exception=False) is True, f"Unsatisfied original logic: {constraint.name}")
        for disjunction in block.component_data_objects(Disjunction, active=True, descend_into=False):
            counts["disjunctions"] += 1
            require(all(d.binary_indicator_var.value is not None for d in disjunction.disjuncts), "Missing disjunction indicator")
            total = sum(pyo.value(d.binary_indicator_var) for d in disjunction.disjuncts)
            observe("disjunctions", abs(total-1) if disjunction.xor else max(0., 1-total), disjunction.name)
        for child in block.component_data_objects(pyo.Block, active=True, descend_into=False):
            walk(child)
        for child in block.component_data_objects(Disjunct, active=True, descend_into=False):
            require(child.binary_indicator_var.value is not None, "Missing disjunct indicator")
            if pyo.value(child.binary_indicator_var) > .5:
                selected.append(child.name)
                walk(child)

    walk(model)
    objective = float(pyo.value(model.obj))
    objective_error = max(abs(objective-solution["objective"]), abs(objective-result["objective"]))
    require(math.isfinite(objective) and objective_error <= 1e-8, "Saved objective mismatch")
    require(max(maxima.values()) <= TOLERANCE, f"Invalid original GDP vector: {maxima}, {worst}")
    booleans = [v.name for v in model.component_data_objects(pyo.BooleanVar, descend_into=descend)
                if v.value is True and not v.name.endswith(".indicator_var")]
    require(set(selected) == set(result["selected_disjuncts"]), "Selected disjunct mismatch")
    require(set(booleans) == set(result["selected_booleans"]), "Selected Boolean mismatch")
    return {"original_gdp_feasible": True, "objective_recomputed": objective,
            "objective_abs_error": objective_error, "variables_checked": len(values),
            "model_variables": len(variables), "missing_unreferenced_variables": missing,
            "checks": dict(counts), "max_original_violation": max(maxima.values()),
            "max_violations_by_kind": maxima, "worst_components": worst,
            "selected_disjuncts": selected, "selected_booleans": booleans}


def historical_inputs():
    selection_path = ROOT / "results/gdp_comparison_current/selection.json"
    comparison_path = ROOT / "results/gdp_comparison_current/analysis/comparison.csv"
    inputs = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in (selection_path, comparison_path,
              ROOT / "results/gdp_comparison_current/analysis/solution_rechecks.json", ROOT / "nlp_cost_analysis.py")}
    previous = {(r["instance_id"], r["method"]): r for r in csv.DictReader(comparison_path.open()) if r["method"] in METHODS}
    require(set(previous) == {(i, m) for i in INSTANCES for m in METHODS}, "Historical selection is incomplete")
    sources = []
    for spec in json.loads(selection_path.read_text())["sources"]:
        methods = set(spec["methods"]) & set(METHODS)
        if not methods:
            continue
        directory = ROOT / spec["directory"]
        pub_path = directory.parent / "publication.json"
        publication = json.loads(pub_path.read_text())
        archive_path = ROOT / publication["source_archive"]
        require(digest(archive_path.read_bytes()) == publication["source_archive_sha256"], "Historical archive changed")
        inputs[str(archive_path.relative_to(ROOT))] = publication["source_archive_sha256"]
        inputs[str(pub_path.relative_to(ROOT))] = digest(pub_path.read_bytes())
        run = json.loads((directory / "run.json").read_text())
        with zipfile.ZipFile(archive_path) as archive:
            prefix = archive_path.stem + "/"
            require(archive.read(prefix + "run.json") == (directory / "run.json").read_bytes(), "Historical run changed")
            for instance in INSTANCES:
                for method in methods:
                    base = prefix + f"jobs/{instance}/{method}/"
                    raw = json.loads(archive.read(base + "result.json"))
                    row = previous[(instance, method)]
                    require(float(row["objective"]) == raw["objective"], "Historical objective selection mismatch")
                    require(raw["status"] == row["status"] and raw["termination"] == row["termination"], "Historical status mismatch")
                    calls = journal(archive, base + "solver_calls.jsonl")
                    row["raw_solver_counts"] = dict(Counter(c["solver"] for c in calls))
                    row["raw_result"] = raw
        sources.append({"directory": spec["directory"], "methods": sorted(methods),
                        "archive": publication["source_archive"], "config": run["config"],
                        "created_utc": run["created_utc"], "host": run["host"],
                        "cpu_affinity": run["cpu_affinity"],
                        "runtime": {k:v for k,v in run["runtime"].items() if k != "templates"}})
    return previous, inputs, sources


def audit_attached_diagnostics():
    directory = ROOT / "diagnostics/gdpopt_20261023"
    sidecar = directory / "dantzig_package.zip.sha256"
    expected, name = sidecar.read_text().split()
    path = directory / name
    require(digest(path.read_bytes()) == expected, "Attached diagnostic package checksum mismatch")
    with zipfile.ZipFile(path) as archive:
        prefix = "gdpopt_20261023/"
        checks = archive.read(prefix + "PACKAGE_SHA256SUMS").decode().splitlines()
        for line in checks:
            sha, relative = line.split("  ", 1)
            require(digest(archive.read(prefix + relative)) == sha, "Diagnostic package member mismatch")
        external = (directory / "SHA256SUMS").read_text().splitlines()
        for line in external:
            sha, relative = line.split("  ", 1)
            data = archive.read(prefix + relative) if prefix + relative in archive.namelist() else (directory / relative).read_bytes()
            require(digest(data) == sha, "Attached diagnostic evidence mismatch")
        accounting = json.loads(archive.read(prefix + "execution_accounting.json"))
    return {"archive": str(path.relative_to(ROOT)), "sha256": expected,
            "internal_checksums_verified": len(checks), "attached_checksums_verified": len(external),
            "optimization_solver_calls": accounting["GDPopt_internal_solver_calls"],
            "identity_note": "October 23 diagnostic package, not the October 25 Process SCIP return.",
            "attached_file_sha256": {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in (sidecar, directory / "SHA256SUMS")}}


def analyze(path, output):
    require(digest(path.read_bytes()) == ARCHIVE_SHA, "Archive identity mismatch")
    output.mkdir(parents=True, exist_ok=True)
    previous, inputs, history = historical_inputs()
    diagnostics = audit_attached_diagnostics()
    rows, checks, paths, pairing, calls_detail, issues = [], [], [], [], [], []
    with zipfile.ZipFile(path) as archive:
        prefix, run, package, verified = verify_archive(archive)
        summary = json.loads(archive.read(prefix + "summary.json"))
        require(run["config"]["planned_jobs"] == 27 and run["config"]["methods"] == list(METHODS), "Unexpected run design")
        require(run["preflight_status"] == "passed", "Preflight did not pass")
        require(all(v == "1" for v in run["runtime"]["thread_environment"].values()), "Unexpected thread environment")
        summary_rows = {(r["instance_id"], r["method"]): r for r in summary["results"]}
        require(len(summary_rows) == len(summary["results"]) == 27, "Missing or duplicate summary rows")
        names = set(archive.namelist())
        total_calls, active_calls, statuses, terminations, versions = Counter(), Counter(), Counter(), Counter(), set()
        terminal_files = 0
        omitted_sealed_files = []
        with frozen_models(archive, prefix) as build:
            for instance in INSTANCES:
                for method in METHODS:
                    job = prefix + f"benchmark/{instance}/{method}/"
                    result = json.loads(archive.read(job + "result.json"))
                    require(all(summary_rows[(instance, method)].get(k) == v for k, v in result.items()), "Summary/result mismatch")
                    seal = json.loads(archive.read(job + "terminal.json"))["files_sha256"]
                    for name, sha in seal.items():
                        if job + name not in names:
                            require(any(part.startswith("gams-") for part in PurePosixPath(name).parts),
                                    f"Missing sealed evidence: {job}{name}")
                            omitted_sealed_files.append({"member": job + name, "sealed_sha256": sha,
                                "reason": "The archived pack() excludes all temporary gams-* directories, including leftovers after the watchdog kill."})
                            continue
                        require(digest(archive.read(job + name)) == sha, f"Terminal seal mismatch: {job}{name}")
                        terminal_files += 1
                    returned = job + "solution.json" in names
                    require(returned == result["has_feasible_solution"], "Solution availability mismatch")
                    require(not result["global_optimality_certified"], "Unexpected global certificate requires review")
                    checked = None
                    if returned:
                        checked = verify_solution(build(result), json.loads(archive.read(job + "solution.json")), result)
                        checks.append({"instance_id": instance, "method": method, **checked})
                    calls = journal(archive, job + "solver_calls.jsonl")
                    require([c["index"] for c in calls] == list(range(1, len(calls)+1)), "Solver call sequence mismatch")
                    require(len(calls) == result.get("solver_calls", len(calls)), "Solver call count mismatch")
                    require(all(c["threads"] == 1 for c in calls), "Solver thread count mismatch")
                    counts = Counter(f"{c['solver']}/{c['mtype']}" for c in calls)
                    require(set(counts) <= {"highs/mip", "scip/nlp"}, "Unexpected solver actually called")
                    require(dict(counts) == summary_rows[(instance, method)]["actual_solver_calls"], "Summary solver count mismatch")
                    total_calls.update(counts)
                    for call in calls:
                        stats = call.get("gams_statistics", {})
                        calls_detail.append({"instance_id": instance, "method": method, "index": call["index"],
                            "solver": call["solver"], "mtype": call["mtype"], "status": call["status"],
                            "termination": call.get("termination"), "modelstat": stats.get("MODELSTAT"),
                            "solvestat": stats.get("SOLVESTAT"), "wall_s": call["wall_s"],
                            "global_subproblem_complete": call.get("global_subproblem_complete")})
                    active = json.loads(archive.read(job + "active_solver_call.json")) if job + "active_solver_call.json" in names else None
                    if active:
                        require(active["index"] == len(calls)+1, "Stale active call")
                        active_calls[f"{active['solver']}/{active['mtype']}"] += 1
                    log = archive.read(job + "run.log").decode()
                    versions.update(re.findall(r"SCIP version [^\n]+|Running HiGHS [^\n]+|  Ipopt [^\n]+", log))
                    trace = journal(archive, job + "gdp_path.jsonl")
                    before = [e for e in trace if e["event"] == "before_subproblem"]
                    for event_index, event in enumerate(trace):
                        binaries = event["binary_values"]
                        selected = sorted(k for k, v in binaries.items() if v is not None and v > .5)
                        feeds = [int(k[12:-1]) for k in selected if k.startswith("YF_asbinary[")]
                        recycles = [int(re.search(r"\[(\d+)\]", k).group(1)) for k in selected if k.startswith("YR_is_recycle[")]
                        paths.append({"instance_id": instance, "method": method, "event_index": event_index,
                            "event": event["event"], "iteration": event["iteration"], "elapsed_s": event["elapsed_s"],
                            "completed_solver_calls": event["completed_solver_calls"],
                            "cstr_external_point": [feeds[0], recycles[0]] if len(feeds) == len(recycles) == 1 else None,
                            "selected_binary_count": len(selected),
                            "binary_values_sha256": digest(json.dumps(binaries, sort_keys=True).encode())})
                    statuses[result["status"]] += 1
                    terminations[result["termination"]] += 1
                    old = previous[(instance, method)]
                    target = float(old["target_value"])
                    require(all(float(previous[(instance, m)]["target_value"]) == target for m in METHODS), "Inconsistent historical target")
                    value = checked["objective_recomputed"] if checked else None
                    duration = result.get("method_wall_s", result["worker_wall_s"])
                    row = {"instance_id": instance, "method": method, "status": result["status"],
                        "termination": result["termination"], "normalized_outcome": "time_limit" if result["termination"] == "maxTimeLimit" else result["status"],
                        "solution_returned": returned, "original_gdp_feasible": bool(checked), "objective": value,
                        "target_value": target, "target_hit": hit(value, target), "target_attained": attained(value, target),
                        "signed_relative_target_gap": (value-target)/max(1, abs(target)) if value is not None else None,
                        "max_original_violation": checked["max_original_violation"] if checked else None,
                        "method_or_watchdog_wall_s": duration, "clock_source": "method_wall_s" if "method_wall_s" in result else "worker_wall_s_watchdog",
                        "worker_wall_s": result["worker_wall_s"], "template_wall_s": result["template_wall_s"],
                        "total_with_preparation_s": duration+result["template_wall_s"],
                        "highs_mip_logged_calls": counts["highs/mip"], "scip_nlp_logged_calls": counts["scip/nlp"],
                        "scip_nlp_calls_without_terminal_record": int(bool(active and active["solver"] == "scip")),
                        "solver_call_wall_s_logged": sum(c["wall_s"] for c in calls),
                        "before_subproblem_callbacks": len(before), "path_events": len(trace),
                        "distinct_binary_assignments_before_subproblem": len({json.dumps(e["binary_values"], sort_keys=True) for e in before}),
                        "reported_lower_bound": result.get("reported_lower_bound"),
                        "reported_upper_bound": result.get("reported_upper_bound"),
                        "global_optimality_certified": False, "initialization": result["initialization"],
                        "solution_member": job + "solution.json" if returned else None,
                        "path_sha256": digest(archive.read(job + "gdp_path.jsonl"))}
                    rows.append(row)
                    old_value = float(old["objective"])
                    require(hit(old_value, target) == (old["target_hit"] == "True"), "Historical target definition differs")
                    pairing.append({"instance_id": instance, "method": method, "target_value": target,
                        "baron_objective": old_value, "scip_objective": value,
                        "scip_minus_baron_objective": value-old_value if value is not None else None,
                        "baron_target_hit": hit(old_value, target), "scip_target_hit": row["target_hit"],
                        "baron_target_attained": attained(old_value, target), "scip_target_attained": row["target_attained"],
                        "baron_status": old["status"], "baron_termination": old["termination"],
                        "scip_status": result["status"], "scip_termination": result["termination"],
                        "baron_completion_s": float(old["measured_total_with_preparation_s"]),
                        "scip_completion_s": row["total_with_preparation_s"],
                        "same_upstream_model_and_initialization_hashes": old["raw_result"]["source"] == result["source"],
                        "same_initialization_label": old["raw_result"]["initialization"] == result["initialization"],
                        "same_template_bound_tightening": old["raw_result"]["globally_implied_bounds"] == result["globally_implied_bounds"],
                        "baron_source_directory": old["source_directory"], "baron_solver_counts": old["raw_solver_counts"]})
                    if result["termination"] in {"maxTimeLimit", "error"}:
                        issues.append({"instance_id": instance, "method": method, "status": result["status"],
                            "termination": result["termination"], "message": result.get("message"),
                            "active_call_at_stop": active, "last_logged_call": calls[-1],
                            "solution_returned": returned, "run_log_member": job + "run.log"})
        require(dict(total_calls) == summary["actual_benchmark_solver_calls"], "Total logged calls mismatch")
        require(len(checks) == summary["solutions_returned"] == summary["feasible_jobs"], "Feasible total mismatch")
        preflight = Counter()
        for name in sorted(names):
            if "/preflight/" in name and name.endswith("/solver_calls.jsonl"):
                preflight.update(f"{c['solver']}/{c['mtype']}" for c in journal(archive, name))
        for row in rows:
            witnesses = [r for r in rows if r["instance_id"] == row["instance_id"] and r["original_gdp_feasible"]]
            witness = min(witnesses, key=lambda r: r["objective"])
            lower = row["reported_lower_bound"]
            row["bound_conflicts_with_new_verified_solution"] = lower is not None and lower > witness["objective"] + TOLERANCE * max(1, abs(witness["objective"]))
            row["best_verified_objective_same_archive"] = witness["objective"]
            row["bound_witness_method"] = witness["method"]
        overview = {"jobs": len(rows), "returned_feasible_solutions": len(checks), "new_optimization_calls_during_analysis": 0,
            "logged_benchmark_solver_calls": dict(total_calls), "additional_calls_without_terminal_record": dict(active_calls),
            "actual_started_benchmark_calls": dict(total_calls + active_calls), "preflight_calls_excluded": dict(preflight),
            "raw_status_counts": dict(statuses), "termination_counts": dict(terminations),
            "max_verified_primal_violation": max(c["max_original_violation"] for c in checks),
            "verified_variables_total": sum(c["variables_checked"] for c in checks),
            "method_or_watchdog_wall_s_total": sum(r["method_or_watchdog_wall_s"] for r in rows),
            "worker_wall_s_total": sum(r["worker_wall_s"] for r in rows),
            "preparation_once_per_instance_s": sum(next(r for r in rows if r["instance_id"] == i)["template_wall_s"] for i in INSTANCES),
            "logged_solver_call_wall_s_total": sum(r["solver_call_wall_s_logged"] for r in rows),
            "path_events": len(paths), "scip_and_component_version_lines": sorted(versions),
            "bound_conflicts": [{k:r[k] for k in ("instance_id", "method", "reported_lower_bound", "best_verified_objective_same_archive", "bound_witness_method")}
                                for r in rows if r["bound_conflicts_with_new_verified_solution"]]}
        methods = []
        for method in METHODS:
            selected = [r for r in rows if r["method"] == method]
            paired = [r for r in pairing if r["method"] == method]
            methods.append({"method": method, "jobs": len(selected), "verified_solutions": sum(r["original_gdp_feasible"] for r in selected),
                "baron_target_hits": sum(r["baron_target_hit"] for r in paired), "scip_target_hits": sum(r["target_hit"] for r in selected),
                "baron_target_attained": sum(r["baron_target_attained"] for r in paired), "scip_target_attained": sum(r["target_attained"] for r in selected),
                "both_hit": sum(r["baron_target_hit"] and r["scip_target_hit"] for r in paired),
                "scip_only_hit": sum(not r["baron_target_hit"] and r["scip_target_hit"] for r in paired),
                "baron_only_hit": sum(r["baron_target_hit"] and not r["scip_target_hit"] for r in paired),
                "neither_hit": sum(not r["baron_target_hit"] and not r["scip_target_hit"] for r in paired),
                "time_limits": sum(r["termination"] == "maxTimeLimit" for r in selected),
                "errors": sum(r["termination"] == "error" for r in selected),
                "baron_completion_s_sum": sum(r["baron_completion_s"] for r in paired),
                "scip_completion_s_sum": sum(r["total_with_preparation_s"] for r in selected)})
        overview["by_method"] = methods
        manifest = {"analysis_base_revision": BASE_REVISION, "executed_repository_revision": None,
            "revision_note": "The returned package records exact file hashes and upstream pins, but no repository commit; no revision is inferred.",
            "archive": "results/archives/"+path.name, "archive_sha256": ARCHIVE_SHA, "archive_bytes": path.stat().st_size,
            "outer_checksum_provenance": "Locally calculated on receipt; no downloaded server sidecar was available.",
            "internal_checksums_verified": len(verified), "terminal_jobs_inspected": len(rows),
            "terminal_jobs_fully_verifiable": len(rows)-len({f['member'].split('/gams-')[0] for f in omitted_sealed_files}),
            "terminal_files_verified": terminal_files, "sealed_files_omitted_by_packer": omitted_sealed_files,
            "run_source_files_verified": len(run["source_sha256"]), "package_files_verified": len(package["files"]),
            "source_sha256": run["source_sha256"], "upstream_pins": package["submodules"],
            "created_utc": run["created_utc"], "run_config": run["config"], "runtime": run["runtime"],
            "correction_policy": run["correction_policy"], "time_policy": run["time_policy"],
            "historical_sources": history, "input_sha256": inputs, "attached_diagnostics": diagnostics,
            "target_rule": "abs(objective-reference) <= 1e-5 * max(1, abs(reference)); reference from unchanged current comparison",
            "supplementary_attainment_rule": "objective <= reference + 1e-5 * max(1, abs(reference))",
            "primal_tolerance": TOLERANCE, "analysis_python": platform.python_version(), "analysis_pyomo": "6.10.0",
            "analysis_system": platform.system(), "analysis_machine": platform.machine(),
            "analysis_source_sha256": {"scripts/analyze_process_scip_return.py": digest(Path(__file__).read_bytes())},
            "analysis_environment_note": "Local Python differs from server Python; no solver is constructed or invoked."}
    save_csv(output / "jobs.csv", rows)
    save_csv(output / "paired_baron_scip.csv", pairing)
    save_csv(output / "methods.csv", methods)
    save_csv(output / "solver_calls.csv", calls_detail)
    save_csv(output / "gdp_path_events.csv", paths)
    save_json(output / "solution_checks.json", checks)
    save_json(output / "issues.json", issues)
    save_json(output / "summary.json", overview)
    save_json(output / "manifest.json", manifest)
    return rows, overview, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "results/archives" / ARCHIVE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.getLogger("pyomo").setLevel(logging.ERROR)
    _, overview, _ = analyze(args.archive, args.output)
    print(json.dumps({k: overview[k] for k in ("jobs", "returned_feasible_solutions", "actual_started_benchmark_calls", "by_method")}, indent=2))


if __name__ == "__main__":
    main()
