"""Run process DFO follow-ups with durable trajectories and isolated workers."""

import argparse
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

from evaluation_trace import EvaluationTrace, finite_value, validate_events
from overnight_benchmark.common import THREADS, append, csv_file, jsonl, now, read, save, sha
from overnight_benchmark.runner import locked, pack, stop, terminal_valid

ROOT = Path(__file__).resolve().parent
KIND = "process_dfo_followup_v1"
FMQA_CONFIG = {"epochs": 1000, "learning_rate": .01, "num_reads": 100,
               "num_sweeps": 1000, "time_limit": 1800}
THREAD_ENV = {**THREADS, "OMP_DYNAMIC": "FALSE", "MKL_DYNAMIC": "FALSE"}
EXPERIMENT = None


def experiment_kind():
    return EXPERIMENT.KIND if EXPERIMENT else KIND


def problem(spec):
    if EXPERIMENT:
        return EXPERIMENT.problem(spec)
    from fmqa_benchmark.protocol import problem as original_problem
    return original_problem(spec)


def plan():
    if EXPERIMENT:
        return EXPERIMENT.plan()
    from fmqa_benchmark.protocol import point_hash, reference_plan
    column = reference_plan(["column"], seeds=[1])[0]
    points = [[10, 3], [13, 6], [8, 9]]
    column.update(seed=10, starting_points=points, initial_design_sha256=point_hash(points))
    jobs = []
    for method in ("dsda", "rbfopt", "bam", "fmqa_sa"):
        settings = {"dsda": {"diagonal": True, "tie_break": "first"},
                    "rbfopt": {"algorithm": "MSRSM", "global_search_method": "solver", "rbf": "auto"},
                    "bam": {}, "fmqa_sa": FMQA_CONFIG}[method]
        jobs.append({**column, "method": method, "settings": dict(settings),
                     "job_id": f"column_B16_seed10_{method}",
                     "purpose": "supplement original Column seeds 1-9 with approved seed 10"})
    for spec in reference_plan(["small_batch"]):
        jobs.append({**spec, "method": "rbfopt",
                     "settings": {"algorithm": "MSRSM", "global_search_method": "sampling", "rbf": "auto"},
                     "job_id": spec["job_id"] + "_rbfopt_msrsm_sampling",
                     "purpose": "new MSRSM/sampling configuration; original Gutmann results retained"})
    return jobs


def source_files():
    names = ["process_followup_runner.py", "run_process_followup_dantzig.sh",
             "docs/process_followup_dantzig.md", "tests/test_process_followup_runner.py",
             "requirements-grid-trace.txt", "requirements-fmqa.txt", "LICENSE",
             "evaluation_trace.py", "instrumentation.py", "grid_dsda.py", "cpu_affinity.py",
             "overnight_benchmark/__init__.py", "overnight_benchmark/common.py",
             "overnight_benchmark/runner.py", "fmqa_benchmark/__init__.py",
             "fmqa_benchmark/protocol.py", "fmqa_benchmark/optimizer.py", "fmqa_benchmark/surrogate.py",
             "fmqa_benchmark/qhd_surrogate.py",
             "fmqa_benchmark/reference/original.manifest.json", "fmqa_benchmark/reference/initial_designs.json"]
    files = [ROOT / name for name in names]
    for folder in ("case_studies", "case_study_data", "fmqa_benchmark/vendor"):
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file()
                  and (p.suffix in {".py", ".csv", ".json"} or p.name == "LICENSE")]
    if EXPERIMENT:
        files += [ROOT / name for name in EXPERIMENT.SOURCE_FILES]
    return sorted(set(files))


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()}


def verify_sources(run):
    if run["kind"] != experiment_kind() or run["plan"] != plan() or run["source_files_sha256"] != source_hashes():
        raise ValueError("Run plan/source changed. Resume with the original extracted runner.")


def frozen_starts(spec):
    from case_studies.common import generate_lhc_starting_points
    oracle = problem(spec)
    points = generate_lhc_starting_points(len(oracle["lower"]), spec["n_starts"],
                                          oracle["lower"], oracle["upper"], spec["seed"])
    if [list(p) for p in points] != spec["starting_points"]:
        raise ValueError("LHC coordinates differ from the frozen design")


