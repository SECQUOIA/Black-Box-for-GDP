"""Sequential, restartable Dantzig experiments with isolated process groups."""

import argparse
from contextlib import contextmanager
import fcntl
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
import time
import zipfile

from .common import (KIND, METHODS, ROOT, THREADS, jsonl, now, point_spec,
                     read, save, sha, source_files, source_hashes)


def plans():
    from fmqa_benchmark.protocol import reference_plan
    jobs = [{**spec, "method": method, "job_id": spec["job_id"] + "_" + method}
            for spec in reference_plan() for method in METHODS]
    assert len(jobs) == 417
    return jobs


def runtime(config, *, exercise=False, allow_other_host=False):
    from cpu_affinity import affinity_record, pin_cpu
    from fmqa_benchmark.protocol import reference_plan, verify_lookup_sources, problem
    from case_studies.common import generate_lhc_starting_points
    from gdp_models._sources import source_root, provenance
    from gdp_models.models import MODELS, initialization_info
    from gdp_models.preflight import model_check
    from gdp_models.solvers import optimizer_for, solve_gams
    import bam
    import pyomo.environ as pyo
    if platform.node() != "dantzig.ecn.purdue.edu" and not platform.node().startswith("dantzig") and not allow_other_host:
        raise ValueError("Run on Dantzig; this runner does not silently label another host as Dantzig")
    cpu = pin_cpu(config["cpu"])
    required = {"numpy": "2.4.6", "scipy": "1.17.1", "rbfopt": "4.3.0", "bam-solver": "5.0.0",
                "pyomo": "6.10.0"}
    versions = {name: importlib.metadata.version(name) for name in
                (*required, "sympy", "networkx", "pandas", "matplotlib")}
    if any(versions[name] != version for name, version in required.items()):
        raise ValueError(f"Environment differs from pinned protocol; run setup: {versions}")
    for name in ("gams", "bonmin", "ipopt", "bam_license"):
        if not Path(config[name]).is_file():
            raise ValueError(f"Missing {name}: {config[name]}")
    verify_lookup_sources()
    external = {}
    for case, size in [("column", 5), ("small_batch", 5), ("dynamic", 5),
                       *(("cstr", n) for n in (5, 10, 15, 20, 25, 30))]:
        name, model_file, _ = MODELS[case]
        source_root(name)
        _, init_files = initialization_info(case, size, config["initialization"])
        files = [model_file, *init_files]
        if case != "dynamic":
            files += ["gdp/dsda/dsda_functions.py", f"main_{case}.py"]
        external[f"{case}_{size}"] = provenance(name, files)
        if exercise:
            model_check(case, size, config["initialization"])
    for spec in reference_plan():
        oracle = problem(spec)
        generated = generate_lhc_starting_points(len(oracle["lower"]), 3, oracle["lower"], oracle["upper"], spec["seed"])
        if [list(p) for p in generated] != spec["starting_points"]:
            raise ValueError("Pinned environment does not reproduce the original LHC coordinates")
    optimizer = optimizer_for(config["solver"], config["gams"])
    version = list(optimizer.version())
    expected_version = config["gams_version"]
    if expected_version and version[:2] != [int(n) for n in expected_version.split(".")]:
        raise ValueError(f"Expected GAMS {expected_version}, got {version}")
    bam.set_license_file(config["bam_license"])
    if tuple(bam.Bam.get_solver_version()) < (2026, 9, 10):
        raise ValueError("Unexpected BAM native solver version")
    if exercise:
        m = pyo.ConcreteModel()
        m.x = pyo.Var(bounds=(0, 3), initialize=.5)
        m.obj = pyo.Objective(expr=(m.x - 1) ** 2)
        result, stats = solve_gams(optimizer, m, config["solver"], 15,
                                  baron_lp_solver="clp" if config["solver"] == "baron" else None)
        if stats["SOLVESTAT"] != 1 or stats["MODELSTAT"] not in (1, 2) or not len(result.solution):
            raise RuntimeError(f"NLP solver preflight failed: {stats}")
        m.solutions.load_from(result)
        if abs(m.x.value - 1) > 1e-4:
            raise RuntimeError("NLP smoke solve returned the wrong solution")
        # Exercise the existing lookup runners; never substitute a new search algorithm.
        from case_studies.column_rbfopt import run_column_rbfopt
        from case_studies.small_batch_bam import run_small_batch_bam
        run_column_rbfopt(seed=1, max_evaluations=4,
                         minlp_solver_path=config["bonmin"], nlp_solver_path=config["ipopt"])
        run_small_batch_bam(seed=0, max_evaluations=4, bam_license_file=config["bam_license"])
    return {"host": platform.node(), "platform": platform.platform(), "python": platform.python_version(),
            "versions": versions, "affinity": affinity_record(cpu), "external_sources": external,
            "gams_version": version, "gams_sha256": sha(config["gams"]),
            "bonmin_sha256": sha(config["bonmin"]), "ipopt_sha256": sha(config["ipopt"]),
            "bam_license_sha256": sha(config["bam_license"]),
            "bam_native": list(bam.Bam.get_solver_version()), "thread_environment": THREADS}


