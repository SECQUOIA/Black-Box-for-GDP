"""Process D-SDA with multistart, replayed from the stored process responses.

The Grid D-SDA descends from each shared initial configuration in order of its
objective value while budget remains, whereas the published process D-SDA
descends only from the best initial configuration and then stops.  This
experiment reruns the 140 process D-SDA jobs under three protocols:

  single         the published single-descent protocol (replay control)
  ranked         the Grid rule: descents from all three shared starts, best first
  ranked_random  the Grid rule, then descents from uniformly drawn unvisited
                 configurations until the evaluation budget is exhausted

Configuration responses and point costs come from the sealed input package in
the D-SDA rerun return archive.  No NLP solver or process model is invoked, and
no method receives the reference target as a stopping criterion.
"""

import os

THREADS = {
    k: "1"
    for k in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "GOTO_NUM_THREADS",
        "NUMEXPR_MAX_THREADS",
    )
}
THREADS.update(OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE", CUDA_VISIBLE_DEVICES="")
os.environ.update(THREADS)

import argparse  # noqa: E402
from contextlib import contextmanager, redirect_stdout  # noqa: E402
import csv  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
import hashlib  # noqa: E402
import importlib.abc  # noqa: E402
import importlib.metadata  # noqa: E402
import importlib.util  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
from pathlib import Path  # noqa: E402
import platform  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import zipfile  # noqa: E402

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
ARCHIVE = REPO / "results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip"
ARCHIVE_SHA256 = "e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e"
PREFIX = "dsda_abs1e5_rerun_20261028_020753_2004611/"
VARIANTS = ("single", "ranked", "ranked_random")
IMPROVEMENT_ABS_TOL = 1e-5
RESTART_STREAM = 20261030
BLOCKED_MODULES = {
    "pyomo",
    "gams",
    "pyscipopt",
    "gdp",
    "gdp_models",
    "rbfopt",
    "bam",
    "fmqa_benchmark",
    "case_studies",
    "cyipopt",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def read_csv(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    rows = list(rows)
    with Path(path).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def finite_or_none(value):
    return value if value is not None and math.isfinite(value) else None


def quantile(values, q):
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def extract_package(archive, destination):
    """Unpack the sealed reproduction package and the archived process runs."""
    if sha(archive) != ARCHIVE_SHA256:
        raise ValueError(f"Return archive hash mismatch: {archive}")
    with zipfile.ZipFile(archive) as z:
        members = [
            n
            for n in z.namelist()
            if n.startswith(PREFIX + "reproduction/")
            or (n.startswith(PREFIX + "runs/") and "/grid_" not in n)
        ]
        z.extractall(destination, members)
    package = Path(destination) / PREFIX / "reproduction"
    for name, digest in read_json(package / "SHA256SUMS.json").items():
        if sha(package / name) != digest:
            raise ValueError(f"Sealed package hash mismatch: {name}")
    return package, Path(destination) / PREFIX / "runs"


class SolverBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED_MODULES:
            raise RuntimeError(f"Solver or model import prohibited: {fullname}")


SEALED_MODULES = ("grid_dsda", "instrumentation", "evaluation_trace", "adopted_analysis", "select_dsda_cpu")


@contextmanager
def sealed_modules(package):
    """Import the sealed sources, never same-named repository modules, then restore."""
    import numpy  # noqa: F401  Load numerical runtime before the import guard.
    import pandas  # noqa: F401

    saved = {name: sys.modules.pop(name) for name in SEALED_MODULES if name in sys.modules}
    sys.path.insert(0, str(package))
    blocker = SolverBlocker()
    try:
        import grid_dsda
        from adopted_analysis import hit

        if Path(grid_dsda.__file__).resolve().parent != Path(package).resolve():
            raise RuntimeError("Sealed grid_dsda was shadowed")
        sys.meta_path.insert(0, blocker)
        yield grid_dsda, hit
    finally:
        if blocker in sys.meta_path:
            sys.meta_path.remove(blocker)
        sys.path.remove(str(package))
        for name in SEALED_MODULES:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def pin_cpu(choice, package):
    if not hasattr(os, "sched_setaffinity"):
        return dict(mode="not_pinned", reason="CPU affinity unsupported")
    if choice == "none":
        return dict(mode="not_pinned", effective_cpus=sorted(os.sched_getaffinity(0)))
    selection = None
    if choice == "auto":
        select = load_module("sealed_select_dsda_cpu", package / "select_dsda_cpu.py").select
        selection = select(preferred=-1)
        if selection["selected_cpu"] is None or not selection.get(
            "physical_core_observed_idle"
        ):
            raise RuntimeError("No fully idle physical core observed; not started")
        cpu = selection["selected_cpu"]
    else:
        cpu = int(choice)
    os.sched_setaffinity(0, {cpu})
    effective = sorted(os.sched_getaffinity(0))
    if effective != [cpu]:
        raise RuntimeError("Could not pin the selected CPU")
    return dict(
        mode="observed_idle_physical_core_then_pinned" if selection else "pinned",
        cpu=cpu,
        effective_cpus=effective,
        selection=selection,
        exclusive_reservation=False,
    )


def make_oracle(core, job, package, directory):
    """The archived StrictOracle: stored responses only, no fallback evaluation."""
    s = job["spec"]
    raw = read_csv(package / f"inputs/process/{s['case']}_oracle.csv")
    full = {
        tuple(json.loads(r["point"])): r
        for r in read_csv(package / f"inputs/process/{s['case']}_full.csv")
    }
    lookup = {tuple(json.loads(r["point"])): {**r, "csv_line": i} for i, r in enumerate(raw, 2)}

    class StrictOracle(core.Oracle):
        def __call__(self, p):
            point = tuple(int(round(float(x))) for x in p)
            if point not in full:
                raise core.MissingEvaluation(f"Missing stored response for {point}")
            stored = full[point]
            if point not in lookup and (
                stored["accepted"] != "False" or core.logical_allowed(s["case"], point)
            ):
                raise core.MissingEvaluation(f"Missing historical response for {point}")
            return super().__call__(p)

    return StrictOracle(s, lookup, directory), full


def single_descent(core, dsda, job, oracle, directory):
    """The published protocol, with the adopted absolute improvement threshold."""
    original = dsda.dsda_from_csv

    def with_tolerance(*args, **kwargs):
        return original(*args, improvement_abs_tol=IMPROVEMENT_ABS_TOL, **kwargs)

    dsda.dsda_from_csv = with_tolerance
    try:
        core.optimize(job["spec"], oracle, {}, directory)
    finally:
        dsda.dsda_from_csv = original


def multistart(dsda, job, oracle, directory, descents, random_restarts):
    """Descend from the ranked shared starts, then optionally from random restarts."""
    import numpy as np

    s = job["spec"]
    random.seed(s["seed"])
    np.random.seed(s["seed"])
    domain = dict.fromkeys(
        itertools.product(*(range(lo, hi + 1) for lo, hi in zip(s["lower"], s["upper"])))
    )
    write_json(
        directory / "actual_settings.json",
        dict(
            **s["settings"],
            improvement_abs_tol=IMPROVEMENT_ABS_TOL,
            start_ranking="method value of the shared starts; unaccepted last; ties keep shared order",
            random_restarts=random_restarts,
            restart_rng=f"numpy default_rng([{RESTART_STREAM}, seed]) over unvisited box points"
            if random_restarts
            else None,
        ),
    )
    values = [oracle(p) for p in s["starts"]]
    rank = sorted(
        range(len(values)), key=lambda i: values[i] if math.isfinite(values[i]) else math.inf
    )
    queue = [(tuple(s["starts"][i]), values[i], f"shared_start_rank_{r + 1}") for r, i in enumerate(rank)]
    rng = np.random.default_rng([RESTART_STREAM, s["seed"]])
    while oracle.call_count < s["budget"]:
        if queue:
            start, value, origin = queue.pop(0)
        elif random_restarts:
            seen = {tuple(e["point"]) for e in oracle.events}
            unseen = [p for p in domain if p not in seen]
            if not unseen:
                break
            start, value, origin = unseen[int(rng.integers(len(unseen)))], None, "uniform_unvisited_restart"
        else:
            break
        record = dict(origin=origin, start=list(start), callbacks_before=oracle.call_count)
        descents.append(record)
        result = dsda.dsda_from_csv(
            csv_path="IPOPT_lookup",
            start_point=start,
            start_value=value,
            grid=domain,
            tracked_objective=oracle,
            max_points_explored=s["budget"] - oracle.call_count,
            verbose=True,
            improvement_abs_tol=IMPROVEMENT_ABS_TOL,
            **s["settings"],
        )
        record.update(
            callbacks_after=oracle.call_count,
            endpoint=list(result["best_point"]),
            endpoint_value=finite_or_none(result["best_value"]),
            stop_reason=result["stop_reason"] or "no_improving_neighbor",
        )


def execute(job, variant, package, runs, dsda, hit):
    s = job["spec"]
    directory = runs / f"{s['job_id']}__{variant}"
    directory.mkdir(parents=True)
    descents, status, error = [], "completed", None
    core, oracle, full = None, None, {}
    # Timing scope matches the archived rerun: module load, table reads, and search.
    started = time.perf_counter()
    try:
        core = load_module(f"frozen_{job['cohort']}", package / "frozen" / f"{job['cohort']}.py")
        oracle, full = make_oracle(core, job, package, directory)
        with (directory / "search.log").open("w") as log, redirect_stdout(log):
            try:
                if variant == "single":
                    single_descent(core, dsda, job, oracle, directory)
                else:
                    multistart(dsda, job, oracle, directory, descents, variant == "ranked_random")
            except core.BudgetStop:
                status = "budget_completed"
    except Exception as exc:
        status = "missing_lookup" if type(exc).__name__ == "MissingEvaluation" else "execution_failed"
        error = traceback.format_exc()
    elapsed = time.perf_counter() - started
    events = oracle.events if oracle else []
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    ok = status in ("completed", "budget_completed")
    success = bool(ok and best and hit(best["raw_objective"], job["target"]))
    costs = [float(full[tuple(e["point"])]["total_wall_s"]) for e in events]
    lookup_s = math.fsum(e["lookup_wall_s"] for e in events)
    prep_s = float(job["baseline"]["prep_s"])
    if descents and "callbacks_after" not in descents[-1]:
        descents[-1].update(callbacks_after=len(events), stop_reason="budget_stop")
    result = dict(
        spec=s,
        variant=variant,
        status=status,
        error=error,
        category="execution_failed"
        if not ok or best is None
        else "target_reached"
        if success
        else "target_not_reached",
        hit=success,
        target=job["target"],
        best_objective=best["raw_objective"] if best else None,
        best_point=best["point"] if best else None,
        evaluations=len(events),
        unused_budget=s["budget"] - len(events),
        first_hit=next(
            (e["index"] for e in accepted if hit(e["raw_objective"], job["target"])), None
        )
        if success
        else None,
        descents=descents if variant != "single" else None,
        search_s=elapsed,
        lookup_s=lookup_s,
        retained_search_s=elapsed - lookup_s,
        point_cost_s=math.fsum(costs),
        prep_s=prep_s,
        completion_s=elapsed - lookup_s + math.fsum(costs) + prep_s,
        improvement_abs_tol=IMPROVEMENT_ABS_TOL,
        process_nlp_calls=0,
        effective_cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
    )
    write_json(directory / "result.json", result)
    return result, events


def replay_check(job, result, events, archived_runs):
    """The single protocol must reproduce the archived rerun exactly."""
    member = archived_runs / job["spec"]["job_id"]
    old = read_json(member / "result.json")
    old_points = [json.loads(line)["point"] for line in (member / "callbacks.jsonl").read_text().splitlines()]
    checks = dict(
        points=[e["point"] for e in events] == old_points,
        evaluations=result["evaluations"] == old["evaluations"],
        best_objective=result["best_objective"] == old["best_objective"],
        hit=result["hit"] == old["hit"],
        first_hit=result["first_hit"] == old["first_hit"],
        category=result["category"] == old["category"],
    )
    return dict(job_id=job["spec"]["job_id"], passed=all(checks.values()), **checks)


def summarize(results):
    rows, conditions = [], {}
    for r in results:
        s = r["spec"]
        rows.append(
            dict(
                case=s["case"],
                budget=s["budget"],
                seed=s["seed"],
                variant=r["variant"],
                status=r["status"],
                hit=r["hit"],
                best_objective=r["best_objective"],
                evaluations=r["evaluations"],
                unused_budget=r["unused_budget"],
                first_hit=r["first_hit"],
                descents=len(r["descents"]) if r["descents"] is not None else 1,
                retained_search_s=r["retained_search_s"],
                lookup_s=r["lookup_s"],
                point_cost_s=r["point_cost_s"],
                prep_s=r["prep_s"],
                completion_s=r["completion_s"],
            )
        )
        conditions.setdefault((s["case"], s["budget"], r["variant"]), []).append(r)
    summary = []
    for (case, budget, variant), group in sorted(conditions.items()):
        searches = [g["retained_search_s"] for g in group]
        completions = [g["completion_s"] for g in group]
        summary.append(
            dict(
                case=case,
                budget=budget,
                variant=variant,
                runs=len(group),
                hits=sum(g["hit"] for g in group),
                median_evaluations=statistics.median(g["evaluations"] for g in group),
                runs_using_full_budget=sum(g["unused_budget"] == 0 for g in group),
                median_search_s=quantile(searches, 0.5),
                q25_search_s=quantile(searches, 0.25),
                q75_search_s=quantile(searches, 0.75),
                median_completion_s=quantile(completions, 0.5),
                q25_completion_s=quantile(completions, 0.25),
                q75_completion_s=quantile(completions, 0.75),
            )
        )
    return rows, summary


CASE_ORDER = ["column", "cstr_5", "cstr_10", "cstr_15", "cstr_20", "cstr_25", "cstr_30", "small_batch", "dynamic"]
CASE_NAME = {"column": "Column", "small_batch": "Small Batch", "dynamic": "Dynamic",
             **{f"cstr_{n}": f"CSTR{n}" for n in (5, 10, 15, 20, 25, 30)}}


def number(x):
    return f"{x:.1f}" if x != int(x) else str(int(x))


def restart_table(summary):
    """Supplementary table rows: hits, full-budget runs, and median evaluations per variant."""
    cells = {(r["case"], r["budget"], r["variant"]): r for r in summary}
    lines = [
        r"\begin{tabular}{lrcccccccc}\toprule",
        r" & & \multicolumn{3}{c}{Target hits} & \multicolumn{2}{c}{Full-budget runs}"
        r" & \multicolumn{3}{c}{Median evaluations}\\"
        r"\cmidrule(lr){3-5}\cmidrule(lr){6-7}\cmidrule(l){8-10}",
        r"Case & \(B\) & S & R & RR & S & R & S & R & RR\\\midrule",
    ]
    for case, budget in sorted({(c, b) for c, b, _ in cells}, key=lambda k: (CASE_ORDER.index(k[0]), k[1])):
        s, r, rr = (cells[case, budget, v] for v in VARIANTS)
        lines.append(
            rf"\texttt{{{CASE_NAME[case]}}} & {budget} & {s['hits']} & {r['hits']} & {rr['hits']} & "
            f"{s['runs_using_full_budget']} & {r['runs_using_full_budget']} & "
            f"{number(s['median_evaluations'])} & {number(r['median_evaluations'])} & "
            rf"{number(rr['median_evaluations'])} \\"
        )
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def provenance(args, cpu, started, finished):
    def git(*a):
        out = subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else None

    versions = {}
    for name in ("numpy", "pandas", "scipy"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return dict(
        command=sys.argv,
        arguments={k: str(v) for k, v in vars(args).items()},
        started_utc=started,
        finished_utc=finished,
        archive=str(Path(args.archive).resolve().relative_to(REPO))
        if Path(args.archive).resolve().is_relative_to(REPO)
        else str(args.archive),
        archive_sha256=ARCHIVE_SHA256,
        script_sha256=sha(HERE),
        git_head=git("rev-parse", "HEAD"),
        git_status=git("status", "--porcelain"),
        host=platform.node(),
        platform=platform.platform(),
        python=platform.python_version(),
        versions=versions,
        threads=THREADS,
        cpu=cpu,
        improvement_abs_tol=IMPROVEMENT_ABS_TOL,
        restart_stream=RESTART_STREAM,
        variants=list(args.variants),
        process_nlp_calls=0,
    )


def run(args):
    started = datetime.now(timezone.utc).isoformat()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    with tempfile.TemporaryDirectory() as scratch:
        package, archived_runs = extract_package(args.archive, scratch)
        cpu = pin_cpu(args.cpu, package)
        jobs = [j for j in read_json(package / "inputs/jobs.json") if j["spec"]["scope"] == "process"]
        if len(jobs) != 140:
            raise ValueError(f"Expected 140 process jobs, found {len(jobs)}")
        if args.jobs:
            wanted = set(args.jobs)
            jobs = [j for j in jobs if j["spec"]["job_id"] in wanted]
            if len(jobs) != len(wanted):
                raise ValueError("Unknown job identifier requested")
        runs = output / "runs"
        runs.mkdir(parents=True)
        results, replay, prefix_checks = [], [], []
        with sealed_modules(package) as (dsda, hit):
            for job in jobs:
                by_variant = {}
                for variant in args.variants:
                    result, events = execute(job, variant, package, runs, dsda, hit)
                    results.append(result)
                    by_variant[variant] = (result, events)
                    print(
                        f"{job['spec']['job_id']:<28} {variant:<14} {result['status']:<17} "
                        f"hit={result['hit']!s:<5} evals={result['evaluations']}/{job['spec']['budget']}",
                        flush=True,
                    )
                if "single" not in by_variant:
                    continue
                single_result, single_events = by_variant["single"]
                replay.append(replay_check(job, single_result, single_events, archived_runs))
                single_points = [e["point"] for e in single_events]
                for variant in ("ranked", "ranked_random"):
                    if variant in by_variant:
                        points = [e["point"] for e in by_variant[variant][1]]
                        prefix_checks.append(
                            dict(
                                job_id=job["spec"]["job_id"],
                                variant=variant,
                                passed=points[: len(single_points)] == single_points,
                            )
                        )
        rows, summary = summarize(results)
        write_csv(output / "runs.csv", rows)
        write_csv(output / "condition_summary.csv", summary)
        if set(args.variants) == set(VARIANTS) and not args.jobs:
            (output / "restart_table.tex").write_text(restart_table(summary))
        failures = [r["spec"]["job_id"] + "__" + r["variant"] for r in results if r["category"] == "execution_failed"]
        checks = dict(
            replay_passed=all(r["passed"] for r in replay) if replay else None,
            replay_failures=[r for r in replay if not r["passed"]],
            first_descent_matches_single=all(p["passed"] for p in prefix_checks) if prefix_checks else None,
            prefix_failures=[p for p in prefix_checks if not p["passed"]],
            execution_failures=failures,
        )
        write_json(output / "checks.json", dict(**checks, replay=replay, prefix=prefix_checks))
        write_json(
            output / "manifest.json",
            provenance(args, cpu, started, datetime.now(timezone.utc).isoformat()),
        )
    passed = checks["replay_passed"] is not False and checks["first_descent_matches_single"] is not False and not failures
    print("CHECKS", "PASSED" if passed else "FAILED", json.dumps({k: v for k, v in checks.items() if not isinstance(v, list)}))
    if not args.no_zip:
        archive = shutil.make_archive(str(output), "zip", output.parent, output.name)
        print("RETURN_ARCHIVE", archive)
        print("SCP_RETURN_ARCHIVE", f"{platform.node()}:{archive}")
    return 0 if passed else 1


def main(argv=None):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", default=str(ARCHIVE))
    parser.add_argument(
        "--output", default=str(REPO / f"results/dsda_process_multistart_{stamp}_{os.getpid()}")
    )
    parser.add_argument("--cpu", default="auto", help="'auto' (observed idle core), an integer, or 'none'")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    parser.add_argument("--jobs", nargs="*", help="Restrict to these job identifiers (for testing)")
    parser.add_argument("--no-zip", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
