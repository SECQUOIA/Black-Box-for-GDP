"""Dantzig controller: plan, check, pilot, run, resume, status, summarize, pack."""

import argparse
from collections import Counter
from contextlib import contextmanager
import fcntl
import itertools
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import zipfile

from .common import METHODS, THREADS, csvrows, read, save, sha, verify


def check_inputs(root):
    digest = verify(root)
    jobs = read(root / "plan.json")
    if len(jobs) != 3430 or len({j["job_id"] for j in jobs}) != 3430:
        raise ValueError("Expected 3430 distinct planned slots")
    references = {}
    for job in jobs:
        key = job["scope"], job["case"], job["seed"]
        if key in references and references[key] != job["starts"]:
            raise ValueError("Different shared initial designs across methods/budgets")
        references[key] = job["starts"]
    missing = []
    grid_costs = {}
    for row in csvrows(root / "data/grid_point_timings.csv"):
        key = row["grid_name"], tuple(json.loads(row["point"]))
        if key in grid_costs:
            raise ValueError("Duplicate grid point cost")
        grid_costs[key] = row
    inventory = []
    for scope, case in sorted({(j["scope"], j["case"]) for j in jobs}):
        job = next(j for j in jobs if (j["scope"], j["case"]) == (scope, case))
        domain = set(
            itertools.product(
                *(range(lo, hi + 1) for lo, hi in zip(job["lower"], job["upper"]))
            )
        )
        if scope == "grid":
            values = {
                tuple(json.loads(r["Point"])): float(r["z_norm"])
                for r in csvrows(root / "frozen/grid/benchmark_grids" / f"{case}.csv")
            }
            rows = {pt: r for (name, pt), r in grid_costs.items() if name == case}
            for pt, row in rows.items():
                if (
                    row["accepted"] != "True"
                    or abs(float(row["csv_objective"]) - values[pt]) > 1e-12
                ):
                    raise ValueError("Grid cost/objective mismatch")
        else:
            raw = csvrows(root / "data" / f"cost_table_{case}.csv")
            rows = {tuple(json.loads(r["point"])): r for r in raw}
            if len(rows) != len(raw):
                raise ValueError("Duplicate Process coordinate")
        if set(rows) != domain:
            missing.extend(
                {"scope": scope, "case": case, "point": list(pt)}
                for pt in domain - set(rows)
            )
            if set(rows) - domain:
                raise ValueError("Out-of-domain cost rows")
        cost_field = "point_wall_s" if scope == "grid" else "total_wall_s"
        for pt, row in rows.items():
            if (
                not row.get(cost_field)
                or not math.isfinite(float(row[cost_field]))
                or float(row[cost_field]) <= 0
            ):
                missing.append(
                    {
                        "scope": scope,
                        "case": case,
                        "point": list(pt),
                        "reason": "missing/nonpositive cost",
                    }
                )
        inventory.append(
            {
                "scope": scope,
                "case": case,
                "points": len(rows),
                "domain_size": len(domain),
            }
        )
    return {
        "package_inventory_sha256": digest,
        "planned_jobs": len(jobs),
        "methods": dict(Counter(j["method"] for j in jobs)),
        "pilot_jobs": sum(j["pilot"] for j in jobs),
        "priority_jobs": sum(j["priority"] for j in jobs),
        "coordinate_inventory": inventory,
        "missing_costs": missing,
        "server_runtime_verified": False,
        "new_process_solves": 0,
    }


def choose(jobs, args, pilot=False):
    return [
        j
        for j in jobs
        if (not pilot or j["pilot"])
        and (
            args.scope == "all"
            or args.scope == j["scope"]
            or args.scope == "priority"
            and j["priority"]
        )
        and j["method"] in args.methods
        and (not args.cases or j["case"] in args.cases)
        and (not args.seeds or j["seed"] in args.seeds)
        and (not args.budgets or j["budget"] in args.budgets)
    ]


def python_command(config, scope):
    executable = Path(config[scope + "_python"])
    if not executable.is_file():
        raise ValueError(
            f"Existing environment unavailable: {executable}; no install attempted"
        )
    if (executable.parent.parent / "conda-meta").is_dir():
        if not config["conda"] or not Path(config["conda"]).is_file():
            raise ValueError("Existing conda environment requires --conda")
        return [
            config["conda"],
            "run",
            "--no-capture-output",
            "--prefix",
            str(executable.parent.parent),
            "python",
        ]
    return [str(executable)]


def worker_environment(root):
    return {
        **os.environ,
        **THREADS,
        "PYTHONPATH": str(root),
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "MPLBACKEND": "Agg",
    }


