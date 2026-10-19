"""Measure only CSTR30 structural rejections; augment frozen DFO costs separately."""
import argparse
from collections import Counter
from contextlib import contextmanager, ExitStack
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import logging
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter_ns
from unittest.mock import patch
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parent
SCOPE = ("perf_counter_ns immediately before/after frozen evaluate_point: original fresh N30 GDP "
         "construction, constructor initialization, external fixing, logical/GDP transformations "
         "and original preprocessing until rejection returns; no solver; excludes batch source "
         "imports/preloading, CSV/checkpoint IO, logging, provenance and output generation")
POINTS = [(x, y) for x in range(1, 31) for y in range(x + 1, 31)]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def rows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, data):
    fields = list(dict.fromkeys(k for row in data for k in row))
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in data:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    temporary.replace(path)


def verify_bundle(root):
    names = []
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(sha(root / name) == digest, "Bundle checksum mismatch: " + name)
        names.append(name)
    require(len(names) == len(set(names)), "Duplicate bundle inventory member")
    return names


def check_inputs(root):
    """All reads/checks occur before the coordinate timer, with no model/solver."""
    verify_bundle(root)
    directory = root / "inputs/cstr_30"
    manifest, info = read(directory / "manifest.json"), read(directory / "provenance.json")
    original = rows(directory / "evaluations.csv")
    allowed = {(x, y) for x in range(1, 31) for y in range(1, x + 1)}
    points = [tuple(json.loads(r["point"])) for r in original]
    require(len(points) == len(set(points)) == 465 and set(points) == allowed, "Original logical coverage differs")
    require(set(itertools.product(range(1, 31), repeat=2)) - set(points) == set(POINTS), "Missing set is not the 435 structural exclusions")
    plan = manifest["plan"]
    require(plan["cstr_size"] == 30 and plan["bounds"] == [[1, 30], [1, 30]]
            and plan["candidate_count"] == 465 and plan["excluded_by_logic"] == 435, "Original model/plan mismatch")
    require(manifest["config"] == {"solver": "gams_ipopt", "initialization": "auto", "time_limit_s": 60,
            "feasibility_tolerance": 1e-5}, "Original evaluation procedure changed")
    require(info["record_selection_note"].startswith("Original completed 465-row table"), "Unexpected attempt selection")
    for row in original:
        record = read(directory / "records" / f'point_{int(row["point_index"]):06d}.json')
        require(record["case"] == "cstr" and record["cstr_size"] == 30 and record["point"] == json.loads(row["point"]), "Wrong-size record")
        require(row["accepted"] == str(record["accepted"]) and row["status"] == record["status"], "Status mismatch")
        for field in ("objective", "candidate_objective", "setup_wall_s", "preprocess_wall_s", "solve_wall_s", "total_wall_s"):
            require((float(row[field]) if row.get(field) else None) == record.get(field), "Original CSV/record mismatch: " + field)
        require(math.isfinite(float(row["total_wall_s"])) and float(row["total_wall_s"]) > 0, "Original cost missing")
    jobs = read(root / "inputs/dfo/plan.json")
    require(len(jobs) == 40 and len({s["job_id"] for s in jobs}) == 40, "CSTR30 DFO matrix differs")
    require({(s["method"], s["seed"]) for s in jobs} == set(itertools.product(("rbfopt", "bam", "dsda", "fmqa_sa"), range(10))), "Missing method/seed")
    require(all(s["cstr_size"] == 30 and s["budget"] == 43 for s in jobs), "Wrong DFO size/budget")
    return original, manifest, jobs


