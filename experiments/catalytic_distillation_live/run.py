"""Live DFO runs on the corrected catalytic distillation column.

Every evaluation solves the NLP of the requested configuration (CONOPT from
init.gdx, one thread), unless the shared response cache already holds it.
Methods share the gap-coordinate box, the seven starts of each seed, the
budget accounting, and the penalties of the published process comparison:

  dsda     D-SDA from the best accepted start, Separable neighborhood (one-coordinate
           moves), improvement tolerance 1e-5, as in the adopted process D-SDA; no
           configuration is evaluated twice
  rbfopt   RBFOpt 4.3 MSRSM with genetic global search, warm-started on the starts
  bam      BAM with the starts as its predetermined design
  fmqa_sa  FMQA with simulated annealing
  uniform  uniform sampling without replacement over the box after the starts
  nomad    NOMAD 4.6 (experiments/mixed_integer_dfo adapter)
  miso     MISO, soogo CPTV (experiments/mixed_integer_dfo adapter)

Inadmissible box points (sum of gaps above 17) are charged to the budget and
returned as infeasible without an NLP solve.  Completion time is search overhead
plus the measured solve time of every evaluated point, as in the published runs.

  python run.py plan --output DIR
  python run.py run --output DIR --gams GAMS --cpus 0-7 [--python-fmqa PY --python-midfo PY ...]
  python run.py summarize --output DIR
"""

import argparse
from collections.abc import Mapping
import csv
from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
import traceback

import case

HERE = Path(__file__).resolve().parent
REPO = case.REPO
METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa", "uniform", "nomad", "miso")
BUDGETS = (25, 50, 100)
SEEDS = tuple(range(10))
PENALTY = 1e6
UNIFORM_STREAM = 20261101
HIT_RTOL = 1e-5
SETTINGS = {
    "dsda": {"diagonal": False, "tie_break": "first", "tol": 1e-12, "improvement_abs_tol": 1e-5},
    "rbfopt": {"algorithm": "MSRSM", "global_search_method": "genetic", "rbf": "auto", "num_cpus": 1},
    "bam": {"integrality": "all_integer"},
    "fmqa_sa": {"epochs": 1000, "learning_rate": 0.01, "num_reads": 100, "num_sweeps": 1000, "time_limit": 7200},
    "uniform": {},
    "nomad": {},
    "miso": {},
}
PYTHON_OPTION = {"fmqa_sa": "python_fmqa", "bam": "python_bam", "nomad": "python_midfo", "miso": "python_midfo"}
THREAD_ENV = {k: "1" for k in ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                               "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}


def write(path, value):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=str) + "\n")
    tmp.replace(path)


def append(path, value):
    with open(path, "a") as f:
        f.write(json.dumps(value, default=str) + "\n")


def jsonl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()] if Path(path).exists() else []


class BudgetStop(Exception):
    """Raised after evaluation B for methods without a native budget."""


class LiveOracle:
    """Charged live evaluations with the callback contract of the published process oracle."""

    penalty = PENALTY

    def __init__(self, spec, evaluator, directory):
        self.spec, self.evaluator, self.directory = spec, evaluator, Path(directory)
        self.events, self.wall_times = [], []
        self.budget_overrun = False
        self.started = time.perf_counter()

    @property
    def call_count(self):
        return len(self.events)

    def __call__(self, coordinates):
        started = time.perf_counter()
        spec, n0 = self.spec, len(self.spec["starts"])
        if self.call_count >= spec["budget"]:
            self.budget_overrun = True
            append(self.directory / "budget_overruns.jsonl", {"after_evaluations": self.call_count,
                                                             "coordinates": [float(x) for x in coordinates]})
            raise RuntimeError("Optimizer swallowed the hard budget stop")
        error, point = None, ()
        try:
            point = tuple(int(round(float(x))) for x in coordinates)
            if not case.in_box(point):
                raise ValueError(f"Optimizer requested out-of-domain point: {point}")
            if self.call_count < n0 and list(point) != spec["starts"][self.call_count]:
                raise ValueError("Optimizer changed the shared initial order")
        except (ValueError, TypeError, OverflowError) as exc:
            error = str(exc)
        record = None if error else self.evaluator(point)
        accepted = bool(record and record["accepted"])
        method = spec["method"]
        value = record["objective"] if accepted else math.nan if method == "bam" else math.inf if method == "fmqa_sa" else PENALTY
        stop = self.call_count + 1 == spec["budget"] and method != "bam"
        event = dict(index=self.call_count + 1, origin="shared_start" if self.call_count < n0 else method,
                     point=list(point), positions=list(case.positions(point)) if point and case.in_box(point) else None,
                     accepted=accepted, raw_objective=record["objective"] if accepted else None,
                     method_value=value if math.isfinite(value) else None,
                     status=error and "protocol_error" or record["status"],
                     solved_now=bool(record and record["status"] != "logical_infeasible" and not record["cached"]),
                     point_cost_s=record["solve_wall_s"] if record else 0.0,
                     lookup_wall_s=time.perf_counter() - started, elapsed_s=time.perf_counter() - self.started)
        self.events.append(event)
        self.wall_times.append(event["lookup_wall_s"])
        append(self.directory / "callbacks.jsonl", event)
        if error:
            raise ValueError(error)
        if stop:
            raise BudgetStop()
        return value