@contextmanager
def locked(directory):
    with (directory / "controller.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Controller or inherited worker lock is active; no duplicate launch"
            ) from exc
        # Child inherits the lock FD: abrupt controller death cannot release a live worker's lock.
        yield handle.fileno()


def attempts(directory, job):
    return sorted((directory / "jobs" / job["job_id"]).glob("attempt_*"))


def selected_result(directory, job):
    for attempt in attempts(directory, job):
        if not (attempt / "seal.json").exists():
            continue
        seal = read(attempt / "seal.json")
        for name, digest in seal.items():
            if sha(attempt / name) != digest:
                raise ValueError(f"Completed job modified: {attempt / name}")
        if read(attempt / "job.json") != job:
            raise ValueError("Completed job differs from frozen plan")
        return attempt, read(attempt / "result.json")
    return None


def unsealed_state(directory, job):
    existing = attempts(directory, job)
    if not existing:
        return "not_run"
    attempt = existing[-1]
    process = (
        read(attempt / "process.json") if (attempt / "process.json").exists() else {}
    )
    if process.get("watchdog_timeout"):
        return "watchdog_interrupted"
    if (attempt / "adapter_failure.json").exists() or process.get("returncode"):
        return "adapter_failed"
    if (attempt / "interrupted.json").exists():
        return "interrupted"
    return "unsealed_or_running"


def attempt_costs(directory, job):
    values = [
        read(p / "process.json").get("worker_wall_s")
        if (p / "process.json").exists()
        else None
        for p in attempts(directory, job)
    ]
    return {
        "attempt_count": len(values),
        "all_attempts_worker_wall_s": sum(values)
        if all(v is not None for v in values)
        else None,
        "attempts_with_unknown_worker_time": sum(v is None for v in values),
    }


def snapshot(directory, jobs):
    counts = Counter()
    outcomes = Counter()
    timings = []
    for job in jobs:
        selected = selected_result(directory, job)
        if selected:
            attempt, result = selected
            counts[result["status"]] += 1
            outcomes[result["category"]] += 1
            timings.append(
                {
                    "job_id": job["job_id"],
                    "scope": job["scope"],
                    "case": job["case"],
                    "budget": job["budget"],
                    "method": job["method"],
                    "pilot": job["pilot"],
                    "status": result["status"],
                    "search_wall_s": result["recorded_search_wall_s"],
                    "worker_wall_s": read(attempt / "process.json").get("worker_wall_s")
                    if (attempt / "process.json").exists()
                    else None,
                    **attempt_costs(directory, job),
                }
            )
        else:
            counts[unsealed_state(directory, job)] += 1
    report = {
        "planned": len(jobs),
        "status_counts": dict(counts),
        "completed_outcome_counts": dict(outcomes),
        "run_times": timings,
        "success_denominator": "10 seeds per completed condition; not-run/interrupted shown separately",
    }
    # Extrapolate only measured pilot strata; provide min/max scenarios, not confidence bounds.
    estimates = {}
    for label, subset in [
        ("all", jobs),
        ("priority", [j for j in jobs if j["priority"]]),
    ]:
        total_low = total_high = 0.0
        uncovered = []
        for scope, method in sorted({(j["scope"], j["method"]) for j in subset}):
            measured = [
                r["worker_wall_s"]
                for r in timings
                if r["pilot"]
                and r["scope"] == scope
                and r["method"] == method
                and r["status"] in ("completed", "budget_completed", "execution_failed")
                and r["worker_wall_s"] is not None
            ]
            count = sum(j["scope"] == scope and j["method"] == method for j in subset)
            if not measured:
                uncovered.append([scope, method, count])
            else:
                total_low += count * min(measured)
                total_high += count * max(measured)
        estimates[label] = {
            "serial_min_scenario_s": total_low if not uncovered else None,
            "serial_max_scenario_s": total_high if not uncovered else None,
            "uncovered_strata": uncovered,
            "warning": "Small fixed pilot; observed range extrapolation is not a bound or confidence interval; job times may vary widely.",
            "estimate_scope": "Sum of worker process wall times, including startup; controller/preflight/status/export overhead is additional.",
        }
    report["pilot_extrapolation"] = estimates
    return report


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def launch(root, directory, job, config, lock_fd):
    attempt = directory / "jobs" / job["job_id"] / f"attempt_{time.time_ns()}"
    attempt.mkdir(parents=True)
    save(attempt / "job.json", job)
    command = python_command(config, job["scope"]) + [
        "-m",
        "review_comparison.runner",
        "_worker",
        "--root",
        str(root),
        "--run-dir",
        str(directory),
        "--attempt",
        str(attempt),
    ]
    start = time.perf_counter()
    interrupted = False
    with (attempt / "run.log").open("w") as logfile:
        process = subprocess.Popen(
            command,
            cwd=attempt,
            env=worker_environment(root),
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(lock_fd,),
        )
        save(
            attempt / "process.json",
            {
                "pid": process.pid,
                "command": command,
                "hard_seconds": job["hard_seconds"],
            },
        )
        try:
            process.wait(timeout=job["hard_seconds"] or None)
        except subprocess.TimeoutExpired:
            interrupted = True
            stop(process)
        except BaseException:
            stop(process)
            save(
                attempt / "interrupted.json",
                {
                    "reason": "controller interrupted",
                    "worker_wall_s": time.perf_counter() - start,
                },
            )
            raise
    wall = time.perf_counter() - start
    save(
        attempt / "process.json",
        {
            "pid": process.pid,
            "command": command,
            "hard_seconds": job["hard_seconds"],
            "returncode": process.returncode,
            "watchdog_timeout": interrupted,
            "worker_wall_s": wall,
        },
    )
    if interrupted or process.returncode or not (attempt / "seal.json").exists():
        save(
            attempt / "interrupted.json",
            {
                "reason": "watchdog" if interrupted else "worker/adapter error",
                "returncode": process.returncode,
                "worker_wall_s": wall,
            },
        )
    return attempt


