"""Uploadable 21-grid GDP comparisons and exhaustive single-thread IPOPT timings."""

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
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent
KIND = "grid_gdp_process_solver_profile_v1"
THREADS = {
    name: "1"
    for name in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "GOTO_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "NUMEXPR_MAX_THREADS",
    )
}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def source_files():
    names = (
        "grid_gdp_benchmark.py",
        "gdp_compare.py",
        "cpu_affinity.py",
        "run_grid_gdp_dantzig.sh",
        "requirements-gdp.txt",
        "requirements-gdp-comparison.txt",
        "LICENSE",
        "docs/grid_gdp.md",
        "docs/grid_gdp_benchmark.md",
        "grid_gdp_process_profile.json",
    )
    return sorted(
        [ROOT / n for n in names]
        + list((ROOT / "gdp_models").glob("*.py"))
        + list((ROOT / "benchmark_grids").glob("*.csv"))
    )


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()}


def record_hash(record):
    return hashlib.sha256(
        json.dumps(
            record, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def append_record(path, record):
    with Path(path).open("a") as stream:
        stream.write(
            json.dumps(
                {"record": record, "sha256": record_hash(record)}, allow_nan=False
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def journal(path, *, repair=False):
    path = Path(path)
    if not path.exists():
        return []
    records, offset = [], 0
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            if i != len(lines) - 1 or line.endswith(b"\n"):
                raise ValueError(f"Corrupt timing journal: {path}")
            if repair:
                path.write_bytes(data[:offset])
            break
        if record_hash(entry["record"]) != entry["sha256"]:
            raise ValueError(f"Timing checksum mismatch: {path}")
        records.append(entry["record"])
        offset += len(line)
    if repair and offset == len(data) and data and not data.endswith(b"\n"):
        with path.open("ab") as stream:
            stream.write(b"\n")
    return records


@contextmanager
def locked(directory):
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "Run is active; do not resume or pack it concurrently"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def runtime(config, *, exercise=False, directory=None):
    from cpu_affinity import affinity_record, pin_cpu
    from gdp_models.grid_benchmark import ExplicitGAMS, method_config
    from gdp_models import comparison as impl
    import pyomo.environ as pyo

    cpu = pin_cpu(config["cpu"])
    executable = Path(config["executable"])
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"Missing GAMS executable: {executable}")
    if importlib.metadata.version("pyomo") != "6.10.0":
        raise ValueError("Use Pyomo 6.10.0, matching the process benchmark")
    version = list(ExplicitGAMS(str(executable)).version())
    config["gams_version"] = version
    expected = [int(x) for x in config["expected_gams_version"].split(".")]
    if version[: len(expected)] != expected:
        raise ValueError(f"Expected GAMS {expected}, found {version}")
    mcpp = None
    if "benchmark" in config["phases"] and "gloa" in config["methods"]:
        from pyomo.contrib.mcpp.pyomo_mcpp import mcpp_available, McCormick
        from pyomo.common.fileutils import find_library

        if not mcpp_available():
            raise ValueError(
                "GLOA requires the existing MC++ build; set PYOMO_CONFIG_DIR or run setup"
            )
        model = pyo.ConcreteModel()
        model.x = pyo.Var(bounds=(0, 2), initialize=1)
        bounds = McCormick(model.x**2)
        if bounds.lower() > 0 or bounds.upper() < 4:
            raise ValueError("MC++ arithmetic test failed")
        mcpp = sha(find_library("mcppInterface"))
    if exercise:
        directory.mkdir(parents=True, exist_ok=True)
        if "points" in config["phases"]:
            impl.smoke_solvers(str(executable), directory / "ipopt", ("ipopt",))
        if "benchmark" in config["phases"]:
            if set(config["methods"]) & {"ric", "gloa", "loa"}:
                impl.smoke_solvers(
                    str(executable),
                    directory / "baron_highs",
                    ("baron_nlp", "highs"),
                    config=method_config(config, "ric"),
                )
            if set(config["methods"]) & {"bigm", "hull"}:
                impl.smoke_solvers(
                    str(executable),
                    directory / "baron_cplex",
                    ("baron", "cplex"),
                    config=method_config(config, "hull"),
                )
    return {
        "host": os.uname().nodename,
        "python": sys.version,
        "gams_version": version,
        "gams_sha256": sha(executable),
        "affinity": affinity_record(cpu),
        "mcpp_sha256": mcpp,
        "versions": {
            n: importlib.metadata.version(n)
            for n in ("pyomo", "numpy", "sympy", "networkx")
        },
        "thread_environment": {n: os.environ.get(n) for n in THREADS},
    }


def verify_points(rows, name, indices):
    from gdp_models.grid import GRID_DIR, _read_reference

    reference, _ = _read_reference(GRID_DIR / f"{name}.csv")
    seen = set()
    for row in rows:
        index = row["flat_index"]
        if (
            row["grid_name"] != name
            or index not in indices
            or index in seen
            or row["point"] != [index // 31, index % 31]
        ):
            raise ValueError("Timing journal differs from selected grid/point plan")
        seen.add(index)
        if row["accepted"] and (
            not row["ipopt_invoked"]
            or row["threads"] != 1
            or abs(row["objective"] - reference[tuple(row["point"])]) > 1e-12
        ):
            raise ValueError("Accepted point is inconsistent with CSV/solver evidence")
    return seen


def point_worker(directory, name):
    from gdp_models.grid_benchmark import prepare_grid, measure_point
    from gdp_models.grid import GRID_DIR, _read_reference

    run = read(directory / "run.json")
    config = run["config"]
    from cpu_affinity import pin_cpu

    pin_cpu(config["cpu"])
    job = directory / "points" / name
    job.mkdir(parents=True, exist_ok=True)
    _, preparation = prepare_grid(name)
    save(job / f"preparation_{time.time_ns()}.json", preparation)
    path = job / "evaluations.jsonl"
    saved = journal(path, repair=True)
    seen = verify_points(saved, name, config["point_indices"])
    reference, _ = _read_reference(GRID_DIR / f"{name}.csv")
    for index in config["point_indices"]:
        if index in seen:
            continue
        point = [index // 31, index % 31]
        save(
            job / "active.json",
            {"point": point, "started_monotonic_s": time.monotonic(), "utc": now()},
        )
        record = measure_point(
            name, point, config, job / "work", job / "ipopt.log", reference
        )
        (job / "active.json").unlink(missing_ok=True)
        if not record["accepted"]:
            append_record(job / "failures.jsonl", record)
            raise RuntimeError(
                f"IPOPT point failed; see {job / 'ipopt.log'} and timing journal"
            )
        append_record(path, record)
        seen.add(index)
        if len(seen) % 25 == 0 or len(seen) == len(config["point_indices"]):
            save(
                job / "progress.json",
                {
                    "completed": len(seen),
                    "planned": len(config["point_indices"]),
                    "utc": now(),
                },
            )
            print(
                f"{name}: {len(seen)}/{len(config['point_indices'])} points", flush=True
            )
    if any(not r["accepted"] for r in saved):
        raise RuntimeError(
            "Earlier solver failure retained; inspect it before treating the grid as complete"
        )
    save(
        job / "complete.json",
        {"journal_sha256": sha(path), "points": len(seen), "utc": now()},
    )


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def process_identity(pid):
    stat = Path(f"/proc/{pid}/stat")
    try:
        ticks = stat.read_text().rpartition(")")[2].split()[19]
    except (OSError, IndexError):
        ticks = None
    return {"pid": pid, "linux_start_ticks": ticks, "utc": now()}


def ensure_stopped(directory):
    paths = [
        *(directory / "points").glob("*/process.json"),
        *(directory / "benchmark").glob("*/*/process.json"),
    ]
    for path in paths:
        saved = read(path)
        current = process_identity(saved["pid"])
        if (
            saved.get("linux_start_ticks") is not None
            and saved["linux_start_ticks"] == current["linux_start_ticks"]
        ):
            raise RuntimeError(f"Previous worker is still running: {path}")


def launch_points(directory, name, config):
    job = directory / "points" / name
    job.mkdir(parents=True, exist_ok=True)
    marker = job / "complete.json"
    if marker.exists():
        if read(marker)["journal_sha256"] != sha(job / "evaluations.jsonl"):
            raise ValueError(f"Completed point journal changed: {job}")
        return
    command = [
        sys.executable,
        str(ROOT / "grid_gdp_benchmark.py"),
        "worker",
        "--run-dir",
        str(directory),
        "--grids",
        name,
    ]
    with (job / "worker.log").open("a") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        save(job / "process.json", process_identity(process.pid))
        started = time.monotonic()
        try:
            while process.poll() is None:
                active = job / "active.json"
                if active.exists():
                    point_start = read(active)["started_monotonic_s"]
                    if (
                        point_start >= started
                        and time.monotonic() - point_start
                        > config["point_seconds"] + 120
                    ):
                        raise TimeoutError(
                            f"Point exceeded solver limit plus 120 s cleanup allowance: {name}"
                        )
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    progress = (
                        read(job / "progress.json")
                        if (job / "progress.json").exists()
                        else {}
                    )
                    print(
                        f"  {name}: {progress.get('completed', 0)}/{len(config['point_indices'])} recorded points",
                        flush=True,
                    )
        except BaseException:
            stop(process)
            raise
    if process.returncode or not marker.exists():
        raise RuntimeError(
            f"Point worker stopped; completed points preserved. Inspect {job / 'worker.log'}"
        )


def csv_file(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: json.dumps(v) if isinstance(v, (dict, list)) else v
                    for k, v in row.items()
                }
            )
    temporary.replace(path)


def seal_benchmark(job):
    paths = sorted(
        p
        for p in job.rglob("*")
        if p.is_file() and p.name != "terminal.json" and not p.name.endswith(".tmp")
    )
    save(
        job / "terminal.json",
        {"files_sha256": {p.relative_to(job).as_posix(): sha(p) for p in paths}},
    )


def benchmark_complete(job):
    marker = job / "terminal.json"
    if not marker.exists():
        return False
    for name, digest in read(marker)["files_sha256"].items():
        if sha(job / name) != digest:
            raise ValueError(f"Benchmark artifact checksum mismatch: {job / name}")
    return read(job / "result.json").get("status") not in {"running", "interrupted"}


def benchmark_plan(config):
    """An explicit retry plan is a list of pairs, never a Cartesian product."""
    jobs = config.get("benchmark_jobs")
    if jobs is None:
        return [
            {"grid_name": name, "method": method}
            for name in config["grids"] for method in config["methods"]
        ]
    seen = set()
    for job in jobs:
        pair = (job["grid_name"], job["method"])
        if (pair in seen or pair[0] not in config["grids"]
                or pair[1] not in config["methods"]):
            raise ValueError("Invalid or duplicate benchmark retry pair")
        seen.add(pair)
    return jobs


def error_kind(record, job):
    message = record.get("message", "")
    if "IntervalException" in message:
        return "fbbt"
    if "DifferentiationException" in message:
        return "differentiation"
    logfile = job / "run.log"
    log = logfile.read_text(errors="replace") if logfile.exists() else ""
    if "network session" in log and "Curl error:" in log:
        return "network"
    return "other"


def select_error_jobs(directory, kind="all"):
    """Read sealed failed results, preserving all parent files unchanged."""
    parent = read(directory / "run.json")
    if parent["kind"] != KIND:
        raise ValueError("Not a grid GDP benchmark run")
    ensure_stopped(directory)
    selected = []
    for pair in benchmark_plan(parent["config"]):
        job = directory / "benchmark" / pair["grid_name"] / pair["method"]
        path = job / "result.json"
        if not path.exists():
            continue
        result = read(path)
        if result.get("status") != "error":
            continue
        if not benchmark_complete(job):
            raise ValueError(f"Failed job is not sealed: {job}")
        category = error_kind(result, job)
        if kind != "all" and category != kind:
            continue
        selected.append({
            **pair, "error_kind": category,
            "previous_message": result.get("message"),
            "previous_result_sha256": sha(path),
            "previous_terminal_sha256": sha(job / "terminal.json"),
        })
    return parent, selected


def retry_errors(args):
    if args.run_dir is None:
        raise ValueError("retry-errors requires --run-dir pointing to the original run")
    original = args.run_dir.resolve()
    parent, selected = select_error_jobs(original, args.error_kind)
    fix_profile = getattr(args, "retry_fix_profile", None)
    if parent["config"].get("retry_fix_profile") and not fix_profile:
        raise ValueError("Retrying a corrected run requires an explicit --retry-fix-profile")
    if fix_profile:
        from gdp_models.grid_retry_fixes import PROFILE, supported_retry

        if fix_profile != PROFILE or any(not supported_retry(job) for job in selected):
            raise ValueError("Correction profile only supports the ten diagnosed FBBT/abs(0) error pairs")
    plan = {
        "source_run": str(original),
        "source_run_json_sha256": sha(original / "run.json"),
        "error_kind": args.error_kind,
        "planned_points": 0,
        "planned_benchmarks": len(selected),
        "jobs": selected,
        "policy": "One fresh attempt per selected error; original solver settings; no error fixes or automatic repeat-until-success.",
    }
    if fix_profile:
        plan.update(retry_fix_profile=fix_profile,
                    policy="One corrected attempt per selected error; original model, solver settings and time limit; separately labelled Pyomo correction profile; no point measurements.")
    print(json.dumps(plan, indent=2), flush=True)
    if args.dry_run or not selected:
        return
    if args.grids or args.point_indices:
        raise ValueError("retry-errors selects exact pairs from the original records")
    config = json.loads(json.dumps(parent["config"]))
    if args.cpu is not None and args.cpu != config["cpu"]:
        raise ValueError(f"Retry must use original CPU {config['cpu']}; set GRID_GDP_CPU accordingly")
    config.update(
        phases=["benchmark"], point_indices=[],
        grids=list(dict.fromkeys(job["grid_name"] for job in selected)),
        methods=list(dict.fromkeys(job["method"] for job in selected)),
        benchmark_jobs=[
            {key: job[key] for key in ("grid_name", "method")} for job in selected
        ],
    )
    if fix_profile:
        config["retry_fix_profile"] = fix_profile
    hashes = source_hashes()
    old_hashes = parent["source_sha256"]
    changed = {
        name: {"original": old_hashes.get(name), "retry": hashes.get(name)}
        for name in sorted(set(hashes) | set(old_hashes))
        if hashes.get(name) != old_hashes.get(name)
    }
    allowed_changes = {"grid_gdp_benchmark.py", "docs/grid_gdp_benchmark.md"}
    if fix_profile:
        allowed_changes.update({"gdp_models/grid_benchmark.py", "gdp_models/grid_retry_fixes.py"})
    if set(changed) - allowed_changes:
        raise ValueError(
            "Same-profile retries require unchanged models, inputs and solver code: "
            + ", ".join(sorted(set(changed) - allowed_changes))
        )
    identity = runtime(config)
    expected = dict(parent["runtime"])
    observed = dict(identity)
    if "gloa" not in config["methods"]:
        expected.pop("mcpp_sha256", None)
        observed.pop("mcpp_sha256", None)
    if observed != expected:
        raise ValueError("Retry runtime/CPU/host differs from the original run")
    output_root = args.output_root.resolve()
    if output_root == original or original in output_root.parents:
        raise ValueError("Retry output must be outside the original run directory")
    args.output_root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(
        prefix=f"grid_gdp_retry_{'fixed_' if fix_profile else ''}{args.error_kind}_{time.strftime('%Y%m%d_%H%M%S')}_",
        dir=args.output_root,
    )).resolve()
    print(f"RUN_DIR={directory}", flush=True)
    for name in hashes:
        target = directory / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    run = {
        **parent, "created_utc": now(), "config": config, "runtime": identity,
        "source_sha256": hashes,
        "retry_of": {**plan, "source_changes": changed},
        "time_policy": "Benchmark errors only; original method time limit and CPU/thread settings; no point measurements",
    }
    save(directory / "run.json", run)
    save(directory / "retry_plan.json", plan)
    try:
        runtime(config, exercise=True, directory=directory / "preflight")
    except BaseException:
        pack(directory)
        raise
    execute(directory, run)


def summarize(directory):
    from gdp_models.grid_benchmark import timing_summary

    config = read(directory / "run.json")["config"]
    points, timings, methods, failures = [], [], [], []
    for name in config["grids"]:
        rows = journal(directory / "points" / name / "evaluations.jsonl")
        verify_points(rows, name, config["point_indices"])
        points.extend(rows)
        failed = journal(directory / "points" / name / "failures.jsonl")
        failures.extend(failed)
        timings.append(
            {
                "grid_name": name,
                "failed_attempts": len(failed),
                "failed_attempt_wall_s": sum(r["point_wall_s"] for r in failed),
                **timing_summary(rows, len(config["point_indices"])),
            }
        )
        for method in (
            job["method"] for job in benchmark_plan(config) if job["grid_name"] == name
        ):
            path = directory / "benchmark" / name / method / "result.json"
            if path.exists():
                methods.append(
                    {**read(path), "terminal_verified": benchmark_complete(path.parent)}
                )
    csv_file(directory / "point_timings.csv", points)
    csv_file(directory / "point_failures.csv", failures)
    save(directory / "point_budget_summary.json", timings)
    flat = []
    for row in timings:
        flat.append(
            {k: v for k, v in row.items() if not isinstance(v, dict)}
            | {
                f"{k}_{stat}": value
                for k, stats in row.items()
                if isinstance(stats, dict)
                for stat, value in stats.items()
            }
        )
    csv_file(directory / "point_budget_summary.csv", flat)
    csv_file(directory / "benchmark.csv", methods)
    accepted = sum(r["accepted"] for r in points)
    planned_points = (
        len(config["grids"]) * len(config["point_indices"])
        if "points" in config["phases"]
        else 0
    )
    planned_methods = (
        len(benchmark_plan(config))
        if "benchmark" in config["phases"]
        else 0
    )
    finished = sum(r["terminal_verified"] for r in methods)
    report = {
        "planned_points": planned_points,
        "accepted_points": accepted,
        "attempted_points": len(points),
        "failed_point_attempts": len(failures),
        "sum_failed_point_attempt_s": sum(r["point_wall_s"] for r in failures),
        "planned_benchmarks": planned_methods,
        "finished_benchmarks": finished,
        "feasible_benchmarks": sum(
            r.get("has_feasible_solution", False) for r in methods
        ),
        "unsupported_benchmarks": sum(
            r.get("status") == "unsupported_expression" for r in methods
        ),
        "error_benchmarks": sum(r.get("status") == "error" for r in methods),
        "hard_time_limit_benchmarks": sum(
            r.get("status") == "hard_time_limit" for r in methods
        ),
        "all_jobs_finished": accepted == planned_points and finished == planned_methods,
        "sum_point_evaluation_s": sum(
            r["point_wall_s"] for r in points if r["accepted"]
        ),
        "point_timing_scope": "fresh preparation + GAMS/IPOPT invocation + verification; source audit and log archival separate",
        "utc": now(),
    }
    save(directory / "summary.json", report)
    return report


def pack(directory):
    ensure_stopped(directory)
    summary = summarize(directory)
    files = sorted(
        p
        for p in directory.rglob("*")
        if p.is_file()
        and p.name != ".lock"
        and not p.name.endswith(".tmp")
        and "work" not in p.relative_to(directory).parts
    )
    output = directory.with_name(directory.name + ".zip")
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(
                path, directory.name + "/" + path.relative_to(directory).as_posix()
            )
        archive.writestr(
            directory.name + "/SHA256SUMS",
            "".join(
                f"{sha(p)}  {p.relative_to(directory).as_posix()}\n" for p in files
            ),
        )
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip():
            raise ValueError("Result ZIP failed CRC verification")
    temporary.replace(output)
    output.with_suffix(".zip.sha256").write_text(f"{sha(output)}  {output.name}\n")
    print(json.dumps(summary), flush=True)
    print(f"RESULT_ZIP={output}", flush=True)


def execute(directory, run):
    from gdp_models.grid_benchmark import grid_template, method_config, benchmark_worker
    from gdp_compare import run_job

    config = run["config"]
    with locked(directory):
        ensure_stopped(directory)
        if source_hashes() != run["source_sha256"]:
            raise ValueError(
                "Source/input hashes changed; resume with this run's source snapshot"
            )
        if runtime(config) != run["runtime"]:
            raise ValueError(
                "Runtime/CPU/host changed; do not combine different timing environments"
            )
        try:
            if "points" in config["phases"]:
                for name in config["grids"]:
                    print(
                        f"POINTS {name}: {len(config['point_indices'])} planned",
                        flush=True,
                    )
                    launch_points(directory, name, config)
                    summarize(directory)
            if "benchmark" in config["phases"]:
                for name in config["grids"]:
                    template = grid_template(name)
                    save(directory / "preparations" / f"{name}.json", template.metadata)
                    for method in (
                        job["method"] for job in benchmark_plan(config)
                        if job["grid_name"] == name
                    ):
                        job = directory / "benchmark" / name / method
                        if job.exists():
                            if (job / "result.json").exists() and benchmark_complete(job):
                                continue
                            old = (
                                directory
                                / "previous_attempts"
                                / name
                                / f"{method}_{time.time_ns()}"
                            )
                            old.parent.mkdir(parents=True, exist_ok=True)
                            job.rename(old)
                        print(f"BENCHMARK {name}/{method}", flush=True)
                        unsupported = template.metadata["grid_preparation"][
                            "unsupported_baron_functions"
                        ]
                        if method in {"bigm", "hull"} and unsupported:
                            save(
                                job / "result.json",
                                {
                                    **template.metadata,
                                    "method": method,
                                    "status": "unsupported_expression",
                                    "unsupported_functions": unsupported,
                                    "has_feasible_solution": False,
                                    "solver_called": False,
                                    "solver_policy": method_config(config, method),
                                    "reason": "GAMS/BARON 52 does not support sin/cos; original analytic objective retained",
                                },
                            )
                        else:
                            run_job(
                                template,
                                method,
                                job,
                                method_config(config, method),
                                target=benchmark_worker,
                            )
                        seal_benchmark(job)
                        summarize(directory)
        finally:
            pack(directory)


def bundle(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    files = source_files() + [ROOT / "tests/test_grid_retry_fixes.py"]
    prefix = "grid_gdp_runner/"
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, prefix + path.relative_to(ROOT).as_posix())
        guide = ROOT / "docs/grid_gdp_benchmark.md"
        archive.write(guide, prefix + "README.md")
        archive.writestr(
            prefix + "SHA256SUMS",
            "".join(f"{sha(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in files)
            + f"{sha(guide)}  README.md\n",
        )
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise ValueError("Runner ZIP failed CRC verification")
    output.with_suffix(".zip.sha256").write_text(f"{sha(output)}  {output.name}\n")
    print(output)


def main():
    os.environ.update(
        THREADS,
        OMP_DYNAMIC="FALSE",
        MKL_DYNAMIC="FALSE",
        PYTHONUNBUFFERED="1",
        MPLBACKEND="Agg",
    )
    os.environ.setdefault("PYOMO_CONFIG_DIR", str(ROOT / ".pyomo-gdp-comparison"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "check",
            "run",
            "points",
            "pilot",
            "benchmark",
            "resume",
            "retry-errors",
            "status",
            "pack",
            "bundle",
            "worker",
            "setup",
        ),
    )
    parser.add_argument("--grids")
    parser.add_argument("--methods", default="ric,gloa,loa,bigm,hull")
    parser.add_argument("--point-indices")
    parser.add_argument("--point-seconds", type=float, default=60)
    parser.add_argument("--time-limit", type=float, default=1800)
    parser.add_argument("--cpu", type=int)
    parser.add_argument(
        "--executable", default=os.environ.get("GAMS_BIN", "/package/gams/52.2/gams")
    )
    parser.add_argument(
        "--expected-gams-version", default=os.environ.get("GDP_GAMS_VERSION", "52.2")
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "results/grid_gdp_benchmark"
    )
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--error-kind", choices=("all", "network", "fbbt", "differentiation", "other"),
        default="all", help="retry-errors: select errors by their recorded cause",
    )
    parser.add_argument("--dry-run", action="store_true", help="List retry jobs without solver calls or writing a run")
    parser.add_argument("--retry-fix-profile", choices=("pyomo610-grid-v1",),
                        help="retry-errors only: explicit changed Pyomo correction profile")
    args = parser.parse_args()
    if args.dry_run and args.mode != "retry-errors":
        parser.error("--dry-run is supported only with retry-errors")
    if args.retry_fix_profile and args.mode != "retry-errors":
        parser.error("--retry-fix-profile is supported only with retry-errors")
    if args.mode == "retry-errors":
        return retry_errors(args)
    if args.mode == "bundle":
        if args.output is None:
            parser.error("bundle requires --output")
        return bundle(args.output)
    if args.mode == "setup":
        from gdp_compare import setup_mcpp

        return setup_mcpp()
    if args.mode in {"resume", "pack", "status", "worker"}:
        if args.run_dir is None:
            parser.error("--run-dir is required")
        directory = args.run_dir.resolve()
        run = read(directory / "run.json")
        if run["kind"] != KIND:
            raise ValueError("Not a grid GDP benchmark run")
        if args.mode == "worker":
            return point_worker(directory, args.grids)
        if args.mode == "resume":
            return execute(directory, run)
        if args.mode == "status":
            return print(
                json.dumps(
                    {
                        "summary": read(directory / "summary.json")
                        if (directory / "summary.json").exists()
                        else None,
                        "points_progress": {
                            p.parent.name: read(p)
                            for p in (directory / "points").glob("*/progress.json")
                        },
                    },
                    indent=2,
                )
            )
        with locked(directory):
            return pack(directory)
    from gdp_models.grid import GRID_NAMES
    from gdp_models.grid_benchmark import METHODS, point_indices, prepare_grid

    grids = args.grids.split(",") if args.grids else list(GRID_NAMES)
    methods = args.methods.split(",")
    if not grids or len(set(grids)) != len(grids) or not set(grids) <= set(GRID_NAMES):
        parser.error("Choose distinct grid names")
    if (
        not methods
        or len(set(methods)) != len(methods)
        or not set(methods) <= set(METHODS)
    ):
        parser.error("Choose supported methods")
    if any(
        not math.isfinite(v) or v <= 0 for v in (args.point_seconds, args.time_limit)
    ):
        parser.error("Time limits must be positive")
    if sys.platform == "linux" and args.cpu is None:
        parser.error("Select an explicit --cpu")
    indices = point_indices(
        args.point_indices or ("0,240,480,720,960" if args.mode == "pilot" else None)
    )
    phases = (
        ["points"]
        if args.mode in {"points", "pilot"}
        else ["benchmark"]
        if args.mode == "benchmark"
        else ["points", "benchmark"]
    )
    executable = shutil.which(args.executable)
    if executable is None:
        parser.error("GAMS executable not found")
    config = {
        "grids": grids,
        "methods": methods,
        "phases": phases,
        "point_indices": indices,
        "point_seconds": args.point_seconds,
        "time_limit": args.time_limit,
        "relative_gap": 1e-5,
        "cpu": args.cpu,
        "executable": str(Path(executable).resolve()),
        "expected_gams_version": args.expected_gams_version,
        "objective": "original normalized analytic formula",
    }
    if args.mode == "check":
        with tempfile.TemporaryDirectory(prefix="grid_gdp_check_") as temp:
            identity = runtime(config, exercise=True, directory=Path(temp))
            audits = [prepare_grid(n)[1] for n in grids]
            print(
                json.dumps(
                    {
                        "runtime": identity,
                        "grids": [
                            {
                                "name": a["grid_name"],
                                "baron_unsupported": a["unsupported_baron_functions"],
                            }
                            for a in audits
                        ],
                    },
                    indent=2,
                )
            )
        return
    args.output_root.mkdir(parents=True, exist_ok=True)
    directory = Path(
        tempfile.mkdtemp(
            prefix=f"grid_gdp_{args.mode}_{time.strftime('%Y%m%d_%H%M%S')}_",
            dir=args.output_root,
        )
    ).resolve()
    print(f"RUN_DIR={directory}", flush=True)
    identity = runtime(config, exercise=True, directory=directory / "preflight")
    hashes = source_hashes()
    for name in hashes:
        target = directory / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    run = {
        "kind": KIND,
        "created_utc": now(),
        "config": config,
        "runtime": identity,
        "source_sha256": hashes,
        "process_profile": read(ROOT / "grid_gdp_process_profile.json"),
        "time_policy": "points first; all 961/grid; 60s solver cap/point, 1800s total/method; 1 CPU/thread",
        "fixed_point_policy": "all original variables fixed; actual IPOPT call through standard GAMS objective-variable representation",
    }
    save(directory / "run.json", run)
    execute(directory, run)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