def prepare_evaluator(root, manifest, strict=True):
    """Warm only imports/source-definition caches, never construct a test model."""
    from gdp_models import evaluation, models, _sources
    from gdp_models.preflight import dependency_versions
    for module in (evaluation, models, _sources):
        require(Path(module.__file__).resolve().is_relative_to(root.resolve()), "Non-bundled adapter imported")
    prior = manifest["runtime"]
    for name, digest in prior["adapter_sha256"].items():
        path = root / "gdp_models" / name
        if path.exists():
            require(sha(path) == digest, "Adapter differs from original: " + name)
    dependencies = dependency_versions()
    if strict:
        require(platform.system() == "Linux" and platform.node() == "dantzig.ecn.purdue.edu", "Production measurement must run on Dantzig")
        require(platform.python_version() == prior["python_version"] and dependencies == prior["dependency_versions"], "Use the original .venv-dantzig-gdp environment")
        require(len(os.sched_getaffinity(0)) == 1, "Use the launcher to pin one CPU")
    source = _sources.provenance("dsda-gdp", prior["source"]["files_sha256"])
    require(source == prior["source"], "Pinned model/helper source differs")
    initialized, files = models.initialization_info("cstr", 30, "auto")
    require(initialized == prior["initialization"] and not files, "Original constructor initialization changed")
    _sources.load_source("dsda-gdp", "gdp/cstr/gdp_reactor.py")
    _sources.load_source("dsda-gdp", "gdp/dsda/dsda_functions.py", ("external_ref", "get_external_information"))
    _sources.load_source("dsda-gdp", "main_cstr.py", ("problem_logic_cstr",))
    identity = {"python": platform.python_version(), "executable": sys.executable,
        "dependencies": dependencies, "host": platform.node(), "platform": platform.platform(),
        "effective_cpu": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "thread_environment": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        "source": source, "initialization": initialized, "clock": vars(__import__("time").get_clock_info("perf_counter")),
        "historical_solver_identity_only": {k: prior[k] for k in ("solver_executable", "solver_executable_sha256", "solver_version")},
        "solver_version_or_availability_probes": 0, "common_preparation_test_models": 0}
    return evaluation.evaluate_point, identity


class ForbiddenExecution(BaseException):
    """Do not let the historical evaluator catch and relabel a forbidden call."""


@contextmanager
def no_solver():
    from gdp_models import evaluation, solvers
    import pyomo.environ as pyo
    import pyomo.opt as opt
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("forbidden solver/process entry")
        raise ForbiddenExecution("Solver and subprocess execution prohibited in structural timing")

    old_logging = logging.root.manager.disable
    with ExitStack() as stack:
        for module, name in ((evaluation, "optimizer_for"), (evaluation, "solve_gams"),
                (solvers, "optimizer_for"), (solvers, "solve_gams"), (pyo, "SolverFactory"),
                (opt, "SolverFactory"), (subprocess, "Popen"), (os, "system")):
            stack.enter_context(patch.object(module, name, forbidden))
        logging.disable(logging.CRITICAL)
        try:
            yield attempts
        finally:
            logging.disable(old_logging)


def measure_one(evaluate, point, run_id, invocation_id, clock=perf_counter_ns):
    require(tuple(point) in POINTS, "Only x2>x1 CSTR30 points may enter the evaluator")
    measured_utc = stamp()
    started = clock()
    report = evaluate("cstr", point, cstr_size=30, initialization="auto", solver="gams_ipopt",
                      time_limit=60.0, feasibility_tolerance=1e-5, tee=False)
    finished = clock()
    # Validation and provenance happen after the returned result was timed.
    require(report["status"] == "preprocessing_infeasible" and report["termination"] == "not_solved"
            and report["accepted"] is False and report["objective"] is None and report["solve_wall_s"] == 0,
            "Original path did not return a structural rejection")
    elapsed = finished - started
    require(type(elapsed) is int and elapsed > 0, "Clock did not record a positive interval")
    report.update(inner_total_wall_s=report["total_wall_s"], total_wall_s=elapsed / 1_000_000_000,
        elapsed_ns=elapsed, x1=point[0], x2=point[1], solver_called=False,
        structural_reason="x2>x1: recycle assigned to a bypass; original GDP reactor/recycle logic is violated",
        measurement_scope=SCOPE, measurement_run_id=run_id, invocation_id=invocation_id,
        measured_utc=measured_utc, time_source="measured_cstr30_structural_rejection",
        evaluation_origin="new_structural_measurement", timing_record_id=f"cstr_30_{point[0]:02d}_{point[1]:02d}")
    require(math.isfinite(report["total_wall_s"]) and report["total_wall_s"] > 0, "Nonfinite/rounded-zero time")
    return report