def runtime(config, role):
    if EXPERIMENT and hasattr(EXPERIMENT, "runtime"):
        return EXPERIMENT.runtime(config, role)
    from cpu_affinity import affinity_record, pin_cpu
    from fmqa_benchmark.protocol import verify_lookup_sources
    if not platform.node().startswith("dantzig") and not config["allow_other_host"]:
        raise ValueError("Use this runner on Dantzig (local checks require --allow-other-host).")
    cpu = pin_cpu(config["cpu"])
    requirements = "requirements-fmqa.txt" if role == "fmqa" else "requirements-grid-trace.txt"
    expected = dict(line.split("==") for line in (ROOT / requirements).read_text().splitlines()
                    if line and not line.startswith("#"))
    versions = {name: importlib.metadata.version(name) for name in expected}
    if versions != expected:
        raise ValueError(f"Environment differs from {requirements}: {versions}")
    data_hashes = verify_lookup_sources()
    details = {}
    if role == "dfo":
        import bam
        for spec in plan():
            frozen_starts(spec)
        for name in ("bonmin", "ipopt", "bam_license"):
            path = Path(config[name])
            if not path.is_file() or (name != "bam_license" and not os.access(path, os.X_OK)):
                raise ValueError(f"Missing/unusable {name}: {path}")
            details[name + "_sha256"] = sha(path)
        bam.set_license_file(config["bam_license"])
        details["bam_native"] = list(bam.Bam.get_solver_version())
        if details["bam_native"] != [2026, 9, 10]:
            raise ValueError(f"Unexpected BAM native version: {details['bam_native']}")
        # Smoke checks are excluded from the measured run plan.
        if EXPERIMENT:
            EXPERIMENT.smoke(config)
        else:
            from case_studies.column_rbfopt import run_column_rbfopt
            from case_studies.small_batch_bam import run_small_batch_bam
            run_column_rbfopt(seed=10, max_evaluations=4,
                             minlp_solver_path=config["bonmin"], nlp_solver_path=config["ipopt"])
            run_small_batch_bam(seed=0, max_evaluations=4, bam_license_file=config["bam_license"])
    else:
        from dwave.samplers import SimulatedAnnealingSampler
        from fmqa_benchmark.surrogate import train
        vendor = ROOT / "fmqa_benchmark/vendor"
        details["upstream"] = read(vendor / "provenance.json")
        for name, source in details["upstream"].items():
            for relative, digest in source["files_sha256"].items():
                if sha(vendor / name / relative) != digest:
                    raise ValueError("Vendored FMQA source checksum mismatch")
        bqm = train(["00", "01", "11"], [1, .5, 0], seed=0, epochs=5, learning_rate=.01)
        samples = [SimulatedAnnealingSampler().sample(bqm, num_reads=3, num_sweeps=20, seed=42)
                   for _ in range(2)]
        if not (samples[0].record.sample == samples[1].record.sample).all():
            raise ValueError("Seeded FMQA-SA smoke check failed")
    return {"host": platform.node(), "platform": platform.platform(), "python": platform.python_version(),
            "executable": sys.executable, "versions": versions, "affinity": affinity_record(cpu),
            "thread_environment": {k: os.environ.get(k) for k in THREAD_ENV},
            "lookup_data_sha256": data_hashes, **details}


class DurableTrace(EvaluationTrace):
    def write(self, event):
        super().write(event)
        os.fsync(self.handle.fileno())


def validate_trace(events, record, spec):
    validate_events(events, record)
    if not spec["n_starts"] <= len(events) <= spec["max_evaluations"]:
        raise ValueError("Callback count is outside the declared evaluation budget")
    if [e["point"] for e in events[:spec["n_starts"]]] != spec["starting_points"]:
        raise ValueError("Trace initial coordinates differ from the frozen ordered design")
    oracle = problem(spec)
    best, seen, previous = None, set(), 0.0
    for i, event in enumerate(events):
        point = tuple(event["point"])
        if len(point) != len(oracle["lower"]) or any(type(v) is not int or not lo <= v <= hi
                for v, lo, hi in zip(point, oracle["lower"], oracle["upper"])):
            raise ValueError("Invalid integer coordinate")
        if [int(round(v)) for v in event["requested_point"]] != list(point):
            raise ValueError("Requested coordinate differs from evaluated coordinate")
        raw = oracle["objective"](point)
        value = raw if math.isfinite(raw) else math.nan if spec["method"] == "bam" else 1e6
        if (event["value"], event["value_kind"]) != finite_value(value):
            raise ValueError("Trace objective differs from original lookup data")
        if best is None or math.isnan(best) or value < best:
            best = value
        if (event["incumbent"], event["incumbent_kind"]) != finite_value(best):
            raise ValueError("Incorrect incumbent history")
        if event["repeated_point"] != (point in seen):
            raise ValueError("Incorrect repeated-point marker")
        seen.add(point)
        if event["phase"] != ("initial" if i < spec["n_starts"] else "adaptive"):
            raise ValueError("Incorrect evaluation phase")
        finished, duration = event["completed_elapsed_s"], event["objective_wall_s"]
        if not (math.isfinite(finished) and math.isfinite(duration) and previous <= finished and 0 <= duration <= finished):
            raise ValueError("Invalid callback clock")
        if "started_elapsed_s" in event and not (
                previous <= event["started_elapsed_s"] <= finished
                and duration <= finished - event["started_elapsed_s"] + 1e-9):
            raise ValueError("Invalid callback start/finish sequence")
        previous = finished
    if (record["unique_evals"] != len(seen) or tuple(record["best_point"]) not in seen
            or not math.isclose(record["best_value"], best, rel_tol=1e-12, abs_tol=1e-9)
            or oracle["objective"](record["best_point"]) != best):
        raise ValueError("Final optimizer result disagrees with callback history")