def preflight(root, selected, config, directory):
    if config["cpu"] is None:
        raise ValueError(
            "Select an idle CPU explicitly with --cpu after inspecting ps/topology"
        )
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "input_check.json", check_inputs(root))
    # Read-only activity inventory; does not kill or reassign any other process.
    activity = subprocess.run(
        ["ps", "-eo", "pid,ppid,psr,pcpu,comm,args"], capture_output=True, text=True
    )
    (directory / "process_inventory.txt").write_text(activity.stdout + activity.stderr)
    for scope in sorted({j["scope"] for j in selected}):
        candidates = [j for j in selected if j["scope"] == scope]
        job = next(
            (j for j in candidates if j["method"] == "rbfopt_msrsm_genetic"),
            candidates[0],
        )
        probe = directory / f"{scope}_probe.json"
        save(probe, job)
        command = python_command(config, scope) + [
            "-m",
            "review_comparison.runner",
            "_probe",
            "--root",
            str(root),
            "--attempt",
            str(probe),
            "--config",
            str(directory / "config.json"),
        ]
        save(directory / "config.json", config)
        result = subprocess.run(
            command,
            env=worker_environment(root),
            cwd=root,
            capture_output=True,
            text=True,
        )
        (directory / f"{scope}_probe.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise ValueError(
                f"{scope} preflight failed; see {directory}/{scope}_probe.log"
            )
        print(f"PREFLIGHT {scope}: passed (no solver trial)", flush=True)