def supplement_callbacks(root, measured, output):
    """Add cost columns only. Every original event/result field stays unchanged."""
    original_runs = {r["job_id"]: r for r in rows(root / "inputs/dfo/runs.csv") if r["cstr_size"] == "30"}
    events_out, runs_out, leftovers = [], [], []
    for spec in read(root / "inputs/dfo/plan.json"):
        job_id = spec["job_id"]
        folder = root / "inputs/dfo/jobs" / job_id
        events = [json.loads(line) for line in (folder / "callbacks.jsonl").read_text().splitlines()]
        result = read(folder / "result.json")
        original = original_runs[job_id]
        require(int(original["callback_count"]) == len(events) == result["callback_count"], "Original callback count changed")
        require(original["execution_status"] == result["status"], "Original failure status mismatch")
        costs, old_costs, added = [], [], []
        for index, event in enumerate(events, 1):
            require(event["index"] == index and event["cstr_size"] == 30, "Callback order/size changed")
            point = tuple(event["point"])
            before = event["selected_attempt_nlp_s"]
            require(before == event["all_attempts_nlp_s"], "Unexpected retry-cost policy")
            applicable = (before is None and event["evaluation_state"] == "logical_exclusion_unmeasured"
                          and not event["budget_overrun"] and event["source_row"] is None and point in measured)
            if event["evaluation_state"] == "logical_exclusion_unmeasured":
                require(point in POINTS and not event["accepted"], "Unexpected structural callback")
            record = measured[point] if applicable else None
            after = record["total_wall_s"] if applicable else before
            overlay = {"timing_supplement_applied": applicable,
                "reconstructed_process_wall_s": after, "reconstructed_all_attempts_wall_s": after,
                "supplement_measurement_run_id": record["measurement_run_id"] if record else None,
                "supplement_record_id": record["timing_record_id"] if record else None,
                "reconstructed_time_source": record["time_source"] if record else "original_selected_attempt" if before is not None else "unavailable",
                "remaining_time_missing_reason": None if after is not None else
                    "budget_protocol_error: original callback never read a process CSV row" if event["budget_overrun"] else event["evaluation_state"]}
            require(not set(event) & set(overlay), "Overlay would overwrite original event fields")
            events_out.append({"job_id": job_id, **event, **overlay})
            require(all(events_out[-1][k] == v for k, v in event.items()), "Original event changed")
            costs.append(after)
            old_costs.append(before)
            if applicable:
                added.append(after)
            if after is None:
                leftovers.append({"job_id": job_id, "index": index, "point": list(point),
                    "reason": overlay["remaining_time_missing_reason"], "original_execution_status": original["execution_status"]})
        before_missing, after_missing = old_costs.count(None), costs.count(None)
        require(int(original["missing_nlp_times"]) == before_missing, "Original missing-time count differs")
        require(float(original["dfo_wall_s"]) == result["dfo_wall_s"], "DFO clock differs")
        require(math.isclose(float(original["lookup_wall_s"]), sum(e["lookup_wall_s"] for e in events), rel_tol=1e-12), "Lookup clock differs")
        runs_out.append({**original, "timing_scope": "reconstructed process cost; every repeated callback charged; DFO/lookup clocks unchanged",
            "missing_process_times_before": before_missing, "structural_callbacks_supplemented": len(added),
            "missing_process_times_after": after_missing, "added_structural_cost_per_callback_s": sum(added),
            "known_process_per_callback_sum_before_s": sum(v for v in old_costs if v is not None),
            "known_process_per_callback_sum_after_s": sum(v for v in costs if v is not None),
            "reconstructed_process_per_callback_sum_s": sum(costs) if not after_missing else None,
            "reconstructed_all_attempts_per_callback_sum_s": sum(costs) if not after_missing else None,
            "reconstructed_time_complete": not after_missing})
        require(all(runs_out[-1][k] == v for k, v in original.items()), "Original run field changed")
    write_csv(output / "callbacks_with_timing_supplement.csv", events_out)
    with (output / "callbacks_with_timing_supplement.jsonl").open("w") as stream:
        for event in events_out:
            stream.write(json.dumps(event, allow_nan=False) + "\n")
    write_csv(output / "cstr30_run_time_comparison.csv", runs_out)
    write(output / "remaining_time_gaps.json", leftovers)
    return {"runs": len(runs_out), "callbacks": len(events_out),
        "missing_before": sum(r["missing_process_times_before"] for r in runs_out),
        "supplemented_callbacks": sum(r["structural_callbacks_supplemented"] for r in runs_out),
        "missing_after": sum(r["missing_process_times_after"] for r in runs_out),
        "remaining_missing_reasons": dict(Counter(r["reason"] for r in leftovers)),
        "run_categories_unchanged": dict(Counter(r["category"] for r in runs_out)),
        "complete_cost_runs": sum(r["reconstructed_time_complete"] for r in runs_out),
        "original_event_and_run_fields_unchanged": True,
        "per_visit_cost_policy": "Sum each callback, including repeated points and initial/failed callbacks; no cache deduplication",
        "cost_interpretation": "Reconstructed from separate process measurements; not measured online DFO runtime"}


