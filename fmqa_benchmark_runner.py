"""Dantzig FMQA-SA: original process/grid conditions and three-point designs."""

import argparse
from datetime import datetime, timezone
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
from time import monotonic
import zipfile

from cpu_affinity import affinity_record, pin_cpu


ROOT = Path(__file__).resolve().parent
THREAD_ENV = {k: "1" for k in ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS",
              "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")}
KIND = "fmqa_sa_process_benchmark_v1"
GRID_KIND = "fmqa_sa_grid_benchmark_v1"


def result_filename(run):
    return "benchmark.csv" if run.get("dataset") == "grid" else "process_case_studies.csv"


def environment():
    os.environ.update(THREAD_ENV, OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE", MPLBACKEND="Agg")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    from evaluation_trace import safe_json
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(safe_json(obj), f, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def source_files():
    paths = [ROOT / n for n in ("fmqa_benchmark_runner.py", "fmqa_grid_benchmark.py", "fmqa_compare.py", "cpu_affinity.py", "requirements-fmqa.txt",
             "instrumentation.py", "evaluation_trace.py", "benchmark_analysis.py", "case_study_analysis.py",
             "timing_analysis.py", "grid_dsda.py", "docs/fmqa_benchmark.md", "docs/fmqa_grids.md", "docs/dantzig_cpu_rerun.md", "LICENSE")]
    for directory in ("fmqa_benchmark", "case_study_data", "benchmark_grids"):
        paths.extend(p for p in (ROOT / directory).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc")
    paths.extend(ROOT / "case_studies" / n for n in (
        "__init__.py", "column_case.py", "cstr_case.py", "small_batch_case.py", "dynamic_case.py"))
    for name in ("run_fmqa_dantzig.sh", "run_fmqa_grid_dantzig.sh"):
        shell = ROOT / name
        if shell.exists():
            paths.append(shell)
    return sorted(set(paths))


def versions():
    names = ("numpy", "dimod", "dwave-samplers", "scipy", "pandas", "matplotlib")
    return {name: importlib.metadata.version(name) for name in names}


def preflight(dataset="case"):
    from fmqa_benchmark.protocol import verify_lookup_sources
    from fmqa_benchmark.surrogate import train
    from dwave.samplers import SimulatedAnnealingSampler
    from fmqa_benchmark.protocol import REFERENCE
    meta = json.loads((ROOT / "fmqa_benchmark/vendor/provenance.json").read_text())
    for name, source in meta.items():
        for relative, digest in source["files_sha256"].items():
            if sha(ROOT / "fmqa_benchmark/vendor" / name / relative) != digest:
                raise ValueError("Vendored upstream source checksum mismatch")
    if dataset == "grid":
        from fmqa_benchmark.grid_protocol import verify_grid_sources
        data_hashes = verify_grid_sources()
    else:
        data_hashes = verify_lookup_sources()
    for name in ("original", "bam5"):
        m = json.loads((REFERENCE / f"{name}.manifest.json").read_text())
        if sha(REFERENCE / f"{name}.csv") != m["output"]["csv_sha256"]:
            raise ValueError("Archived reference result checksum mismatch")
    bqm = train(["00", "01", "11"], [1, .5, 0], seed=0, epochs=5, learning_rate=.01)
    first = SimulatedAnnealingSampler().sample(bqm, num_reads=3, num_sweeps=20, seed=42)
    second = SimulatedAnnealingSampler().sample(bqm, num_reads=3, num_sweeps=20, seed=42)
    if not (first.record.sample == second.record.sample).all():
        raise RuntimeError("Seeded SA smoke test was not reproducible")
    return {"python": sys.version, "packages": versions(), "platform": platform.platform(),
            "host": platform.node(), "machine": platform.machine(), "upstream": meta,
            "lookup_data_sha256": data_hashes, "thread_environment": THREAD_ENV,
            "sampler": "dwave.samplers.SimulatedAnnealingSampler (local CPU)",
            "surrogate": "NumPy CPU port of pinned TsudaLab rank-8 FMBQM; SECQUOIA training function",
            "objective_mode": "lookup, matching original DFO; no GDP/NLP solve or cached NLP time added"}


def result_record(spec, state):
    import math
    from instrumentation import make_result_record
    from fmqa_benchmark.protocol import METHOD, problem
    target = problem(spec)["target"]
    return make_result_record(
        spec["csv_name"], METHOD, spec["seed"], spec["n_starts"], spec["max_evaluations"],
        state["best_value"], state["best_point"], state["total_evals"], state["wall_time_s"],
        state.get("has_feasible_solution", False) and math.isclose(state["best_value"], target, rel_tol=0, abs_tol=1e-12),
        state["incumbent_trajectory"], initial_evals=state["initial_evals"],
        adaptive_evals=state["adaptive_evals"], unique_evals=state["unique_evals"],
        solver_evalcount=state["adaptive_evals"], solver_iterations=state["adaptive_evals"],
        solver_status=state["status"], solver_message="FMQA with CPU simulated annealing; lookup objective")


def worker(directory, identifier):
    from fmqa_benchmark.optimizer import optimize
    from fmqa_benchmark.protocol import problem
    run = json.loads((directory / "run.json").read_text())
    spec = next(s for s in run["plan"] if s["job_id"] == identifier)
    job = directory / "jobs" / identifier
    oracle = problem(spec)
    with (job / "evaluations.jsonl").open("w", buffering=1) as events, (job / "proposals.jsonl").open("w", buffering=1) as proposals:
        def evaluated(event, state):
            events.write(json.dumps(event, allow_nan=False) + "\n")
            events.flush()
            save(job / "result.json", {"spec": spec, **state})

        def proposed(event):
            proposals.write(json.dumps(event, allow_nan=False) + "\n")
            proposals.flush()

        state = optimize(oracle["objective"], oracle["lower"], oracle["upper"],
                         spec["starting_points"], spec["max_evaluations"], spec["seed"], run["config"],
                         on_evaluation=evaluated, on_proposal=proposed)
    save(job / "result.json", {"spec": spec, **state})


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


def launch(directory, spec, config):
    job = directory / "jobs" / spec["job_id"]
    if job.exists():
        old = directory / "previous_attempts"
        old.mkdir(exist_ok=True)
        job.rename(old / (job.name + "_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")))
    job.mkdir(parents=True)
    started = monotonic()
    outcome = None
    with (job / "run.log").open("w") as log:
        process = subprocess.Popen([sys.executable, str(ROOT / "fmqa_benchmark_runner.py"), "worker",
                                    "--run-dir", str(directory), "--job-id", spec["job_id"]],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=config["time_limit"])
        except subprocess.TimeoutExpired:
            outcome = "hard_time_limit"
            stop(process)
        except BaseException:
            stop(process)
            raise
    path = job / "result.json"
    result = json.loads(path.read_text()) if path.exists() else {"spec": spec, "total_evals": 0}
    if outcome:
        result["status"] = outcome
        result["wall_time_s"] = max(result.get("wall_time_s", 0), monotonic() - started)
    elif process.returncode != 0:
        result["status"] = "error"
    result.update(worker_wall_s=monotonic() - started, worker_pid=process.pid, worker_returncode=process.returncode)
    save(path, result)
    return result


def validate_job(job, spec):
    import math
    from fmqa_benchmark.protocol import point_hash, problem
    from fmqa_benchmark.optimizer import BinaryCoordinates, PENALTY
    result = json.loads((job / "result.json").read_text())
    if result["spec"] != spec:
        raise ValueError("Saved FMQA job belongs to a different run")
    events = [json.loads(line) for line in (job / "evaluations.jsonl").read_text().splitlines()]
    if result.get("status") not in {"completed", "time_limit", "hard_time_limit"}:
        raise ValueError("Job has not returned a usable terminal outcome")
    if not spec["n_starts"] <= len(events) <= spec["max_evaluations"]:
        raise ValueError("Invalid objective callback count")
    if result["status"] == "completed" and len(events) != spec["max_evaluations"]:
        raise ValueError("Completed FMQA run did not consume its evaluation budget")
    initial = [e["point"] for e in events[:spec["n_starts"]]]
    if point_hash(initial) != spec["initial_design_sha256"]:
        raise ValueError("Initial coordinates differ from the original Dantzig design")
    if (result["total_evals"] != len(events) or
            result["incumbent_trajectory"] != [e["incumbent"] for e in events] or
            [e["evaluation_index"] for e in events] != list(range(1, len(events) + 1))):
        raise ValueError("Objective trace differs from the saved result")
    if len({tuple(e["point"]) for e in events}) != len(events):
        raise ValueError("Unexpected repeated objective evaluations")
    oracle = problem(spec)
    encoding = BinaryCoordinates(oracle["lower"], oracle["upper"])
    best, best_point, feasible = PENALTY, None, False
    for index, event in enumerate(events):
        point = event["point"]
        if not encoding.valid(point):
            raise ValueError("Evaluated point is outside the original integer bounds")
        raw = oracle["objective"](point)
        finite = math.isfinite(raw)
        # Identical CSV bytes can parse a couple of ULPs apart across platforms.
        # Keep the server's recorded values/trajectory; tolerate only floating
        # representation noise against the independently loaded objective table.
        recorded = event["raw_value"]
        equivalent = (recorded is None if not finite else
                      isinstance(recorded, (int, float)) and math.isfinite(recorded)
                      and abs(recorded - raw) <= 4 * max(math.ulp(recorded), math.ulp(raw)))
        value = recorded if finite else PENALTY
        if (not equivalent or event["value"] != value
                or event["lookup_feasible"] != finite
                or event["phase"] != ("initial" if index < spec["n_starts"] else "adaptive")):
            raise ValueError("Evaluation trace does not match the original objective table")
        if best_point is None or value < best:
            best, best_point = value, point
        feasible = feasible or finite
        if event["incumbent"] != best:
            raise ValueError("Incorrect recorded incumbent")
    if (result["best_value"] != best or result["best_point"] != best_point
            or result["has_feasible_solution"] != feasible
            or result["initial_evals"] != spec["n_starts"]
            or result["adaptive_evals"] != len(events) - spec["n_starts"]
            or result["unique_evals"] != len(events)):
        raise ValueError("Incorrect final objective or evaluation counts")
    for field in ("wall_time_s", "training_wall_s", "annealing_wall_s", "objective_wall_s"):
        if not math.isfinite(result[field]) or result[field] < 0:
            raise ValueError("Invalid recorded time")
    return result


def summarize(directory):
    from instrumentation import RESULT_FIELDS, save_results_csv
    run = json.loads((directory / "run.json").read_text())
    records, outcomes, missing = [], [], []
    for spec in run["plan"]:
        job = directory / "jobs" / spec["job_id"]
        try:
            result = validate_job(job, spec)
        except (OSError, ValueError, KeyError) as error:
            missing.append({"job_id": spec["job_id"], "reason": str(error)})
            continue
        records.append(result_record(spec, result))
        outcomes.append(result)
    summary = {"planned_runs": len(run["plan"]), "recorded_runs": len(records),
               "complete": not missing, "missing_or_invalid": missing, "outcomes": outcomes}
    save(directory / "summary.json", summary)
    csv_path = directory / result_filename(run)
    save_results_csv(records, csv_path)
    manifest = {"schema": {"name": "unified_benchmark_result", "fields": list(RESULT_FIELDS),
                           "structured_value_encoding": "JSON strings in CSV cells"},
                "run": {"status": "completed" if not missing else "incomplete",
                        "expected_rows": len(run["plan"]), "completed_rows": len(records)},
                "output": {"csv_bytes": csv_path.stat().st_size, "csv_sha256": sha(csv_path)},
                "fmqa_protocol": run,
                "artifacts_sha256": {p.relative_to(directory).as_posix(): sha(p)
                                     for p in sorted((directory / "jobs").rglob("*")) if p.is_file()}}
    save(csv_path.with_suffix(".manifest.json"), manifest)
    return summary


def pack(directory):
    directory = Path(directory).resolve()
    if json.loads((directory / "run.json").read_text())["kind"] not in {KIND, GRID_KIND}:
        raise ValueError("Not an FMQA benchmark directory")
    summary = summarize(directory)
    files = sorted(p for p in directory.rglob("*") if p.is_file() and not p.is_symlink()
                   and p.name != "SHA256SUMS" and not p.name.endswith(".tmp"))
    sums = directory / "SHA256SUMS"
    sums.write_text("".join(f"{sha(p)}  {p.relative_to(directory).as_posix()}\n" for p in files))
    output = directory.with_suffix(".zip")
    tmp = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in [*files, sums]:
            z.write(p, directory.name + "/" + p.relative_to(directory).as_posix())
    with zipfile.ZipFile(tmp) as z:
        if z.testzip():
            raise ValueError("Corrupt FMQA result ZIP")
    tmp.replace(output)
    output.with_suffix(".zip.sha256").write_text(f"{sha(output)}  {output.name}\n")
    print(f"RESULT_ZIP={output}", flush=True)
    return summary


def bundle(output, dataset="case"):
    files = source_files()
    package_root = "fmqa_grid_runner" if dataset == "grid" else "fmqa_runner"
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, package_root + "/" + p.relative_to(ROOT).as_posix())
        z.writestr(package_root + "/RUNNER_SHA256SUMS", "".join(
            f"{sha(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in files))
    print(f"RUNNER_ZIP={output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "check", "run", "worker", "pack", "bundle"))
    parser.add_argument("--dataset", choices=("case", "grid"), default="case")
    parser.add_argument("--grids", help="Optional comma-separated grid names, e.g. ackley,alpine1")
    parser.add_argument("--grid-budgets", default="10,30,50,70,100")
    parser.add_argument("--cases", default="column,cstr,small_batch,dynamic")
    parser.add_argument("--cstr-sizes", default="5,10,15,20,25,30")
    parser.add_argument("--seeds", help="Optional comma-separated subset of original seeds")
    parser.add_argument("--epochs", type=int, default=1000)
    parser.add_argument("--learning-rate", type=float, default=.01)
    parser.add_argument("--num-reads", type=int, default=100)
    parser.add_argument("--num-sweeps", type=int, default=1000)
    parser.add_argument("--time-limit", type=int, default=1800, help="Safety wall limit per run; evaluation budgets match original")
    parser.add_argument("--cpu", type=int, help="Linux logical CPU ID; default: first allowed CPU")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--job-id")
    args = parser.parse_args()
    environment()
    from fmqa_benchmark.protocol import CASES, CSTR_SIZES, reference_plan
    try:
        if args.mode == "bundle":
            if args.output is None:
                parser.error("bundle requires --output")
            bundle(args.output, args.dataset)
            return 0
        if args.mode == "pack":
            if args.run_dir is None:
                parser.error("pack requires --run-dir")
            pack(args.run_dir)
            return 0
        if args.mode == "worker":
            worker(args.run_dir.resolve(), args.job_id)
            return 0
        cases = args.cases.split(",")
        sizes = [int(x) for x in args.cstr_sizes.split(",")]
        seeds = [int(x) for x in args.seeds.split(",")] if args.seeds else None
        if (not set(cases) <= set(CASES) or len(set(cases)) != len(cases)
                or not set(sizes) <= set(CSTR_SIZES) or len(set(sizes)) != len(sizes)
                or seeds is not None and (not set(seeds) <= set(range(10)) or len(set(seeds)) != len(seeds))):
            parser.error("Select distinct original cases, CSTR sizes and seeds")
        config = {k: getattr(args, k) for k in ("epochs", "learning_rate", "num_reads", "num_sweeps", "time_limit")}
        if any(not math.isfinite(v) or v <= 0 for v in config.values()):
            parser.error("FMQA parameters must be positive")
        if args.dataset == "grid":
            from fmqa_benchmark.grid_protocol import reference_grid_plan
            plan = reference_grid_plan(args.grids.split(",") if args.grids else None, seeds,
                                       [int(x) for x in args.grid_budgets.split(",")])
        else:
            if args.grids or args.grid_budgets != "10,30,50,70,100":
                parser.error("Grid selection requires --dataset grid")
            plan = reference_plan(cases, sizes, seeds)
        kind = GRID_KIND if args.dataset == "grid" else KIND
        if args.mode == "plan":
            print(json.dumps({"runs": len(plan), "config": config, "plan": plan}, indent=2))
            return 0
        cpu = pin_cpu(args.cpu)
        runtime = preflight(args.dataset)
        runtime["cpu_affinity"] = affinity_record(cpu)
        if args.mode == "check":
            print(json.dumps({"preflight": "passed", "runs": len(plan), "runtime": runtime}, indent=2))
            return 0
        hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()}
        if args.resume:
            directory = args.resume.resolve()
            previous = json.loads((directory / "run.json").read_text())
            if (previous["kind"] != kind or previous["plan"] != plan or previous["config"] != config
                    or previous["source_sha256"] != hashes or previous["runtime"] != runtime
                    or previous.get("cpu") != cpu):
                raise ValueError("Resume requires identical plan, options, sources, dependencies, host and CPU")
        else:
            args.output_root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            label = "dantzig_fmqa_grid" if args.dataset == "grid" else "dantzig_fmqa"
            directory = Path(tempfile.mkdtemp(prefix=f"{label}_{stamp}_", dir=args.output_root)).resolve()
            save(directory / "run.json", {"kind": kind, "dataset": args.dataset, "config": config, "plan": plan, "runtime": runtime,
                                         "cpu": cpu, "source_sha256": hashes,
                                         "created_utc": datetime.now(timezone.utc).isoformat()})
            for p in source_files():
                dest = directory / "source" / p.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        print(f"CPU_AFFINITY={json.dumps(runtime['cpu_affinity'])}", flush=True)
        print(f"RESULT_DIR={directory}", flush=True)
        try:
            for i, spec in enumerate(plan, 1):
                try:
                    saved = validate_job(directory / "jobs" / spec["job_id"], spec)
                    if saved["status"] == "completed":
                        print(f"SKIP {spec['job_id']}: completed", flush=True)
                        continue
                except (OSError, ValueError, KeyError):
                    pass
                print(f"START {i}/{len(plan)} {spec['job_id']}", flush=True)
                outcome = launch(directory, spec, config)
                # Full trace audits/hash inventories are done once when packaging.
                # Re-reading every earlier trace after each of 1,050 jobs is quadratic.
                save(directory / "progress.json", {"last_job_id": spec["job_id"], "position": i,
                                                  "planned_runs": len(plan), "status": outcome["status"]})
                print(f"DONE {spec['job_id']}: {outcome['status']}, evaluations={outcome['total_evals']}", flush=True)
        finally:
            summary = pack(directory)
        print(json.dumps({k: v for k, v in summary.items() if k != "outcomes"}, indent=2))
        return 0 if summary["complete"] else 1
    except KeyboardInterrupt:
        print("Interrupted; saved work is packaged. Resume with the same options.", file=sys.stderr)
        return 130
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