def dfo_lookup(spec, config, directory):
    frozen_starts(spec)
    if EXPERIMENT:
        runner, kwargs = EXPERIMENT.run_dfo, {"spec": spec, "config": config}
    else:
        module = importlib.import_module(f"case_studies.{spec['case_name']}_{spec['method']}")
        runner = getattr(module, f"run_{spec['case_name']}_{spec['method']}")
        kwargs = dict(seed=spec["seed"], n_starts=spec["n_starts"], max_evaluations=spec["max_evaluations"],
                      verbose=True, **spec["settings"])
        if spec["method"] == "rbfopt":
            kwargs.update(minlp_solver_path=config["bonmin"], nlp_solver_path=config["ipopt"])
        if spec["method"] == "bam":
            kwargs["bam_license_file"] = config["bam_license"]
    with DurableTrace(directory / "lookup.csv", spec) as trace:
        output = runner(**kwargs)
        elapsed = trace.timer() - trace.origin
        record = output["result_record"]
        validate_trace(trace.events, record, spec)
        artifact = trace.complete(record)
    return {"status": "completed", "result_record": record, "trace": artifact,
            "search_wall_s": elapsed, "lookup_wall_s": sum(e["objective_wall_s"] for e in trace.events),
            "clock_scope": "runner entry through optimizer return; includes trace writes; excludes validation/export",
            "stop_reason": output.get("stop_reason")}


def fmqa_lookup(spec, config, directory):
    from fmqa_benchmark.optimizer import optimize
    from instrumentation import make_result_record
    oracle = problem(spec)
    path = directory / "evaluations.jsonl"
    append(path, {"event": "run_start", "run_key": spec, "clock_origin": "FMQA optimize entry",
                  "evaluation_source": "lookup; no GDP/NLP solve is performed"})
    seen, events = set(), []

    def evaluated(event, state):
        point = tuple(event["point"])
        entry = {**event, "requested_point": event["point"], "repeated_point": point in seen,
                 "value_kind": "finite", "incumbent_kind": "finite", "exception_type": None}
        append(path, entry)
        seen.add(point)
        events.append(entry)
        save(directory / "checkpoint.json", state)

    from fmqa_benchmark.surrogate import train as legacy_train
    trainer = {"trainer": EXPERIMENT.train if EXPERIMENT and hasattr(EXPERIMENT, "train") else legacy_train}
    state = optimize(oracle["objective"], oracle["lower"], oracle["upper"], spec["starting_points"],
                     spec["max_evaluations"], spec["seed"], spec["settings"], on_evaluation=evaluated,
                     on_proposal=lambda event: append(directory / "proposals.jsonl", event), **trainer)
    record = make_result_record(
        spec["csv_name"], getattr(EXPERIMENT, "RESULT_METHOD", "FMQA-SA"), spec["seed"], spec["n_starts"], spec["max_evaluations"],
        state["best_value"], state["best_point"], state["total_evals"], state["wall_time_s"],
        state["has_feasible_solution"] and math.isclose(state["best_value"], oracle["target"], rel_tol=0, abs_tol=1e-12),
        state["incumbent_trajectory"], initial_evals=state["initial_evals"], adaptive_evals=state["adaptive_evals"],
        unique_evals=state["unique_evals"], solver_status=state["status"])
    if state["status"] == "completed":
        validate_trace(events, record, spec)
    append(path, {"event": "run_complete" if state["status"] == "completed" else "run_incomplete",
                  "result_record": record})
    return {"status": state["status"], "result_record": record,
            "trace": {"path": path.name, "sha256": sha(path), "evaluations": len(events)},
            "search_wall_s": state["wall_time_s"], "lookup_wall_s": state["objective_wall_s"],
            "clock_scope": "original FMQA optimize clock, including trace/checkpoint writes",
            "fmqa_state": state}