def report_results(root, output, original, guard_attempts):
    records = [read(p) for p in sorted((output / "records").glob("*.json"))]
    measured = {tuple(r["point"]): r for r in records}
    require(len(measured) == len(records) and set(measured) <= set(POINTS), "Unexpected/duplicate supplemental coordinate")
    for record in records:
        require(record["elapsed_ns"] > 0 and record["total_wall_s"] == record["elapsed_ns"] / 1e9
                and math.isfinite(record["total_wall_s"]) and record["solve_wall_s"] == 0
                and not record["accepted"] and not record["solver_called"]
                and record["case"] == "cstr" and record["cstr_size"] == 30
                and record["measurement_run_id"] == output.name and record["objective"] is None
                and record["status"] == "preprocessing_infeasible"
                and record["termination"] == "not_solved", "Invalid supplemental checkpoint")
    if records:
        write_csv(output / "structural_rejections.csv", records)
    complete = len(records) == 435
    if complete:
        combined = [{**row, "evaluation_origin": "original_465", "measurement_run_id": "dantzig_gdp_gams_20260922_050038_p4q8hy54",
                     "time_source": "original_same_attempt_csv", "measurement_scope": "Original evaluation scope; see frozen input manifest"}
                    for row in original] + records
        combined.sort(key=lambda r: tuple(json.loads(r["point"]) if isinstance(r["point"], str) else r["point"]))
        write_csv(output / "combined_cstr30_900.csv", combined)
        reread = rows(output / "combined_cstr30_900.csv")
        keys = [tuple(json.loads(r["point"])) for r in reread]
        require(len(keys) == len(set(keys)) == 900 and set(keys) == set(itertools.product(range(1, 31), repeat=2)), "Combined box coverage differs")
        original_map = {tuple(json.loads(r["point"])): r for r in original}
        for row in reread:
            old = original_map.get(tuple(json.loads(row["point"])))
            if old:
                require(all(row[k] == v for k, v in old.items()), "Original 465 CSV field changed")
            else:
                require(float(row["total_wall_s"]) > 0, "CSV rounded time to zero")
    dfo = supplement_callbacks(root, measured, output)
    summary = {"complete": complete, "expected_structural_points": 435, "measured_structural_points": len(records),
        "pending_points": len(POINTS) - len(records), "original_rows_preserved": 465,
        "combined_rows": 900 if complete else None, "all_total_times_positive_finite": True,
        "original_csv_byte_copy_matches": sha(output / "original_465.csv") == sha(root / "inputs/cstr_30/evaluations.csv"),
        "solver_calls": 0, "forbidden_entry_attempts": guard_attempts,
        "measurement_scope": SCOPE, "common_preparation_in_coordinate_times": False,
        "dfo": dfo, "updated_utc": stamp()}
    require(not guard_attempts, "Forbidden execution was attempted; run is invalid")
    if complete:
        require(dfo["supplemented_callbacks"] == 508 and dfo["missing_after"] == 7,
                "Unexpected frozen DFO accounting; inspect remaining gaps")
    write(output / "summary.json", summary)
    return summary