@contextmanager
def locked(directory):
    path = Path(directory) / ".lock"
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("This run is already active; do not start a duplicate coordinator") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def terminal_valid(job):
    result_path = job / "result.json"
    if not result_path.exists() or not (job / "terminal.json").exists():
        return False
    terminal = read(job / "terminal.json")
    for name, digest in terminal["files_sha256"].items():
        if sha(job / name) != digest:
            raise ValueError(f"Saved job changed: {job / name}")
    return True


def launch(directory, mode, spec, config, *, retry_errors=False):
    job = directory / mode / spec["job_id"]
    if terminal_valid(job):
        old = read(job / "result.json")
        if old["spec"] != spec:
            raise ValueError("Saved job does not match the run plan")
        if not retry_errors or old["status"] not in {"error", "setup_error"}:
            return old
    if job.exists():
        active_path = job / "process.json"
        if active_path.exists():
            active = read(active_path)
            pid = active["pid"]
            # /proc command line ties this PID to this exact worker. Refuse to
            # duplicate an orphan still running after a coordinator failure.
            proc = Path(f"/proc/{pid}/cmdline")
            if proc.exists():
                command = proc.read_bytes().replace(b"\0", b" ").decode(errors="replace")
                if str(directory) in command and spec["job_id"] in command:
                    raise RuntimeError(f"Previous worker PID {pid} is still active: {job}")
        previous = directory / "previous_attempts" / mode
        previous.mkdir(parents=True, exist_ok=True)
        job.rename(previous / f"{job.name}_{time.time_ns()}")
    job.mkdir(parents=True)
    save(job / "spec.json", spec)
    started = time.monotonic()
    status = None
    limit = config["point_hard_seconds"] if mode == "points" else config["run_seconds"]
    with (job / "run.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "overnight_benchmark", "worker", "--run-dir", str(directory),
             "--phase", mode, "--job-id", spec["job_id"]],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT)
        save(job / "process.json", {"pid": process.pid, "started_utc": now()})
        try:
            while True:
                remaining = limit - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(process.args, limit)
                try:
                    process.wait(timeout=min(30, remaining))
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic() - started
                    if elapsed >= limit:
                        raise
                    print(f"  running PID={process.pid} elapsed={elapsed:.0f}s/{limit:g}s", flush=True)
        except subprocess.TimeoutExpired:
            status = "hard_time_limit"
            stop(process)
        except BaseException:
            stop(process)
            raise
    finished = time.monotonic()
    path = job / "result.json"
    result = read(path) if path.exists() else {"spec": spec, "mode": mode, "status": "error"}
    if status:
        result["status"] = status
    elif process.returncode and result.get("status") not in {"error", "setup_error"}:
        result["status"] = "error"
    if (job / "clock.json").exists() and result.get("wall_time_s") is None:
        result["wall_time_s"] = finished - read(job / "clock.json")["started_monotonic_s"]
    active_path = job / "active_evaluation.json"
    if active_path.exists():
        active = read(active_path)
        events = jsonl(job / "evaluations.jsonl")
        # A crash after writing the event but before removing active.json must
        # not charge the same evaluation twice.
        if not events or active.get("evaluation_index", 1) > events[-1]["evaluation_index"]:
            result["interrupted_evaluation"] = active
            result["interrupted_evaluation_wall_s"] = finished - active["started_monotonic_s"]
            result["interrupted_evaluation_note"] = "Observed elapsed cost through process-group termination; censored outcome, not infeasibility"
    result.update(worker_wall_s=finished - started, worker_returncode=process.returncode,
                  completed_utc=now())
    save(path, result)
    files = sorted(p for p in job.rglob("*") if p.is_file() and not p.name.endswith(".tmp")
                   and p.name != "terminal.json")
    save(job / "terminal.json", {"files_sha256": {p.relative_to(job).as_posix(): sha(p) for p in files}})
    return result