def worker(directory, identifier):
    from cpu_affinity import pin_cpu
    run = read(directory / "run.json")
    verify_sources(run)
    spec = next(s for s in run["plan"] if s["job_id"] == identifier)
    job = directory / "jobs" / identifier
    pin_cpu(run["config"]["cpu"])
    try:
        if EXPERIMENT and hasattr(EXPERIMENT, "worker_setup"):
            EXPERIMENT.worker_setup()
        lookup = fmqa_lookup if spec["method"] == "fmqa_sa" else dfo_lookup
        result = lookup(spec, run["config"], job)
    except Exception as error:
        traceback.print_exc()
        result = {"status": "error", "error_type": type(error).__name__, "error": str(error)}
    save(job / "result.json", {"spec": spec, "completed_utc": now(), **result})
    return 0 if result["status"] == "completed" else 1


def command(config, role, *arguments):
    python = config[role + "_python"]
    environment = Path(python).parent.parent
    # The original FMQA environment is a Python venv, not necessarily a conda
    # prefix. Never send a venv to `conda run --prefix`.
    prefix = ([config["conda"], "run", "--no-capture-output", "--prefix", str(environment), "python"]
              if config["conda"] and (environment / "conda-meta").is_dir() else [python])
    return [*prefix, str(ROOT / "process_followup_runner.py"), *map(str, arguments),
            "--experiment", config.get("experiment", "followup")]


def check_environments(directory, config):
    identities = {}
    for role in getattr(EXPERIMENT, "RUNTIME_ROLES", ("dfo", "fmqa")):
        output = directory / f"runtime_{role}.json"
        with (directory / f"check_{role}.log").open("w") as log:
            process = subprocess.Popen(command(config, role, "_check", "--run-dir", directory, "--role", role),
                                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=180)
            except BaseException:
                stop(process)
                raise
        if code:
            raise RuntimeError(f"{role} environment check failed; inspect {directory / f'check_{role}.log'}")
        identities[role] = read(output)
        print(f"  {role} environment and solver smoke checks passed", flush=True)
    return identities


def assert_inactive(job):
    if (job / "process.json").exists():
        pid = read(job / "process.json")["pid"]
        proc = Path(f"/proc/{pid}/cmdline")
        if proc.exists():
            cmd = proc.read_bytes().replace(b"\0", b" ").decode(errors="replace")
            if str(job.parents[1]) in cmd and job.name in cmd:
                raise RuntimeError(f"Previous worker PID {pid} is still active: {job}")


def saved_result(job, spec):
    if not terminal_valid(job):
        return None
    result = read(job / "result.json")
    if result["spec"] != spec:
        raise ValueError("Saved job does not match the plan")
    if result["status"] == "completed":
        path = job / result["trace"]["path"]
        entries = jsonl(path)
        if (sha(path) != result["trace"]["sha256"] or entries[0]["run_key"] != spec
                or entries[-1]["event"] != "run_complete" or entries[-1]["result_record"] != result["result_record"]):
            raise ValueError("Trace header/footer/checksum mismatch")
        validate_trace(entries[1:-1], result["result_record"], spec)
    return result


