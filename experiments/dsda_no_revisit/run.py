"""D-SDA that never evaluates a configuration twice, replayed from stored responses.

The published D-SDA runs evaluated an already explored neighbor or line-search
point again and charged it to the budget.  The original D-SDA (``global_evaluated``)
and the Pyomo LD-SDA (``explored_point_set``) never do.  The repository
``grid_dsda.py`` now reuses the stored value of an explored configuration without
charging it.  This experiment reruns every D-SDA job of the manuscript with it:

  grid           1,050 Grid runs: ranked shared starts, common target stop
  single         140 process runs: one descent from the best accepted start
  ranked         140 process runs: descents from the ranked shared starts
  ranked_random  140 process runs: then from uniformly drawn unvisited configurations

Each job is also replayed with ``reevaluate_explored=True``, which must reproduce
the published run exactly, so the no-revisit rule is the only change.  Responses
and point costs come from stored tables; no NLP solver or process model is run.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

import importlib.metadata  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "dsda_process_multistart", REPO / "experiments/dsda_process_multistart/run.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)  # sets the one-thread environment

import argparse  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import platform  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import zipfile  # noqa: E402

GRID_ARCHIVE = REPO / "results/archives/dsda_grid_target_stop_20261028_032943_2346732.zip"
GRID_PREFIX = "dsda_grid_target_stop_20261028_032943_2346732/runs/"
GRID_COSTS = REPO / "results/grid_gdp_20261009/raw/point_timings.csv"
GRID_COSTS_SHA256 = "2490d8f8de368d9b54d6cd3d9082ace5c74dfa2ebb84fd266b0488a43a7fcd0f"
VARIANTS = ("grid", "single", "ranked", "ranked_random")
TOL = ms.IMPROVEMENT_ABS_TOL


def first_occurrences(points):
    seen, out = set(), []
    for p in map(tuple, points):
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def import_fixed_dsda():
    """The repository grid_dsda.py, never a sealed copy."""
    import numpy  # noqa: F401  Load numerical runtime before the import guard.
    import pandas  # noqa: F401
    import grid_dsda
    import dsda_protocol

    if Path(grid_dsda.__file__).resolve() != REPO / "grid_dsda.py":
        raise RuntimeError(f"Unexpected grid_dsda: {grid_dsda.__file__}")
    if "reevaluate_explored" not in grid_dsda.dsda_from_csv.__code__.co_varnames:
        raise RuntimeError("grid_dsda.py lacks the no-revisit rule")
    return grid_dsda, dsda_protocol


def grid_costs():
    if ms.sha(GRID_COSTS) != GRID_COSTS_SHA256:
        raise ValueError("Grid point-cost table changed")
    return {(r["grid_name"], tuple(json.loads(r["point"]))): float(r["point_wall_s"])
            for r in ms.read_csv(GRID_COSTS)}


def run_grid(dsda, protocol, hit, job, package, reevaluate):
    """Grid protocol of the published runs: ranked shared starts and common target stop."""
    s = job["spec"]
    path = package / "inputs/grids" / f"{s['case']}.csv"
    _, grid = dsda.load_grid_csv(path)
    events = []

    class Recording(protocol.ObservedObjective):
        def __call__(self, p):
            value = super().__call__(p)
            events.append(dict(index=self.call_count, point=list(p), raw_objective=value,
                               accepted=True, lookup_wall_s=self.wall_times[-1]))
            return value

    import numpy as np

    random.seed(s["seed"])
    np.random.seed(s["seed"])
    result = dsda.run_dsda_from_best_starting_points(
        path, s["starts"], target_value=job["target"], verbose=True, max_points_explored=s["budget"],
        improvement_abs_tol=TOL, target_stop=hit, grid=grid,
        tracked_objective=Recording(dsda.make_grid_objective(grid)), reevaluate_explored=reevaluate,
        **s["settings"])
    return events, dict(termination=result["stop_reason"] or "all_ranked_starts_exhausted",
                        descent_count=len(result["runs"]))


def run_process(dsda, job, variant, package, directory, reevaluate):
    """Process protocols on the archived lookup oracle; unaccepted responses return 1e6."""
    import numpy as np

    s = job["spec"]
    core = ms.load_module(f"frozen_{job['cohort']}", package / "frozen" / f"{job['cohort']}.py")
    oracle, full = ms.make_oracle(core, job, package, directory)
    random.seed(s["seed"])
    np.random.seed(s["seed"])
    domain = dict.fromkeys(itertools.product(*(range(lo, hi + 1) for lo, hi in zip(s["lower"], s["upper"]))))
    descents, status = [], "completed"

    def descend(start, value, origin):
        record = dict(origin=origin, start=list(start), callbacks_before=oracle.call_count)
        descents.append(record)
        result = dsda.dsda_from_csv(
            csv_path="IPOPT_lookup", start_point=start, start_value=value, grid=domain, tracked_objective=oracle,
            max_points_explored=s["budget"] - oracle.call_count, verbose=True, improvement_abs_tol=TOL,
            known_values=known, reevaluate_explored=reevaluate, **s["settings"])
        record.update(callbacks_after=oracle.call_count, endpoint=list(result["best_point"]),
                      endpoint_value=ms.finite_or_none(result["best_value"]),
                      stop_reason=result["stop_reason"] or "no_improving_neighbor")

    try:
        values = [oracle(p) for p in s["starts"]]
        known = dict(zip(map(tuple, s["starts"]), values))
        if variant == "single":
            accepted = [e for e in oracle.events if e["accepted"]]
            if not accepted:
                raise RuntimeError("No accepted initial point; no reseeding")
            best = min(accepted, key=lambda e: e["raw_objective"])
            descend(tuple(best["point"]), best["raw_objective"], "best_accepted_start")
        else:
            rank = sorted(range(3), key=lambda i: values[i] if math.isfinite(values[i]) else math.inf)
            queue = [(tuple(s["starts"][i]), values[i], f"shared_start_rank_{r + 1}") for r, i in enumerate(rank)]
            rng = np.random.default_rng([ms.RESTART_STREAM, s["seed"]])
            while oracle.call_count < s["budget"]:
                if queue:
                    descend(*queue.pop(0))
                elif variant == "ranked_random":
                    seen = {tuple(e["point"]) for e in oracle.events}
                    unseen = [p for p in domain if p not in seen]
                    if not unseen:
                        break
                    descend(unseen[int(rng.integers(len(unseen)))], None, "uniform_unvisited_restart")
                else:
                    break
    except core.BudgetStop:
        status = "budget_completed"
    if descents and "callbacks_after" not in descents[-1]:
        descents[-1].update(callbacks_after=oracle.call_count, stop_reason="budget_stop")
    return oracle.events, full, status, descents


def execute(job, variant, package, runs, dsda, protocol, hit, costs, reevaluate=False):
    s = job["spec"]
    directory = runs / f"{s['job_id']}__{variant}"
    directory.mkdir(parents=True)
    events, descents, status, error, extra, full = [], [], "completed", None, {}, {}
    started = time.perf_counter()
    try:
        with (directory / "search.log").open("w") as log, redirect_stdout(log):
            if variant == "grid":
                events, extra = run_grid(dsda, protocol, hit, job, package, reevaluate)
            else:
                events, full, status, descents = run_process(dsda, job, variant, package, directory, reevaluate)
    except Exception as exc:
        status = "missing_lookup" if type(exc).__name__ in ("MissingEvaluation", "KeyError") else "execution_failed"
        error = traceback.format_exc()
    elapsed = time.perf_counter() - started
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    ok = status in ("completed", "budget_completed")
    success = bool(ok and best and hit(best["raw_objective"], job["target"]))
    if variant == "grid":
        point_costs = [costs[s["case"], tuple(e["point"])] for e in events]
        prep_s = 0.0
    else:
        point_costs = [float(full[tuple(e["point"])]["total_wall_s"]) for e in events]
        prep_s = float(job["baseline"]["prep_s"])
    lookup_s = math.fsum(e["lookup_wall_s"] for e in events)
    points = [tuple(e["point"]) for e in events]
    result = dict(
        spec=s, variant=variant, reevaluate_explored=reevaluate, status=status, error=error,
        category="execution_failed" if not ok or best is None else "target_reached" if success else "target_not_reached",
        hit=success, target=job["target"],
        best_objective=best["raw_objective"] if best else None, best_point=best["point"] if best else None,
        evaluations=len(events), distinct_evaluations=len(set(points)), unused_budget=s["budget"] - len(events),
        first_hit=next((e["index"] for e in accepted if hit(e["raw_objective"], job["target"])), None)
        if success else None,
        descents=descents or None, **(extra or dict(descent_count=len(descents))),
        search_s=elapsed, lookup_s=lookup_s, retained_search_s=elapsed - lookup_s,
        point_cost_s=math.fsum(point_costs), prep_s=prep_s,
        completion_s=elapsed - lookup_s + math.fsum(point_costs) + prep_s,
        improvement_abs_tol=TOL, process_nlp_calls=0,
        effective_cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
    )
    ms.write_json(directory / "result.json", result)
    with (directory / "callbacks.jsonl").open("w") as f:
        for e in events:
            f.write(json.dumps({k: e[k] for k in ("index", "point", "accepted", "raw_objective", "lookup_wall_s")}) + "\n")
    return result, points


def published_points(job, archived_runs, grid_zip):
    s = job["spec"]
    if s["scope"] == "grid":
        text = grid_zip.read(GRID_PREFIX + s["job_id"] + "/callbacks.jsonl").decode()
        result = json.loads(grid_zip.read(GRID_PREFIX + s["job_id"] + "/result.json"))
    else:
        member = archived_runs / s["job_id"]
        text = (member / "callbacks.jsonl").read_text()
        result = ms.read_json(member / "result.json")
    return [tuple(json.loads(line)["point"]) for line in text.splitlines()], result


def summarize(results):
    rows, groups = [], {}
    for r in results:
        s = r["spec"]
        rows.append(dict(scope=s["scope"], case=s["case"], budget=s["budget"], seed=s["seed"], variant=r["variant"],
                         status=r["status"], hit=r["hit"], best_objective=r["best_objective"],
                         evaluations=r["evaluations"], distinct_evaluations=r["distinct_evaluations"],
                         unused_budget=r["unused_budget"], first_hit=r["first_hit"],
                         descents=r["descent_count"],
                         retained_search_s=r["retained_search_s"], lookup_s=r["lookup_s"],
                         point_cost_s=r["point_cost_s"], prep_s=r["prep_s"], completion_s=r["completion_s"]))
        key = ("grid", "all", s["budget"]) if s["scope"] == "grid" else (r["variant"], s["case"], s["budget"])
        groups.setdefault(key, []).append(r)
    summary = []
    for (variant, case, budget), group in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        completions = [g["completion_s"] for g in group]
        summary.append(dict(variant=variant, case=case, budget=budget, runs=len(group),
                            hits=sum(g["hit"] for g in group),
                            median_evaluations=ms.quantile([g["evaluations"] for g in group], 0.5),
                            runs_using_full_budget=sum(g["unused_budget"] == 0 for g in group),
                            median_search_s=ms.quantile([g["retained_search_s"] for g in group], 0.5),
                            median_completion_s=ms.quantile(completions, 0.5),
                            q25_completion_s=ms.quantile(completions, 0.25),
                            q75_completion_s=ms.quantile(completions, 0.75)))
    return rows, summary


def run(args):
    started = datetime.now(timezone.utc).isoformat()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if ms.sha(GRID_ARCHIVE) != (GRID_ARCHIVE.with_suffix(".zip.sha256").read_text().split()[0]):
        raise ValueError("Grid archive hash mismatch")
    with tempfile.TemporaryDirectory() as scratch:
        package, archived_runs = ms.extract_package(args.archive, scratch)
        cpu = ms.pin_cpu(args.cpu, package)
        hit = ms.load_module("sealed_adopted_analysis", package / "adopted_analysis.py").hit
        dsda, protocol = import_fixed_dsda()
        costs = grid_costs()
        jobs = ms.read_json(package / "inputs/jobs.json")
        if len(jobs) != 1190:
            raise ValueError(f"Expected 1,190 D-SDA jobs, found {len(jobs)}")
        if args.jobs:
            wanted = set(args.jobs)
            jobs = [j for j in jobs if j["spec"]["job_id"] in wanted]
            if len(jobs) != len(wanted):
                raise ValueError("Unknown job identifier requested")
        runs, legacy_runs = output / "runs", Path(scratch) / "legacy_runs"
        runs.mkdir(parents=True)
        blocker = ms.SolverBlocker()
        sys.meta_path.insert(0, blocker)
        results, checks = [], []
        try:
            with zipfile.ZipFile(GRID_ARCHIVE) as grid_zip:
                for job in jobs:
                    s = job["spec"]
                    variants = ["grid"] if s["scope"] == "grid" else [v for v in args.variants if v != "grid"]
                    if s["scope"] == "grid" and "grid" not in args.variants:
                        continue
                    published, old = published_points(job, archived_runs, grid_zip)
                    single = None
                    for variant in variants:
                        result, points = execute(job, variant, package, runs, dsda, protocol, hit, costs)
                        results.append(result)
                        check = dict(job_id=s["job_id"], variant=variant,
                                     no_repeats=len(points) == len(set(points)),
                                     ok=result["category"] != "execution_failed")
                        if variant in ("grid", "single"):
                            legacy, legacy_points = execute(job, variant, package, legacy_runs, dsda, protocol, hit,
                                                            costs, reevaluate=True)
                            distinct = first_occurrences(published)
                            check.update(
                                legacy_reproduces_published=legacy_points == published
                                and legacy["best_objective"] == old["best_objective"] and legacy["hit"] == old["hit"],
                                published_distinct_prefix=points[:len(distinct)] == distinct,
                                not_worse=old["best_objective"] is None or (
                                    result["best_objective"] is not None
                                    and result["best_objective"] <= old["best_objective"]),
                                hit_kept=result["hit"] or not old["hit"],
                                published_hit=old["hit"], published_evaluations=len(published),
                                published_repeats=len(published) - len(distinct))
                            single = points if variant == "single" else None
                        elif single is not None:
                            check.update(first_descent_matches_single=points[:len(single)] == single)
                        check["passed"] = all(v for k, v in check.items() if isinstance(v, bool) and k != "published_hit")
                        checks.append(check)
                        print(f"{s['job_id']:<40} {variant:<14} {result['status']:<17} hit={result['hit']!s:<5} "
                              f"evals={result['evaluations']}/{s['budget']} checks={'ok' if check['passed'] else 'FAILED'}",
                              flush=True)
        finally:
            sys.meta_path.remove(blocker)
        rows, summary = summarize(results)
        ms.write_csv(output / "runs.csv", rows)
        ms.write_csv(output / "condition_summary.csv", summary)
        fields = list(dict.fromkeys(k for c in checks for k in c))
        ms.write_csv(output / "checks.csv", [{k: c.get(k) for k in fields} for c in checks])
        failures = [c for c in checks if not c["passed"]]
        ms.write_json(output / "checks.json", dict(passed=not failures, jobs=len(checks), failures=failures))

        def git(*a):
            out = subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)
            return out.stdout.strip() if out.returncode == 0 else None

        versions = {}
        for name in ("numpy", "pandas", "scipy"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        ms.write_json(output / "manifest.json", dict(
            command=sys.argv, started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
            archive_sha256=ms.ARCHIVE_SHA256, grid_archive_sha256=ms.sha(GRID_ARCHIVE),
            grid_costs_sha256=GRID_COSTS_SHA256, script_sha256=ms.sha(HERE),
            grid_dsda_sha256=ms.sha(REPO / "grid_dsda.py"), git_head=git("rev-parse", "HEAD"),
            git_status=git("status", "--porcelain"), host=platform.node(), platform=platform.platform(),
            python=platform.python_version(), versions=versions, threads=ms.THREADS, cpu=cpu,
            improvement_abs_tol=TOL, restart_stream=ms.RESTART_STREAM, variants=list(args.variants),
            process_nlp_calls=0))
    print("CHECKS", "PASSED" if not failures else "FAILED", f"{len(checks) - len(failures)}/{len(checks)} jobs")
    if not args.no_zip:
        archive = shutil.make_archive(str(output), "zip", output.parent, output.name)
        print("RETURN_ARCHIVE", archive)
    return 0 if not failures else 1


def main(argv=None):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", default=str(ms.ARCHIVE))
    parser.add_argument("--output", default=str(REPO / f"results/dsda_no_revisit_{stamp}_{os.getpid()}"))
    parser.add_argument("--cpu", default="auto", help="'auto' (observed idle core), an integer, or 'none'")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    parser.add_argument("--jobs", nargs="*", help="Restrict to these job identifiers (for testing)")
    parser.add_argument("--no-zip", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