class LiveResponses(Mapping):
    """Lazy (accepted, objective) mapping for the mixed-integer DFO Lookup."""

    def __init__(self, evaluator):
        self.evaluator = evaluator

    def __getitem__(self, point):
        record = self.evaluator(point)
        return record["accepted"], record["objective"]

    def __contains__(self, point):
        return case.in_box(tuple(point))

    def __iter__(self):
        return case.box_points()

    def __len__(self):
        return (case.CAP + 1) ** case.DIM


class LiveCosts(Mapping):
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def __getitem__(self, point):
        return self.evaluator(point)["solve_wall_s"]

    def __iter__(self):
        return case.box_points()

    def __len__(self):
        return (case.CAP + 1) ** case.DIM


def load_midfo():
    spec = importlib.util.spec_from_file_location("mixed_integer_dfo", REPO / "experiments/mixed_integer_dfo/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_midfo(spec, evaluator_factory, directory):
    """NOMAD or MISO in a forked child; a native crash is rerun once and kept only on an identical path."""
    import multiprocessing as mp

    midfo = load_midfo()

    def child(stream, log):
        evaluator = evaluator_factory()
        job = {"spec": {**spec, "job_id": spec["job_id"]}}
        lookup = midfo.Lookup(job, LiveResponses(evaluator), LiveCosts(evaluator),
                              lambda p: "logical_infeasible" if not case.admissible(p) else "solved", stream)
        details = midfo.ADAPTERS[spec["method"]](lookup, spec["seed"], log)
        write(Path(stream).with_suffix(".details.json"), {"details": details, "overruns": lookup.overruns,
                                                          "invalid": lookup.invalid, "solved_now": evaluator.live_solves})

    attempts = []
    for attempt in (1, 2):
        stream = directory / f"attempt{attempt}.jsonl"
        stream.unlink(missing_ok=True)
        process = mp.get_context("fork").Process(target=child, args=(stream, directory / f"attempt{attempt}.log"))
        process.start()
        process.join()
        attempts.append(dict(attempt=attempt, exitcode=process.exitcode, events=jsonl(stream)))
        if process.exitcode == 0:
            break
    final = attempts[-1]
    identical = len(attempts) == 1 or [e["point"] for e in attempts[0]["events"]] == \
        [e["point"] for e in final["events"][:len(attempts[0]["events"])]]
    status = ("completed" if len(attempts) == 1 and final["exitcode"] == 0 else
              "completed_after_verified_rerun" if final["exitcode"] == 0 and identical else
              f"crashed_exit_{final['exitcode']}")
    events = [dict(e, solved_now=None) for e in final["events"]]
    for e in events:
        e["status"] = "accepted" if e["accepted"] else "logical_infeasible" if e["nlp_solve"] == "logical_infeasible" else "unaccepted"
    with open(directory / "callbacks.jsonl", "w") as f:
        f.writelines(json.dumps(e) + "\n" for e in events)
    details = json.loads(Path(directory / f"attempt{final['attempt']}.details.json").read_text()) \
        if Path(directory / f"attempt{final['attempt']}.details.json").exists() else {}
    return status, events, dict(details, attempts=[{k: a[k] for k in ("attempt", "exitcode")} for a in attempts])


def optimize(spec, oracle, config):
    """Run one non-forked method; returns method-specific details."""
    import numpy as np
    import random

    random.seed(spec["seed"])
    np.random.seed(spec["seed"])
    method, starts, n0 = spec["method"], spec["starts"], len(spec["starts"])
    lower, upper = spec["lower"], spec["upper"]
    if method == "uniform":
        for p in starts:
            oracle(p)
        rng = np.random.default_rng([UNIFORM_STREAM, spec["seed"]])
        rest = [p for p in case.box_points() if list(p) not in starts]
        for i in rng.permutation(len(rest)):
            oracle(rest[i])
        return {}
    if method == "dsda":
        sys.path.insert(0, str(REPO))
        from grid_dsda import dsda_from_csv

        for p in starts:
            oracle(p)
        accepted = [e for e in oracle.events if e["accepted"]]
        if not accepted:
            raise RuntimeError("No accepted initial point; no reseeding")
        best = min(accepted, key=lambda e: e["raw_objective"])
        grid = dict.fromkeys(case.box_points())
        # The shared starts are known, so D-SDA never requests a configuration twice.
        known = {tuple(e["point"]): e["method_value"] for e in oracle.events}
        result = dsda_from_csv(csv_path="live", start_point=tuple(best["point"]), start_value=best["raw_objective"],
                               grid=grid, tracked_objective=oracle, max_points_explored=spec["budget"] - n0,
                               verbose=False, known_values=known, **spec["settings"])
        return {"returned": str(result)[:2000]}
    if method == "rbfopt":
        import rbfopt

        settings = rbfopt.RbfoptSettings(max_evaluations=spec["budget"], rand_seed=spec["seed"],
                                         minlp_solver_path=config["bonmin"], nlp_solver_path=config["ipopt"],
                                         **spec["settings"])
        bb = rbfopt.RbfoptUserBlackBox(len(lower), np.array(lower), np.array(upper), np.array(["I"] * len(lower)), oracle)
        alg = rbfopt.RbfoptAlgorithm(settings, bb, init_node_pos=np.array(starts, dtype=float), init_node_val=None,
                                     do_init_strategy=False)
        return {"returned": str(alg.optimize())[:2000]}
    if method == "bam":
        import bam

        bam.set_license_file(config["bam_license"])
        values = np.array([oracle(p) for p in starts], dtype=float)
        options = {"print_to_screen": 1, "x_evaluated": np.array(starts, dtype=float), "f_evaluated": values,
                   "max_evals": spec["budget"] - n0}
        result = bam.minimize(oracle, x0=None, bounds=list(zip(lower, upper)), integrality=[1] * len(lower), options=options)
        return {k: str(getattr(result, k, None)) for k in ("x", "fun", "status", "success", "message", "nit", "nfev")}
    if method == "fmqa_sa":
        sys.path.insert(0, str(REPO))
        from fmqa_benchmark.optimizer import optimize as fmqa
        from fmqa_benchmark.qhd_surrogate import cpu_settings

        with cpu_settings():
            fmqa(oracle, lower, upper, starts, spec["budget"], spec["seed"], spec["settings"])
        return {}
    raise ValueError(f"Unknown method {method}")


def worker(args):
    directory = Path(args.job_dir)
    spec = json.loads((directory / "spec.json").read_text())
    config = json.loads((directory / "config.json").read_text())
    (directory / "callbacks.jsonl").unlink(missing_ok=True)
    started = time.perf_counter()
    status, error, details, events = "completed", None, {}, []

    def evaluator_factory():
        return case.Evaluator(config["cache"], config["gams"])

    try:
        if spec["method"] in ("nomad", "miso"):
            status, events, details = run_midfo(spec, evaluator_factory, directory)
        else:
            oracle = LiveOracle(spec, evaluator_factory(), directory)
            try:
                details = optimize(spec, oracle, config)
            except BudgetStop:
                pass
            events = oracle.events
            if oracle.budget_overrun:
                status = "budget_overrun"
    except Exception:  # noqa: BLE001  A method failure is a recorded outcome.
        status, error = "execution_failed", traceback.format_exc()[-4000:]
        events = jsonl(directory / "callbacks.jsonl")
    wall = time.perf_counter() - started
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    point_cost = sum(e["point_cost_s"] for e in events)
    callbacks = sum(e["lookup_wall_s"] for e in events)
    write(directory / "result.json", dict(
        spec=spec, status=status, error=error, details=details, evaluations=len(events),
        accepted_evaluations=len(accepted), logical_rejections=sum(e["status"] == "logical_infeasible" for e in events),
        distinct_points=len({tuple(e["point"]) for e in events}),
        solved_now=details.get("solved_now") if spec["method"] in ("nomad", "miso") else sum(bool(e.get("solved_now")) for e in events),
        best_objective=best["raw_objective"] if best else None, best_point=best["point"] if best else None,
        best_positions=list(case.positions(best["point"])) if best else None,
        best_index=best["index"] if best else None, worker_wall_s=wall, callback_wall_s=callbacks,
        search_overhead_s=wall - callbacks, point_cost_s=point_cost, completion_s=wall - callbacks + point_cost,
        host=platform.node(), cpu=sorted(os.sched_getaffinity(0)),
        finished_utc=datetime.now(timezone.utc).isoformat()))
    return 0


def plan(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    starts = {seed: case.shared_starts(seed) for seed in args.seeds}
    jobs = [dict(job_id=f"{m}_B{b}_seed{s}", method=m, seed=s, budget=b, starts=starts[s],
                 lower=case.LOWER, upper=case.UPPER, settings=SETTINGS[m])
            for b in args.budgets for s in args.seeds for m in args.methods]
    write(output / "plan.json", dict(created_utc=datetime.now(timezone.utc).isoformat(), methods=args.methods,
                                     budgets=args.budgets, seeds=args.seeds, starts=starts, jobs=jobs,
                                     space=dict(coordinates="gaps", lower=case.LOWER, upper=case.UPPER,
                                                sum_limit=case.SUM_LIMIT)))
    print(f"{len(jobs)} jobs in {output / 'plan.json'}")
    return 0


def cpus(text):
    out = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def run(args):
    output = Path(args.output)
    jobs = json.loads((output / "plan.json").read_text())["jobs"]
    if args.methods:
        jobs = [j for j in jobs if j["method"] in args.methods]
    if args.jobs:
        jobs = [j for j in jobs if j["job_id"] in args.jobs]
    pending = [j for j in jobs if not (output / "runs" / j["job_id"] / "result.json").exists()]
    # Largest budgets first so long runs do not trail at the end.
    pending.sort(key=lambda j: -j["budget"])
    config = dict(cache=str(output / "cache.sqlite"), gams=args.gams, bonmin=args.bonmin, ipopt=args.ipopt,
                  bam_license=args.bam_license)
    case.Evaluator(config["cache"], args.gams).db.close()
    free, running = list(cpus(args.cpus)), {}
    env = {**os.environ, **THREAD_ENV, "PYTHONUNBUFFERED": "1"}
    print(f"{len(pending)} pending of {len(jobs)} jobs on CPUs {free}", flush=True)
    while pending or running:
        while pending and free:
            job, cpu = pending.pop(0), free.pop(0)
            directory = output / "runs" / job["job_id"]
            directory.mkdir(parents=True, exist_ok=True)
            write(directory / "spec.json", job)
            write(directory / "config.json", config)
            python = getattr(args, PYTHON_OPTION.get(job["method"], "python_default")) or sys.executable
            log = open(directory / "worker.log", "w")
            process = subprocess.Popen([python, str(HERE / "run.py"), "worker", "--job-dir", str(directory)],
                                       cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                       preexec_fn=lambda c=cpu: os.sched_setaffinity(0, {c}))
            running[process.pid] = (process, job, cpu, time.monotonic(), log)
        time.sleep(1)
        for pid, (process, job, cpu, started, log) in list(running.items()):
            timed_out = time.monotonic() - started > args.hard_seconds
            if timed_out:
                os.killpg(process.pid, signal.SIGKILL)
            if process.poll() is None and not timed_out:
                continue
            process.wait()
            log.close()
            del running[pid]
            free.append(cpu)
            result = output / "runs" / job["job_id"] / "result.json"
            if not result.exists():
                write(output / "runs" / job["job_id"] / "worker_failure.json",
                      dict(returncode=process.returncode, timed_out=timed_out))
            print(f"{job['job_id']:<28} cpu {cpu:>3} rc {process.returncode} "
                  f"{json.loads(result.read_text())['status'] if result.exists() else 'no result'}", flush=True)
    return 0


def summarize(args):
    output = Path(args.output)
    evaluator = case.Evaluator(output / "cache.sqlite", None, solve=lambda c: None)
    records = evaluator.records()
    accepted = {p: r["objective"] for p, r in records.items() if r["accepted"]}
    for path in args.reference or []:
        for row in csv.DictReader(open(path)):
            if row["solvestat"] == "1" and row["modelstat"] in ("1", "2"):
                p = case.gaps_of(tuple(int(row[k]) for k in ("f1", "c1", "c2", "c3", "f2", "b")))
                if case.admissible(p):
                    accepted[p] = min(accepted.get(p, math.inf), float(row["zobj"]))
    best_point = min(accepted, key=accepted.get)
    best = accepted[best_point]
    write(output / "best_known.json", dict(objective=best, gaps=list(best_point),
                                           positions=list(case.positions(best_point)),
                                           distinct_solved=len(records), distinct_accepted=len(accepted),
                                           references=args.reference or []))
    rows = []
    for path in sorted((output / "runs").glob("*/result.json")):
        r = json.loads(path.read_text())
        s = r["spec"]
        hit = r["best_objective"] is not None and abs(r["best_objective"] - best) <= HIT_RTOL * max(1.0, abs(best))
        rows.append(dict(job_id=s["job_id"], method=s["method"], seed=s["seed"], budget=s["budget"], status=r["status"],
                         evaluations=r["evaluations"], accepted=r["accepted_evaluations"],
                         logical_rejections=r["logical_rejections"], best_objective=r["best_objective"],
                         gap_to_best_known=None if r["best_objective"] is None else r["best_objective"] - best,
                         hit=hit, best_index=r["best_index"], completion_s=r["completion_s"],
                         point_cost_s=r["point_cost_s"], search_overhead_s=r["search_overhead_s"]))
    with open(output / "runs.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    groups = {}
    for r in rows:
        groups.setdefault((r["method"], r["budget"]), []).append(r)
    summary = []
    for (method, budget), g in sorted(groups.items()):
        gaps = sorted(r["gap_to_best_known"] for r in g if r["gap_to_best_known"] is not None)
        summary.append(dict(method=method, budget=budget, runs=len(g), hits=sum(r["hit"] for r in g),
                            completed=sum(r["status"].startswith("completed") for r in g),
                            median_gap=gaps[len(gaps) // 2] if gaps else None,
                            median_completion_s=sorted(r["completion_s"] for r in g)[len(g) // 2]))
    with open(output / "conditions.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)
    for s in summary:
        print(s)
    print(f"best known {best:.6f} at gaps {best_point} positions {case.positions(best_point)}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--output", required=True)
    p.add_argument("--methods", nargs="+", default=list(METHODS), choices=METHODS)
    p.add_argument("--budgets", nargs="+", type=int, default=list(BUDGETS))
    p.add_argument("--seeds", nargs="+", type=int, default=list(SEEDS))
    p = sub.add_parser("run")
    p.add_argument("--output", required=True)
    p.add_argument("--gams", required=True)
    p.add_argument("--cpus", required=True, help="CPUs for one pinned job each, e.g. 0-7 or 2,4,6")
    p.add_argument("--methods", nargs="+", choices=METHODS)
    p.add_argument("--jobs", nargs="+")
    p.add_argument("--hard-seconds", type=float, default=6 * 3600)
    p.add_argument("--bonmin", default=None)
    p.add_argument("--ipopt", default=None)
    p.add_argument("--bam-license", default=None)
    for option in ("python_default", "python_fmqa", "python_bam", "python_midfo"):
        p.add_argument("--" + option.replace("_", "-"), dest=option, default=None)
    p = sub.add_parser("worker")
    p.add_argument("--job-dir", required=True)
    p = sub.add_parser("summarize")
    p.add_argument("--output", required=True)
    p.add_argument("--reference", nargs="*", help="solves.csv files of the same protocol to include in the best-known value")
    args = parser.parse_args(argv)
    return {"plan": plan, "run": run, "worker": worker, "summarize": summarize}[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
