"""Measure only the 96 missing logical-rejection points, one CPU/thread."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile

from overnight_benchmark.common import THREADS, now, read, save, sha

ROOT = Path(__file__).resolve().parent
PLAN = "benchmark_protocols/fmqa_qhd_missing_points.json"


def plan():
    rows = read(ROOT / PLAN)["points"]
    if len(rows) != 96 or len({r["job_id"] for r in rows}) != 96:
        raise ValueError("Expected exactly 96 distinct missing points")
    for row in rows:
        x, y = row["point"]
        if not ((row["case_name"] == "cstr" and 1 <= x < y <= row["grid_size"])
                or (row["case_name"] == "column" and 1 <= x <= 15 and 1 <= y <= 15 and (x < 8 or y > 8))):
            raise ValueError("This runner accepts only frozen logically infeasible points")
    return rows


def sources():
    files = [ROOT / name for name in ("fmqa_qhd_point_runner.py", "run_fmqa_qhd_points_dantzig.sh", PLAN,
             "docs/fmqa_qhd_points_dantzig.md",
             "cpu_affinity.py", "evaluation_trace.py", "overnight_benchmark/__init__.py",
             "overnight_benchmark/common.py", "overnight_benchmark/worker.py", "requirements-gdp.txt")]
    files += sorted(p for p in (ROOT / "gdp_models").glob("*.py"))
    return files


def valid_record(result, spec):
    record = result["record"]
    if (result["spec"] != spec or result["status"] != "completed"
            or record["case"] != spec["case_name"] or record["point"] != spec["point"]
            or record["cstr_size"] != spec["grid_size"]
            or record["status"] != "preprocessing_infeasible" or record["accepted"]
            or record["solve_wall_s"] != 0 or not 0 < record["total_wall_s"] < math.inf):
        raise ValueError("Expected a measured logical rejection with no solver call")
    return record


def worker(directory, identifier):
    from cpu_affinity import pin_cpu
    from overnight_benchmark.worker import point
    import gdp_models.evaluation as evaluation
    run = read(directory / "run.json")
    pin_cpu(run["cpu"])
    spec = next(r for r in run["plan"] if r["job_id"] == identifier)
    def no_solver(*args, **kwargs):
        raise RuntimeError("Unexpected solver invocation for a logically infeasible point")
    evaluation.optimizer_for = no_solver
    job = directory / "jobs" / identifier
    result = point(spec, {"solver": "gams_ipopt", "initialization": "auto", "nlp_seconds": 60, "gams": None}, job)
    valid_record(result, spec)
    save(job / "result.json", result)
    save(job / "complete.json", {"result_sha256": sha(job / "result.json")})


def completed(directory, spec):
    job = directory / "jobs" / spec["job_id"]
    if not (job / "complete.json").exists():
        return None
    if sha(job / "result.json") != read(job / "complete.json")["result_sha256"]:
        raise ValueError("Point result seal mismatch")
    return valid_record(read(job / "result.json"), spec)


def pack(directory):
    run = read(directory / "run.json")
    records = [r for s in run["plan"] if (r := completed(directory, s)) is not None]
    summary = {"planned_points": len(run["plan"]), "completed_points": len(records),
               "all_completed": len(records) == len(run["plan"]), "solver_calls": 0,
               "sum_point_evaluation_s": math.fsum(r["total_wall_s"] for r in records), "updated_utc": now()}
    save(directory / "summary.json", summary)
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    inventory = "".join(f"{sha(p)}  {p.relative_to(directory).as_posix()}\n" for p in files)
    archive = directory.with_suffix(".zip")
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, directory.name + "/" + p.relative_to(directory).as_posix())
        z.writestr(directory.name + "/SHA256SUMS", inventory)
    temporary.replace(archive)
    print(json.dumps(summary), flush=True)
    print(f"RESULT_ZIP={archive}", flush=True)


def execute(directory):
    import fcntl
    with (directory / ".coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _execute_locked(directory)


def _execute_locked(directory):
    run = read(directory / "run.json")
    if run["source_sha256"] != {p.relative_to(ROOT).as_posix(): sha(p) for p in sources()}:
        raise ValueError("Point runner sources changed")
    from cpu_affinity import pin_cpu
    pin_cpu(run["cpu"])
    try:
        for i, spec in enumerate(run["plan"], 1):
            if completed(directory, spec) is not None:
                continue
            job = directory / "jobs" / spec["job_id"]
            job.mkdir(parents=True, exist_ok=True)
            print(f"[{i}/{len(run['plan'])}] {spec['job_id']}", flush=True)
            with (job / "run.log").open("a") as log:
                proc = subprocess.run([sys.executable, str(ROOT / "fmqa_qhd_point_runner.py"), "_worker",
                    "--run-dir", str(directory), "--job-id", spec["job_id"]], stdout=log, stderr=subprocess.STDOUT,
                    timeout=180, check=False)
            if proc.returncode or completed(directory, spec) is None:
                raise RuntimeError(f"Point failed; inspect {job / 'run.log'}. Completed records can be resumed.")
            print(f"  preprocessing_infeasible; {completed(directory, spec)['total_wall_s']:.6f}s", flush=True)
    finally:
        pack(directory)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("plan", "check", "run", "resume", "pack", "bundle", "_worker"))
    p.add_argument("--run-dir", type=Path)
    p.add_argument("--output-root", type=Path, default=ROOT / "results/fmqa_qhd_points")
    p.add_argument("--output", type=Path)
    p.add_argument("--job-id")
    p.add_argument("--cpu", type=int, default=6)
    p.add_argument("--allow-other-host", action="store_true", help="Development only; publication rejects this host")
    args = p.parse_args(argv)
    os.environ.update(THREADS)
    os.environ.update(OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE", PYTHONPATH=str(ROOT))
    if args.mode == "plan":
        print(json.dumps(plan(), indent=2))
        return
    if args.mode == "bundle":
        if args.output is None:
            p.error("bundle requires --output")
        with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as z:
            for path in sources():
                z.write(path, "fmqa_qhd_points_runner/" + path.relative_to(ROOT).as_posix())
            z.writestr("fmqa_qhd_points_runner/RUNNER_SHA256SUMS", "".join(
                f"{sha(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in sources()))
        args.output.with_suffix(".zip.sha256").write_text(f"{sha(args.output)}  {args.output.name}\n")
        return
    if args.mode == "_worker":
        worker(args.run_dir.resolve(), args.job_id)
        return
    if args.mode == "pack":
        pack(args.run_dir.resolve())
        return
    if not platform.node().startswith("dantzig") and not args.allow_other_host:
        p.error("Run measurements on Dantzig")
    from cpu_affinity import affinity_record, pin_cpu
    from gdp_models.preflight import dependency_versions, model_check
    from gdp_models._sources import provenance
    cpu = pin_cpu(args.cpu)
    versions = dependency_versions()
    if versions["pyomo"] != "6.10.0":
        raise ValueError("Use the original .venv-dantzig-nlp-overnight environment (Pyomo 6.10.0)")
    if args.mode == "resume":
        old = read(args.run_dir / "run.json")
        if (old["host"] != platform.node() or old["versions"] != versions or old["plan"] != plan()
                or provenance("dsda-gdp", old["upstream"]["files_sha256"]) != old["upstream"]):
            raise ValueError("Resume runtime/plan mismatch")
        execute(args.run_dir.resolve())
        return
    for case, size in sorted({(s["case_name"], s["grid_size"] or 5) for s in plan()}):
        model_check(case, size, "auto")
    from gdp_models.models import MODELS, initialization_info
    upstream_files = set()
    for spec in plan():
        _, relative, _ = MODELS[spec["case_name"]]
        _, initial_files = initialization_info(spec["case_name"], spec["grid_size"] or 5, "auto")
        upstream_files.update([relative, *initial_files, "gdp/dsda/dsda_functions.py", f"main_{spec['case_name']}.py"])
    upstream = provenance("dsda-gdp", sorted(upstream_files))
    if args.mode == "check":
        print(json.dumps({"points": len(plan()), "versions": versions, "status": "passed"}))
        return
    args.output_root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="fmqa_qhd_points_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_"), dir=args.output_root)).resolve()
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources()}
    save(directory / "run.json", {"kind": "fmqa_qhd_logical_rejection_points_v1", "created_utc": now(),
        "host": platform.node(), "platform": platform.platform(), "versions": versions,
        "cpu": cpu, "affinity": affinity_record(cpu), "thread_environment": {k: os.environ.get(k) for k in THREADS},
        "plan": plan(), "source_sha256": hashes,
        "upstream": upstream,
        "timing_scope": "Original evaluate_point total_wall_s; fresh preparation and logical rejection; model_check outside timer"})
    for path in sources():
        destination = directory / "source" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    print(f"RUN_DIR={directory}", flush=True)
    execute(directory)


if __name__ == "__main__":
    main()