def pack(directory, *, live=False):
    """Snapshot result bytes. Live snapshots are explicitly incomplete exports."""
    directory = Path(directory)
    suffix = f"_snapshot_{time.strftime('%Y%m%d_%H%M%S')}" if live else ""
    archive_path = directory.with_name(directory.name + suffix + ".zip")
    temporary = archive_path.with_suffix(".zip.tmp")
    import hashlib
    sums = []
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if (not path.is_file() or path.is_symlink() or path.name in {".lock", "SHA256SUMS"}
                    or path.name.endswith(".tmp") or "matplotlib-cache" in path.parts):
                continue
            relative = path.relative_to(directory).as_posix()
            try:
                content = path.read_bytes()
            except FileNotFoundError:
                if live:
                    continue
                raise
            archive.writestr(directory.name + "/" + relative, content)
            sums.append(f"{hashlib.sha256(content).hexdigest()}  {relative}\n")
        archive.writestr(directory.name + "/SHA256SUMS", "".join(sums))
        if live:
            archive.writestr(directory.name + "/LIVE_SNAPSHOT.txt",
                             "Non-atomic snapshot of an active run. May contain partial final JSONL lines or changing checkpoints. Not a completed benchmark; collect the final archive when finished.\n")
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip():
            raise RuntimeError("Result ZIP CRC check failed")
    temporary.replace(archive_path)
    archive_path.with_suffix(".zip.sha256").write_text(f"{sha(archive_path)}  {archive_path.name}\n")
    print(f"RESULT_ZIP={archive_path}", flush=True)
    return archive_path


def execute(directory, *, retry_errors=False):
    from .analysis import lookup_runs, requested_points, summarize
    from .references import archived_fmqa, historical_costs
    directory = Path(directory)
    with locked(directory):
        run = read(directory / "run.json")
        config = run["config"]
        if source_hashes() != run["source_files_sha256"]:
            raise ValueError("Runner sources changed; use the same ZIP to resume")
        current_runtime = runtime(config, allow_other_host=run.get("development_only", False))
        if current_runtime != run["runtime"]:
            raise ValueError("Runtime/CPU/model identity changed; do not mix runs")
        _, fmqa = archived_fmqa()
        historical, reuse_audit = historical_costs(config, current_runtime)
        save(directory / "historical_reuse.json", reuse_audit)
        def report():
            return summarize(directory, fmqa, historical, reuse_audit)
        def run_phase(phase, plan):
            for i, spec in enumerate(plan, 1):
                save(directory / "progress.json", {"phase": phase, "index": i, "planned": len(plan),
                     "job_id": spec["job_id"], "updated_utc": now(), "coordinator_pid": os.getpid()})
                print(f"[{phase} {i}/{len(plan)}] {spec['job_id']}", flush=True)
                result = launch(directory, phase, spec, config, retry_errors=retry_errors)
                print(f"  {result['status']} {result.get('wall_time_s', result.get('worker_wall_s', 0)):.3f}s", flush=True)
                if result["status"] == "setup_error":
                    raise RuntimeError("Solver/environment setup failed; stopped instead of counting failures as infeasible")
                if i % 10 == 0:
                    report()
            report()
        try:
            run_phase("lookup", run["lookup_plan"])
            traces = lookup_runs(directory, run["lookup_plan"], fmqa)
            keys = requested_points(traces)
            point_plan = [point_spec(k) for k in keys if k not in historical]
            # If Dynamic preparation is absent from the archive, measure one
            # dynamic point even if all its point costs can otherwise be reused.
            if not reuse_audit.get("preparations") and not any(p["case_name"] == "dynamic" for p in point_plan):
                dynamic = next((k for k in keys if k[0] == "dynamic"), None)
                if dynamic:
                    point_plan.append(point_spec(dynamic))
            save(directory / "point_plan.json", point_plan)
            save(directory / "requested_points.json", [point_spec(k) for k in keys])
            run_phase("points", point_plan)
            audit = report()
            save(directory / "complete.json", {"status": "all_jobs_attempted", "completed_utc": now(), **audit})
            save(directory / "progress.json", {"phase": "finished", "updated_utc": now(), **audit})
        finally:
            try:
                report()
            finally:
                pack(directory)