def pack(root, directory, jobs):
    with locked(directory):
        save(directory / "progress.json", snapshot(directory, jobs))
        # Self-contained return ZIP, including exact executed package sources and inputs.
        path = directory.with_name(directory.name + f"_return_{time.time_ns()}.zip")
        with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(directory.rglob("*")):
                if p.is_file():
                    z.write(
                        p, directory.name + "/" + p.relative_to(directory).as_posix()
                    )
            for name in [
                *read(root / "inventory.json")["files_sha256"],
                "inventory.json",
            ]:
                z.write(root / name, directory.name + "/reproduction/" + name)
        Path(str(path) + ".sha256").write_text(f"{sha(path)}  {path.name}\n")
        print("RESULT_ZIP=" + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=[
            "plan",
            "check",
            "pilot",
            "run",
            "resume",
            "status",
            "summarize",
            "pack",
            "_worker",
            "_probe",
        ],
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--attempt", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--scope", choices=["all", "grid", "process", "priority"], default="all"
    )
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--budgets", type=int, nargs="+")
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--ack-idle-cpu", action="store_true")
    parser.add_argument("--controller-seconds", type=float, default=0)
    parser.add_argument("--retry-interrupted", action="store_true")
    base = "/local/scratch/a/lee4382/repository/RBFopt_Test"
    parser.add_argument(
        "--grid-python", default=base + "/.venv-dantzig-grid-trace/bin/python"
    )
    parser.add_argument(
        "--process-python", default=base + "/.venv-dantzig-nlp-overnight/bin/python"
    )
    parser.add_argument(
        "--conda", default="/local/scratch/a/lee4382/miniconda3/bin/conda"
    )
    parser.add_argument("--bonmin", default=base + "/.venv-dantzig/bin/bonmin")
    parser.add_argument("--ipopt", default=base + "/.venv-dantzig/bin/ipopt")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "_probe":
        from .worker import runtime

        print(json.dumps(runtime(read(args.attempt), read(args.config)), indent=2))
        return
    if args.mode == "_worker":
        from .worker import run

        if verify(root) != read(args.run_dir / "run.json")["package_identity"]:
            raise ValueError("Worker package changed since preflight")
        job = read(args.attempt / "job.json")
        with locked(args.attempt.parent):
            run(root, job, read(args.run_dir / "run.json")["config"], args.attempt)
        return
    identity = verify(root)
    jobs = read(root / "plan.json")
    selected = choose(jobs, args, args.mode == "pilot")
    if not selected:
        raise ValueError("Empty selection")
    if args.mode == "plan":
        print(
            json.dumps(
                {
                    "selection_count": len(selected),
                    "counts": dict(Counter((j["method"]) for j in selected)),
                    "pilot_job_ids": [j["job_id"] for j in selected if j["pilot"]],
                    "planned_settings": "plan.json, reference_settings; only global_search_method changes",
                },
                indent=2,
            )
        )
        return
    if not args.run_dir:
        parser.error("--run-dir required (use a new directory for a new experiment)")
    directory = args.run_dir.resolve()
    if directory == root or root in directory.parents:
        raise ValueError("Store results outside the immutable package directory")
    if (directory / "run.json").exists() and read(directory / "run.json")[
        "package_identity"
    ] != identity:
        raise ValueError(
            "Run belongs to different source/input package; use its original package"
        )
    config = {
        k: getattr(args, k)
        for k in ("cpu", "grid_python", "process_python", "conda", "bonmin", "ipopt")
    }
    if args.mode == "check":
        preflight(root, selected, config, directory / f"preflight_{time.time_ns()}")
        return
    if args.mode in ("pilot", "run", "resume"):
        if not args.ack_idle_cpu:
            raise ValueError(
                "Inspect process inventory/CPU availability, then pass --ack-idle-cpu; affinity is not reservation"
            )
        directory.mkdir(parents=True, exist_ok=True)
        with locked(directory) as lock_fd:
            manifest = directory / "run.json"
            if manifest.exists():
                saved = read(manifest)
                if saved["package_identity"] != identity or saved["config"] != config:
                    raise ValueError(
                        "Resume input/source/settings/environment route changed"
                    )
            else:
                if args.mode == "resume":
                    raise ValueError("No existing run to resume")
                save(
                    manifest,
                    {
                        "package_identity": identity,
                        "config": config,
                        "concurrency": 1,
                        "created_ns": time.time_ns(),
                        "attempt_selection": "First sealed outcome; failed outcomes never retried; explicit retry only unsealed interrupted attempts; all attempts preserved",
                    },
                )
            if args.mode != "pilot":
                pilots = [j for j in choose(jobs, args) if j["pilot"]]
                if not pilots or any(not attempts(directory, j) for j in pilots):
                    raise ValueError(
                        "Run the fixed selected pilot first and inspect status estimates before the full batch"
                    )
            preflight(root, selected, config, directory / f"preflight_{time.time_ns()}")
            started = time.perf_counter()
            for job in selected:
                if selected_result(directory, job):
                    continue
                if attempts(directory, job) and not args.retry_interrupted:
                    continue
                if (
                    args.controller_seconds
                    and time.perf_counter() - started >= args.controller_seconds
                ):
                    print(
                        "Controller time allowance reached at job boundary; no optimizer limit changed",
                        flush=True,
                    )
                    break
                print("START " + job["job_id"], flush=True)
                attempt = launch(root, directory, job, config, lock_fd)
                result = (
                    read(attempt / "result.json")
                    if (attempt / "seal.json").exists()
                    else {"status": "interrupted_or_adapter_failed"}
                )
                print("END " + job["job_id"] + ": " + result["status"], flush=True)
                save(
                    directory / "latest_job.json",
                    {
                        "job_id": job["job_id"],
                        "status": result["status"],
                        "attempt": str(attempt.relative_to(directory)),
                        "note": "Use status for a current full inventory; no repeated full-artifact scan during search.",
                    },
                )
            save(directory / "progress.json", snapshot(directory, jobs))
        print("RESULT_DIR=" + str(directory))
    elif args.mode == "status":
        print(json.dumps(snapshot(directory, jobs), indent=2))
    elif args.mode == "pack":
        pack(root, directory, jobs)
    elif args.mode == "summarize":
        from .analysis import summarize

        directory.mkdir(parents=True, exist_ok=True)
        with locked(directory):
            print(summarize(root, directory, jobs))


if __name__ == "__main__":
    main()