def launch(directory, spec, config, retry_errors):
    job = directory / "jobs" / spec["job_id"]
    assert_inactive(job)
    old = saved_result(job, spec)
    if old and (old["status"] == "completed" or not retry_errors):
        return old
    if job.exists():
        previous = directory / "previous_attempts"
        previous.mkdir(exist_ok=True)
        job.rename(previous / f"{job.name}_{time.time_ns()}")
    job.mkdir(parents=True)
    save(job / "spec.json", spec)
    role = "fmqa" if spec["method"] == "fmqa_sa" else "dfo"
    started = time.monotonic()
    timed_out = False
    with (job / "run.log").open("w") as log:
        process = subprocess.Popen(command(config, role, "_worker", "--run-dir", directory, "--job-id", spec["job_id"]),
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        save(job / "process.json", {"pid": process.pid, "started_utc": now()})
        try:
            while process.poll() is None:
                remaining = config["hard_seconds"] - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    stop(process)
                    break
                try:
                    process.wait(timeout=min(30, remaining))
                except subprocess.TimeoutExpired:
                    print(f"  running {time.monotonic() - started:.0f}s: {spec['job_id']}", flush=True)
        except BaseException:
            stop(process)
            raise
    path = job / "result.json"
    result = read(path) if path.exists() else {"spec": spec, "status": "error", "error": "Worker exited without a result"}
    if timed_out:
        result["status"] = "hard_time_limit"
    elif process.returncode and result["status"] == "completed":
        result["status"] = "error"
    result.update(worker_returncode=process.returncode, worker_wall_s=time.monotonic() - started, completed_utc=now())
    save(path, result)
    save(job / "terminal.json", {"files_sha256": {p.relative_to(job).as_posix(): sha(p)
         for p in sorted(job.rglob("*")) if p.is_file() and p.name != "terminal.json" and not p.name.endswith(".tmp")}})
    saved_result(job, spec)
    return result


def report(directory):
    run = read(directory / "run.json")
    rows, callbacks, results = [], [], []
    for spec in run["plan"]:
        job = directory / "jobs" / spec["job_id"]
        result = saved_result(job, spec)
        if result is None:
            continue
        results.append(result)
        rows.append({"job_id": spec["job_id"], "case_name": spec["case_name"], "status": result["status"],
                     "settings": spec["settings"], "search_wall_s": result.get("search_wall_s"),
                     "lookup_wall_s": result.get("lookup_wall_s"), **result.get("result_record", {})})
        if result["status"] == "completed":
            entries = jsonl(job / result["trace"]["path"])[1:-1]
            callbacks.extend({"job_id": spec["job_id"], "case_name": spec["case_name"],
                              "method": spec["method"], "seed": spec["seed"], **e} for e in entries)
    summary = {"planned_runs": len(run["plan"]), "finished_runs": len(results),
               "completed_runs": sum(r["status"] == "completed" for r in results),
               "failed_runs": sum(r["status"] != "completed" for r in results),
               "evaluation_callbacks": len(callbacks),
               "all_completed": len(results) == len(run["plan"]) and all(r["status"] == "completed" for r in results),
               "objective_mode": "lookup; pointwise NLP costs must be joined separately", "updated_utc": now()}
    csv_file(directory / "runs.csv", rows)
    csv_file(directory / "trajectories.csv", callbacks)
    if EXPERIMENT:
        summary.update(EXPERIMENT.report_costs(directory, results, callbacks))
    save(directory / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return summary


def execute(directory, retry_errors=False):
    with locked(directory):
        run = read(directory / "run.json")
        verify_sources(run)
        for spec in run["plan"]:
            assert_inactive(directory / "jobs" / spec["job_id"])
        try:
            identity = check_environments(directory, run["config"])
            if "runtime" in run and identity != run["runtime"]:
                raise ValueError("Runtime changed since this run was created")
            run["runtime"] = identity
            save(directory / "run.json", run)
            for i, spec in enumerate(run["plan"], 1):
                print(f"[{i}/{len(run['plan'])}] {spec['job_id']}", flush=True)
                result = launch(directory, spec, run["config"], retry_errors)
                print(f"  {result['status']}; {result.get('result_record', {}).get('total_evals', 0)} callbacks", flush=True)
                report(directory)
        finally:
            report(directory)
            pack(directory)
    return 0 if read(directory / "summary.json")["all_completed"] else 1


def bundle(output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    folder = EXPERIMENT.BUNDLE_FOLDER if EXPERIMENT else "process_followup_runner"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():
            archive.write(path, folder + "/" + path.relative_to(ROOT).as_posix())
        archive.writestr(folder + "/BUNDLE_MANIFEST.json", json.dumps(
            {"kind": experiment_kind(), "created_utc": now(), "source_files_sha256": source_hashes(), "plan": plan()}, indent=2))
    output.with_suffix(".zip.sha256").write_text(f"{sha(output)}  {output.name}\n")
    print(f"BUNDLE_ZIP={output}")


def main(argv=None):
    global EXPERIMENT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "bundle", "check", "run", "resume", "status", "pack", "_worker", "_check"))
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/process_followup")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--cpu", type=int, default=None)
    parser.add_argument("--dfo-python", default=sys.executable)
    parser.add_argument("--fmqa-python", default="")
    parser.add_argument("--conda", default="")
    parser.add_argument("--bonmin", default=shutil.which("bonmin") or "")
    parser.add_argument("--ipopt", default=shutil.which("ipopt") or "")
    parser.add_argument("--bam-license", default=os.environ.get("BAM_LICENSE_FILE", ""))
    parser.add_argument("--hard-seconds", type=float, default=2100)
    parser.add_argument("--allow-other-host", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--role", choices=("dfo", "fmqa"))
    parser.add_argument("--job-id")
    parser.add_argument("--experiment", choices=("followup", "small_batch_full_domain", "fmqa_qhd"), default="followup")
    parser.add_argument("--scope", choices=("small_batch", "process", "grid", "all"), default="small_batch")
    parser.add_argument("--seeds", nargs="+", type=int)
    args = parser.parse_args(argv)
    modules = {"small_batch_full_domain": "small_batch_full_domain", "fmqa_qhd": "fmqa_qhd_experiment"}
    EXPERIMENT = importlib.import_module(modules[args.experiment]) if args.experiment in modules else None
    if args.experiment == "fmqa_qhd":
        selection = read(args.run_dir / "run.json")["config"] if args.run_dir else vars(args)
        EXPERIMENT.configure(selection["scope"], selection.get("seeds"))
    os.environ.update(THREAD_ENV)
    os.environ.update(PYTHONPATH=str(ROOT), PYTHONUNBUFFERED="1", PYTHONNOUSERSITE="1")
    if args.mode == "plan":
        print(json.dumps(plan(), indent=2))
        return 0
    if args.mode == "bundle":
        if args.output is None:
            parser.error("bundle requires --output FILE.zip")
        bundle(args.output)
        return 0
    if args.mode in {"resume", "status", "pack", "_worker", "_check"}:
        if args.run_dir is None:
            parser.error(f"{args.mode} requires --run-dir PATH")
        directory = args.run_dir.resolve()
        if args.mode == "_worker":
            return worker(directory, args.job_id)
        if args.mode == "_check":
            save(directory / f"runtime_{args.role}.json", runtime(read(directory / "run.json")["config"], args.role))
            return 0
        if args.mode == "resume":
            return execute(directory, args.retry_errors)
        with locked(directory):
            for spec in read(directory / "run.json")["plan"]:
                assert_inactive(directory / "jobs" / spec["job_id"])
            report(directory)
            if args.mode == "pack":
                pack(directory)
        return 0
    config = {"cpu": args.cpu, "hard_seconds": args.hard_seconds, "allow_other_host": args.allow_other_host,
              "experiment": args.experiment,
              **{name: str(Path(getattr(args, name)).expanduser().absolute()) if getattr(args, name) else ""
                 for name in ("dfo_python", "fmqa_python", "conda", "bonmin", "ipopt", "bam_license")}}
    if args.experiment == "fmqa_qhd":
        config.update(scope=args.scope, seeds=args.seeds)
    if not math.isfinite(args.hard_seconds) or args.hard_seconds <= 0 or not args.fmqa_python:
        parser.error("A positive --hard-seconds and --fmqa-python are required")
    args.output_root.mkdir(parents=True, exist_ok=True)
    prefix = getattr(EXPERIMENT, "RUN_PREFIX", "small_batch_full_domain_") if EXPERIMENT else "process_followup_"
    directory = Path(tempfile.mkdtemp(prefix=prefix + time.strftime("%Y%m%d_%H%M%S_"), dir=args.output_root)).resolve()
    print(f"RUN_DIR={directory}", flush=True)
    protocol = EXPERIMENT.PROTOCOL if EXPERIMENT else {
        "initial_evaluations_in_budget": True, "column_original_seeds": list(range(1, 10)),
        "column_supplement_seed": 10, "column_seed0": "all 3 starts infeasible; excluded in original study",
        "objective_mode": "original lookup tables; no online GDP/NLP solves",
        "trajectory": "every actual objective callback, including repeats; internal proposals are not callbacks"}
    save(directory / "run.json", {"kind": experiment_kind(), "created_utc": now(), "config": config,
         "plan": plan(), "source_files_sha256": source_hashes(),
         "protocol": protocol})
    for path in source_files():
        destination = directory / "source" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    if args.mode == "check":
        check_environments(directory, config)
        return 0
    return execute(directory)


if __name__ == "__main__":
    sys.exit(main())