def bundle(path):
    files = source_files()
    metadata = read(ROOT / "overnight_benchmark/reference_archives.json")
    files += [ROOT / item["path"] for item in metadata.values()]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = path.stem
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(set(files)):
            archive.write(item, prefix + "/" + item.relative_to(ROOT).as_posix())
        inventory = "".join(f"{sha(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in sorted(set(files)))
        readme = ROOT / "docs/dfo_trace_nlp_dantzig.md"
        archive.write(readme, prefix + "/README.md")
        inventory += f"{sha(readme)}  README.md\n"
        archive.writestr(prefix + "/SHA256SUMS", inventory)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise RuntimeError("Runner ZIP CRC validation failed")
    path.with_suffix(".zip.sha256").write_text(f"{sha(path)}  {path.name}\n")
    print(path)


def main():
    os.environ.update(THREADS, OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE", PYTHONUNBUFFERED="1")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "run", "resume", "status", "pack", "bundle", "worker"))
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/dfo_trace_nlp")
    parser.add_argument("--cpu", type=int, default=6)
    parser.add_argument("--solver", choices=("gams_ipopt", "baron"), default="gams_ipopt")
    parser.add_argument("--initialization", choices=("auto", "default"), default="auto")
    parser.add_argument("--nlp-seconds", type=float, default=60)
    parser.add_argument("--run-seconds", type=float, default=1800)
    parser.add_argument("--gams", default=os.environ.get("GAMS_BIN", "/package/gams/52.2/gams"))
    parser.add_argument("--gams-version", default="52.2")
    parser.add_argument("--coin-bin", default=os.environ.get("COIN_BIN", ""))
    parser.add_argument("--bam-license", default=os.environ.get("BAM_LICENSE_FILE", ""))
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--live", action="store_true", help="Pack a labelled incomplete snapshot while running")
    parser.add_argument("--phase", choices=("lookup", "points"))
    parser.add_argument("--job-id")
    parser.add_argument("--allow-other-host", action="store_true", help="Development only; output explicitly marked non-Dantzig")
    args = parser.parse_args()
    if args.mode == "worker":
        from .worker import main as worker_main
        sys.exit(worker_main(args.run_dir, args.phase, args.job_id))
    if args.mode == "bundle":
        if args.output is None:
            parser.error("bundle requires --output")
        return bundle(args.output)
    if args.mode in {"resume", "status", "pack"}:
        if args.run_dir is None:
            parser.error(f"{args.mode} requires --run-dir")
        if read(args.run_dir / "run.json")["kind"] != KIND:
            raise ValueError("Not an overnight benchmark result directory")
        if args.mode == "resume":
            return execute(args.run_dir.resolve(), retry_errors=args.retry_errors)
        if args.mode == "status":
            print(json.dumps(read(args.run_dir / "progress.json"), indent=2))
            return
        if args.live:
            return pack(args.run_dir, live=True)
        with locked(args.run_dir):
            return pack(args.run_dir)
    if any(not math.isfinite(v) or v <= 0 for v in (args.nlp_seconds, args.run_seconds)):
        parser.error("Time limits must be finite and positive")
    from .references import archived_fmqa, historical_costs
    _, fmqa = archived_fmqa()
    config = {"solver": args.solver, "initialization": args.initialization,
              "nlp_seconds": args.nlp_seconds, "run_seconds": args.run_seconds,
              "point_hard_seconds": args.nlp_seconds + 120, "cpu": args.cpu,
              "gams": str(Path(args.gams).resolve()), "gams_version": args.gams_version,
              "bonmin": str((Path(args.coin_bin) / "bonmin").resolve()),
              "ipopt": str((Path(args.coin_bin) / "ipopt").resolve()),
              "bam_license": str(Path(args.bam_license).resolve())}
    if args.allow_other_host and not hasattr(os, "sched_getaffinity"):
        config["cpu"] = None
    identity = runtime(config, exercise=True, allow_other_host=args.allow_other_host)
    lookup = plans()
    historical, reuse_audit = historical_costs(config, identity)
    print(f"PRECHECK PASSED: original DFO lookup runs={len(lookup)}, archived FMQA traces={len(fmqa)}, reusable historical points={len(historical)}", flush=True)
    if args.mode == "check":
        print(json.dumps({"config": config, "runtime": identity, "reuse": reuse_audit}, indent=2))
        return
    import tempfile
    args.output_root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=time.strftime("dantzig_dfo_trace_nlp_%Y%m%d_%H%M%S_"),
                                     dir=args.output_root)).resolve()
    save(directory / "run.json", {"kind": KIND, "created_utc": now(), "config": config,
         "runtime": identity, "source_files_sha256": source_hashes(), "lookup_plan": lookup,
         "development_only": args.allow_other_host,
         "evaluation_policy": "Run the original DFO lookup implementation unchanged; measure NLP cost separately at visited coordinates only",
         "point_policy": "Verified historical original attempts reused; missing visited coordinates measured once, including nonaccepted outcomes; values never fed back to DFO"})
    for path in source_files():
        destination = directory / "source" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    print(f"RUN_DIR={directory}", flush=True)
    save(args.output_root / "latest_run.json", {"run_dir": str(directory)})
    execute(directory)


if __name__ == "__main__":
    main()