def pack(output):
    archive = output.with_suffix(".zip")
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for path in sorted(output.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".tmp") and path.name != ".run.lock":
                target.write(path, output.name + "/" + path.relative_to(output).as_posix())
    temporary.replace(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{sha(archive)}  {archive.name}\n")
    print(f"RESULT_DIR={output}\nRESULT_ZIP={archive}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "plan", "run", "resume", "pack"))
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.mode == "pack":
        require(args.run_dir is not None and args.run_dir.is_dir(), "Existing --run-dir required")
        pack(args.run_dir.resolve())
        return
    common_started = perf_counter_ns()
    original, historical_manifest, _ = check_inputs(ROOT)
    if args.mode == "plan":
        print(json.dumps({"original_points": 465, "missing_points": 435, "points": POINTS,
                          "expected_callback_fills": 508, "remaining_budget_errors": 7}))
        return
    evaluator, identity = prepare_evaluator(ROOT, historical_manifest)
    if args.mode == "check":
        print(json.dumps({"check": "passed", "original_points": 465, "structural_points": 435,
            "solver_probes": 0, "model_evaluations": 0, "runtime": identity}, indent=2))
        return
    if args.mode == "run":
        require(args.run_dir is None, "Use resume for an existing directory")
        args.output_root.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix="dantzig_cstr30_structural_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_"), dir=args.output_root)).resolve()
        names = verify_bundle(ROOT)
        for name in [*names, "SHA256SUMS"]:
            target = output / "reproduction" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        shutil.copyfile(ROOT / "inputs/cstr_30/evaluations.csv", output / "original_465.csv")
        write(output / "manifest.json", {"measurement_run_id": output.name, "created_utc": stamp(),
            "bundle_sha256": sha(ROOT / "SHA256SUMS"), "code_and_input_provenance": read(ROOT / "bundle_provenance.json"),
            "runtime": identity, "scope": SCOPE, "historical_manifest": historical_manifest,
            "solver_calls_permitted": False, "dfo_search_executed": False})
    else:
        require(args.run_dir is not None and args.run_dir.is_dir(), "Existing --run-dir required")
        output = args.run_dir.resolve()
        manifest = read(output / "manifest.json")
        require(manifest["bundle_sha256"] == sha(ROOT / "SHA256SUMS") and manifest["runtime"] == identity, "Resume environment/code changed")
        verify_bundle(output / "reproduction")
    import fcntl
    with (output / ".run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (output / "records").mkdir(exist_ok=True)
        invocation = uuid4().hex
        common_ns = perf_counter_ns() - common_started
        write(output / "invocations" / f"{invocation}.json", {"invocation_id": invocation, "created_utc": stamp(),
            "common_preparation_wall_ns": common_ns, "common_preparation_wall_s": common_ns / 1e9,
            "scope": "Input verification, library/source-definition preloading and output/snapshot preparation; no warm-up model/solve",
            "included_in_coordinate_times": False})
        attempts = []
        try:
            with no_solver() as attempts:
                for index, point in enumerate(POINTS, 1):
                    target = output / "records" / f"point_{point[0]:02d}_{point[1]:02d}.json"
                    if target.exists():
                        continue
                    record = measure_one(evaluator, point, output.name, invocation)
                    write(target, record)
                    if index % 25 == 0 or index == len(POINTS):
                        print(f"COMPLETED {index}/435; solver calls=0", flush=True)
            summary = report_results(ROOT, output, original, len(attempts))
            verify_bundle(ROOT)
            print(json.dumps(summary, indent=2), flush=True)
        except BaseException as error:
            write(output / "interruption.json", {"error": f"{type(error).__name__}: {error}",
                "forbidden_entry_attempts": len(attempts), "updated_utc": stamp(), "resume_skips_completed_points": True})
            raise
        finally:
            pack(output)


if __name__ == "__main__":
    main()
