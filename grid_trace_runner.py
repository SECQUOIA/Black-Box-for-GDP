"""Separate, restartable RBFOpt/BAM grid runs with every objective callback saved."""

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parent
KIND = "grid_dfo_callback_trace_v1"
ORIGINAL_RUNNER_SHA256 = "35926bdc10a5915f701d0522a49f9887c501b5781608a90992e0ee33be4de895"
RESULT_ABS_TOLERANCE = 1e-12
THREADS = {name: "1" for name in (
    "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
THREADS.update(OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def source_files():
    names = (
        "grid_trace_runner.py", "run_grid_trace_dantzig.sh", "requirements-grid-trace.txt",
        "benchmark.py", "grid_dsda.py", "dsda_protocol.py", "instrumentation.py", "evaluation_trace.py",
        "cpu_affinity.py", "case_studies/__init__.py", "case_studies/common.py",
        "case_studies/bam_common.py", "fmqa_benchmark/__init__.py",
        "fmqa_benchmark/protocol.py", "fmqa_benchmark/grid_protocol.py",
        "docs/grid_trace_dantzig.md", "LICENSE",
    )
    return sorted([ROOT / name for name in names]
                  + list((ROOT / "benchmark_grids").glob("*.csv"))
                  + [ROOT / "fmqa_benchmark/reference/grid" / name for name in
                     ("original.csv", "bam5.csv", "comparison_audit.json", "reference.json")])


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()}


def plan(method, names=None, seeds=None, budgets=(10, 30, 50, 70, 100)):
    from fmqa_benchmark.grid_protocol import reference_grid_plan
    if method not in ("rbfopt", "bam"):
        raise ValueError("Select exactly one method: rbfopt or bam")
    if seeds is not None and (not seeds or len(set(seeds)) != len(seeds)
                              or not set(seeds) <= set(range(10))):
        raise ValueError("Select distinct original seeds 0..9")
    return [{**spec, "method": method, "job_id": spec["job_id"] + "_" + method}
            for spec in reference_grid_plan(names, seeds, budgets)]


def runtime(config):
    from cpu_affinity import affinity_record, pin_cpu
    from benchmark import resolve_required_solver_paths
    cpu = pin_cpu(config["cpu"])
    expected = dict(line.split("==") for line in (ROOT / "requirements-grid-trace.txt").read_text().splitlines()
                    if line and not line.startswith("#"))
    # Each method needs only its own optimizer installation/license.
    expected.pop("bam-solver" if config["method"] == "rbfopt" else "rbfopt")
    versions = {name: importlib.metadata.version(name) for name in expected}
    if versions != expected:
        raise ValueError(f"Environment differs from requirements-grid-trace.txt: {versions}")
    solvers = {}
    if config["method"] == "rbfopt":
        paths = resolve_required_solver_paths(minlp_solver_path=config["bonmin"],
                                              nlp_solver_path=config["ipopt"])
        for name, path in zip(("bonmin", "ipopt"), paths):
            if not os.access(path, os.X_OK):
                raise ValueError(f"Solver is not executable: {path}")
            config[name] = str(Path(path).resolve())
            solvers[name] = sha(path)
    else:
        import bam
        path = Path(config["bam_license"])
        if not path.is_file():
            raise ValueError("Set BAM_LICENSE_FILE or --bam-license to the existing license file")
        bam.set_license_file(str(path))
        native = list(bam.Bam.get_solver_version())
        if native != [2026, 9, 10]:
            raise ValueError(f"Expected BAM 5 native version 2026-09-10; got {native}")
        solvers = {"bam_native": native, "bam_license_sha256": sha(path)}
    return {"host": platform.node(), "platform": platform.platform(), "python": platform.python_version(),
            "versions": versions, "solvers": solvers, "affinity": affinity_record(cpu),
            "thread_environment": {name: os.environ.get(name) for name in THREADS}}


def validate_grid_events(events, record, spec):
    from evaluation_trace import validate_events
    from fmqa_benchmark.grid_protocol import grid_problem
    validate_events(events, record)
    if [e["point"] for e in events[:3]] != spec["starting_points"]:
        raise ValueError("Trace initial coordinates differ from the frozen ordered design")
    oracle = grid_problem(spec["csv_name"])["objective"]
    seen, best, previous_time = set(), math.inf, 0.0
    for event in events:
        point = tuple(event["point"])
        requested = event["requested_point"]
        if len(point) != 2 or any(type(x) is not int or not 0 <= x <= 30 for x in point):
            raise ValueError("Trace contains a non-grid coordinate")
        if [int(round(x)) for x in requested] != list(point):
            raise ValueError("Requested and evaluated coordinates differ")
        best = min(best, oracle(point))
        if event["value"] != oracle(point) or event["incumbent"] != best:
            raise ValueError("Trace objective/incumbent differs from original grid CSV")
        if event["repeated_point"] != (point in seen):
            raise ValueError("Incorrect repeated-point marker")
        seen.add(point)
        if not (previous_time <= event["started_elapsed_s"] <= event["completed_elapsed_s"]
                and 0 <= event["objective_wall_s"] <= event["completed_elapsed_s"] - event["started_elapsed_s"] + 1e-9):
            raise ValueError("Invalid callback clock sequence")
        previous_time = event["completed_elapsed_s"]
    # A native solver may round its returned objective by a few ULPs. Keep
    # callback/CSV and returned-coordinate checks exact; tolerate roundoff
    # only when comparing the native scalar result with the observed minimum.
    if (record["unique_evals"] != len(seen)
            or not math.isclose(record["best_value"], best, rel_tol=0.0, abs_tol=RESULT_ABS_TOLERANCE)
            or oracle(record["best_point"]) != best):
        raise ValueError(
            f"Final optimizer result disagrees with callback history: reported={record['best_value']!r}, "
            f"observed={best!r}, returned_point_value={oracle(record['best_point'])!r}, "
            f"unique_evals={record['unique_evals']}, observed_unique={len(seen)}")


def lookup(spec, config, directory):
    from benchmark import run_rbfopt_benchmark_case, run_bam_benchmark_case
    from evaluation_trace import EvaluationTrace
    from grid_dsda import load_grid_csv
    csv_path = ROOT / "benchmark_grids" / spec["csv_name"]
    _, grid = load_grid_csv(csv_path)
    kwargs = dict(csv_path=csv_path, grid=grid, lower_bounds=[0, 0], upper_bounds=[30, 30],
                  starting_points=spec["starting_points"], seed=spec["seed"], n_starts=3,
                  max_evals=spec["max_evaluations"], target_value=min(grid.values()), verbose=True)
    if spec["method"] == "rbfopt":
        runner = run_rbfopt_benchmark_case
        kwargs.update(minlp_solver_path=config["bonmin"], nlp_solver_path=config["ipopt"])
    else:
        runner = run_bam_benchmark_case
        kwargs["bam_license_file"] = config["bam_license"]
    with EvaluationTrace(directory / "lookup.csv", spec) as trace:
        record = runner(**kwargs)["result_record"]
        # Stop the search clock before validation and export.
        elapsed = trace.timer() - trace.origin
        validate_grid_events(trace.events, record, spec)
        artifact = trace.complete(record)
    return {"spec": spec, "status": "completed", "result_record": record, "trace": artifact,
            "search_wall_s": elapsed, "lookup_wall_s": sum(e["objective_wall_s"] for e in trace.events),
            "budget_exceeded": record["total_evals"] > spec["max_evaluations"],
            "completed_utc": now()}


def worker(directory, attempt, job_id):
    run = read(directory / "run.json")
    spec = next(spec for spec in run["plan"] if spec["job_id"] == job_id)
    from cpu_affinity import pin_cpu
    pin_cpu(run["config"]["cpu"])
    try:
        result = lookup(spec, run["config"], attempt)
        save(attempt / "result.json", result)
        save(attempt / "complete.json", {"result_sha256": sha(attempt / "result.json")})
    except Exception as error:
        traceback.print_exc()
        save(attempt / "error.json", {"type": type(error).__name__, "message": str(error), "utc": now()})
        return 1
    return 0


def completed(job, spec):
    for attempt in sorted(job.glob("attempt_*"), reverse=True):
        marker = attempt / "complete.json"
        if not marker.exists():
            continue
        if read(marker)["result_sha256"] != sha(attempt / "result.json"):
            raise ValueError(f"Saved result checksum mismatch: {attempt}")
        result = read(attempt / "result.json")
        if result["spec"] != spec or result["status"] != "completed":
            raise ValueError("Saved run does not match the frozen plan")
        trace = attempt / result["trace"]["path"]
        if sha(trace) != result["trace"]["sha256"]:
            raise ValueError(f"Trace checksum mismatch: {trace}")
        entries = [json.loads(line) for line in trace.read_text().splitlines()]
        if (entries[0]["event"] != "run_start" or entries[0]["run_key"] != spec
                or entries[-1]["event"] != "run_complete"
                or entries[-1]["result_record"] != result["result_record"]):
            raise ValueError("Trace header/footer does not match its result")
        events = entries[1:-1]
        validate_grid_events(events, result["result_record"], spec)
        return attempt, result, events
    return None


@contextmanager
def locked(directory):
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("This run is active; wait for it to stop before resuming/packing") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def ensure_stopped(directory):
    for path in (directory / "jobs").glob("*/attempt_*/process.json"):
        proc = Path(f"/proc/{read(path)['pid']}/cmdline")
        if proc.exists() and str(path.parent).encode() in proc.read_bytes():
            raise RuntimeError(f"Previous worker is still running: {path}")


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    except ProcessLookupError:
        return
    # Terminate any remaining solver grandchildren as well.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def launch(directory, spec, limit):
    job = directory / "jobs" / spec["job_id"]
    attempt = job / f"attempt_{time.time_ns()}"
    attempt.mkdir(parents=True)
    command = [sys.executable, str(ROOT / "grid_trace_runner.py"), "worker", "--run-dir", str(directory),
               "--attempt-dir", str(attempt), "--job-id", spec["job_id"]]
    with (attempt / "run.log").open("w") as log:
        process = subprocess.Popen(command, cwd=attempt, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        save(attempt / "process.json", {"pid": process.pid, "started_utc": now()})
        try:
            process.wait(timeout=limit or None)
        except BaseException:
            stop(process)
            raise
    if process.returncode or not (attempt / "complete.json").exists():
        raise RuntimeError(f"Job failed; partial trace retained. Inspect {attempt / 'run.log'}")
    return completed(job, spec)


def csv_export(path, rows, fields):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    temporary.replace(path)


def export(directory, run):
    from instrumentation import RESULT_FIELDS
    results, evaluations, points = [], [], set()
    for spec in run["plan"]:
        found = completed(directory / "jobs" / spec["job_id"], spec)
        if found is None:
            continue
        attempt, result, events = found
        results.append(result["result_record"])
        for event in events:
            evaluations.append({"job_id": spec["job_id"], "csv_name": spec["csv_name"],
                                "method": spec["method"], "seed": spec["seed"],
                                "max_evals": spec["max_evaluations"],
                                "trace_path": (attempt / result["trace"]["path"]).relative_to(directory).as_posix(),
                                **event})
            points.add((spec["csv_name"], *event["point"]))
    csv_export(directory / "benchmark.csv", results, RESULT_FIELDS)
    if evaluations:
        csv_export(directory / "evaluations.csv", evaluations, list(evaluations[0]))
    save(directory / "visited_points.json", [{"csv_name": n, "point": [x, y]} for n, x, y in sorted(points)])
    summary = {"planned_runs": len(run["plan"]), "completed_runs": len(results),
               "evaluation_callbacks": len(evaluations), "unique_grid_points": len(points),
               "all_completed": len(results) == len(run["plan"]), "updated_utc": now()}
    save(directory / "summary.json", summary)
    return summary


def pack(directory):
    ensure_stopped(directory)
    summary = export(directory, read(directory / "run.json"))
    path = directory.with_suffix(".zip")
    temporary = path.with_suffix(".zip.tmp")
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != ".lock"
                   and not p.name.endswith(".tmp"))
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.write(item, directory.name + "/" + item.relative_to(directory).as_posix())
        archive.writestr(directory.name + "/SHA256SUMS", "".join(
            f"{sha(p)}  {p.relative_to(directory).as_posix()}\n" for p in files))
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip():
            raise RuntimeError("Result ZIP CRC failed")
    temporary.replace(path)
    path.with_suffix(".zip.sha256").write_text(f"{sha(path)}  {path.name}\n")
    print(json.dumps(summary), flush=True)
    print(f"RESULT_ZIP={path}", flush=True)


def upgrade_roundoff_validation(directory, run, hashes):
    """Audit the one supported validation-only update, retaining original inputs."""
    original = run["source_sha256"]
    changed = {name for name in set(original) | set(hashes) if original.get(name) != hashes.get(name)}
    if (run.get("resume_source_sha256") is not None or changed != {"grid_trace_runner.py"}
            or original.get("grid_trace_runner.py") != ORIGINAL_RUNNER_SHA256):
        raise ValueError("Roundoff fix accepts only the original runner with all other inputs unchanged")
    for name, digest in original.items():
        if sha(directory / "source" / name) != digest:
            raise ValueError(f"Original source snapshot changed: {name}")
    finished = sum(completed(directory / "jobs" / spec["job_id"], spec) is not None for spec in run["plan"])
    audit = directory / "validation_fix"
    audit.mkdir(exist_ok=True)
    before = audit / "original_run.json"
    if before.exists() and read(before) != run:
        raise ValueError("A different validation update was already prepared for this run")
    save(before, run)
    shutil.copy2(ROOT / "grid_trace_runner.py", audit / "grid_trace_runner.py")
    detail = {"applied_utc": now(), "completed_runs_preserved": finished,
              "original_runner_sha256": original["grid_trace_runner.py"],
              "new_runner_sha256": hashes["grid_trace_runner.py"],
              "original_run_sha256": sha(before), "returned_objective_abs_tolerance": RESULT_ABS_TOLERANCE,
              "scope": "Native returned scalar only; callback values, points, optimizer settings and search unchanged"}
    save(audit / "manifest.json", detail)
    run.update(resume_source_sha256=hashes, validation_fix=detail)
    save(directory / "run.json", run)
    print(f"VALIDATION_FIX_APPLIED: preserved {finished} completed runs", flush=True)


def execute(directory, run, *, allow_roundoff_fix=False):
    with locked(directory):
        ensure_stopped(directory)
        hashes = source_hashes()
        changed = hashes != run.get("resume_source_sha256", run["source_sha256"])
        if changed and not allow_roundoff_fix:
            raise ValueError("Runner/input files changed; resume using the frozen source snapshot")
        actual = runtime(run["config"])
        if actual != run["runtime"]:
            raise ValueError("Runtime/CPU/host changed; start a new experiment instead of mixing timings")
        if changed:
            upgrade_roundoff_validation(directory, run, hashes)
        try:
            for i, spec in enumerate(run["plan"], 1):
                if completed(directory / "jobs" / spec["job_id"], spec) is not None:
                    continue
                save(directory / "progress.json", {"index": i, "total": len(run["plan"]),
                                                    "job_id": spec["job_id"], "updated_utc": now()})
                print(f"[{i}/{len(run['plan'])}] {spec['job_id']}", flush=True)
                _, result, _ = launch(directory, spec, run["config"]["max_run_seconds"])
                print(f"  {result['trace']['evaluations']} callbacks, {result['search_wall_s']:.3f}s", flush=True)
        finally:
            pack(directory)


def bundle(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "grid_dfo_trace_runner/"
    files = source_files()
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.write(item, prefix + item.relative_to(ROOT).as_posix())
        guide = ROOT / "docs/grid_trace_dantzig.md"
        archive.write(guide, prefix + "README.md")
        archive.writestr(prefix + "SHA256SUMS", "".join(
            f"{sha(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in files) + f"{sha(guide)}  README.md\n")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise RuntimeError("Runner ZIP CRC failed")
    path.with_suffix(".zip.sha256").write_text(f"{sha(path)}  {path.name}\n")
    print(path)


def main():
    os.environ.update(THREADS, PYTHONUNBUFFERED="1")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "check", "run", "resume", "status", "pack", "bundle", "worker"))
    parser.add_argument("--method", choices=("rbfopt", "bam"))
    parser.add_argument("--grids", help="Comma-separated grid names; default all 21")
    parser.add_argument("--seeds", default="0-9")
    parser.add_argument("--budgets", default="10,30,50,70,100")
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--bonmin", default="")
    parser.add_argument("--ipopt", default="")
    parser.add_argument("--bam-license", default=os.environ.get("BAM_LICENSE_FILE", ""))
    parser.add_argument("--max-run-seconds", type=float, default=0, help="0: no external timeout")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/grid_dfo_trace")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--allow-roundoff-fix", action="store_true",
                        help="Resume the original runner with the audited native-result rounding fix")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--attempt-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--job-id", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.allow_roundoff_fix and args.mode != "resume":
        parser.error("--allow-roundoff-fix is only valid with resume")
    if args.mode == "bundle":
        if args.output is None:
            parser.error("bundle requires --output")
        return bundle(args.output)
    if args.mode in ("worker", "resume", "status", "pack"):
        if args.run_dir is None:
            parser.error(f"{args.mode} requires --run-dir")
        directory = args.run_dir.resolve()
        run = read(directory / "run.json")
        if run["kind"] != KIND:
            raise ValueError("Not a grid DFO trace run")
        if args.mode == "worker":
            return worker(directory, args.attempt_dir, args.job_id)
        if args.mode == "resume":
            return execute(directory, run, allow_roundoff_fix=args.allow_roundoff_fix)
        if args.mode == "status":
            count = sum(any((directory / "jobs" / s["job_id"]).glob("attempt_*/complete.json")) for s in run["plan"])
            print(json.dumps({"planned_runs": len(run["plan"]), "completion_markers": count,
                              "progress": read(directory / "progress.json") if (directory / "progress.json").exists() else None}))
            return
        with locked(directory):
            return pack(directory)
    if args.method is None:
        parser.error("--method rbfopt or --method bam is required; each has a separate run directory")
    from benchmark import parse_int_sequence
    jobs = plan(args.method, args.grids.split(",") if args.grids else None,
                parse_int_sequence(args.seeds), parse_int_sequence(args.budgets))
    if args.mode == "plan":
        print(json.dumps({"method": args.method, "runs": len(jobs), "first": jobs[0], "last": jobs[-1]}, indent=2))
        return
    if not math.isfinite(args.max_run_seconds) or args.max_run_seconds < 0:
        parser.error("--max-run-seconds must be finite and nonnegative")
    if sys.platform == "linux" and args.cpu is None:
        parser.error("Choose an explicit --cpu for this method")
    config = {"method": args.method, "cpu": args.cpu, "bonmin": args.bonmin, "ipopt": args.ipopt,
              "bam_license": str(Path(args.bam_license).expanduser().resolve()) if args.bam_license else "",
              "max_run_seconds": args.max_run_seconds}
    environment = runtime(config)
    if args.mode == "check":
        with tempfile.TemporaryDirectory(prefix="grid_trace_check_") as temporary:
            smoke = {**jobs[0], "max_evaluations": 10}
            result = lookup(smoke, config, Path(temporary))
            print(json.dumps({"planned_runs": len(jobs), "runtime": environment,
                              "smoke_callbacks": result["trace"]["evaluations"], "status": "passed"}, indent=2))
        return
    args.output_root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=f"grid_trace_{args.method}_{time.strftime('%Y%m%d_%H%M%S')}_",
                                      dir=args.output_root)).resolve()
    hashes = source_hashes()
    for name in hashes:
        target = directory / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    run = {"kind": KIND, "created_utc": now(), "config": config, "runtime": environment,
           "plan": jobs, "source_sha256": hashes,
           "protocol": {"evaluation": "original CSV lookup; new rerun, not an archived path",
                        "initialization": "three frozen ordered points; counted in total budget",
                        "rbfopt": "MSRSM, rbf=auto, global_search_method=solver, original defaults",
                        "bam": "5.0.0; original x_evaluated/f_evaluated warm start; seed labels initial design",
                        "clock": "search_wall_s includes setup and trace writes, excludes CSV loading, validation, worker startup",
                        "callbacks": "all actual objective calls, including repeats; internal cache hits are not evaluations"}}
    save(directory / "run.json", run)
    print(f"RUN_DIR={directory}", flush=True)
    execute(directory, run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
