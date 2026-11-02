"""D-SDA with the separable neighborhood on the stored-response benchmarks.

  python experiments/dsda_separable/run.py --output OUT [--cpu auto]

The D-SDA runs of the manuscript (results/dsda_no_revisit_20261031) use the unit
L-infinity neighborhood, whose 3**d - 1 neighbors are 8 in two dimensions and 26 in
three.  The catalytic column, with six external variables, uses the separable
neighborhood (one external variable changed by +-1, 2*d neighbors), because its L-infinity
neighborhood has 728 configurations.  This experiment repeats the 1,050 Grid runs and the
140 single-descent process runs with the separable neighborhood and every other setting
unchanged, through the harness of experiments/dsda_no_revisit, and compares each run with
its L-infinity counterpart.  Responses and point costs come from stored tables; no NLP
solver or process model is run.
"""

import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
_spec = importlib.util.spec_from_file_location("dsda_no_revisit", REPO / "experiments/dsda_no_revisit/run.py")
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)  # sets the one-thread environment
ms = nr.ms
LINF_RUNS = REPO / "results/dsda_no_revisit_20261031/runs.csv"


def separable(job):
    job = copy.deepcopy(job)
    job["spec"]["settings"] = {**job["spec"]["settings"], "diagonal": False}
    return job


def compare(rows):
    """Pair every separable run with the L-infinity run of the same job."""
    linf = {(r["scope"], r["case"], r["budget"], r["seed"]): r for r in ms.read_csv(LINF_RUNS)
            if r["variant"] in ("grid", "single")}
    paired, conditions = [], {}
    for r in rows:
        key = (r["scope"], r["case"], str(r["budget"]), str(r["seed"]))
        old = linf[key]
        both = dict(scope=r["scope"], case=r["case"], budget=r["budget"], seed=r["seed"],
                    hit_linf=old["hit"] == "True", hit_separable=bool(r["hit"]),
                    best_linf=old["best_objective"], best_separable=r["best_objective"],
                    evaluations_linf=int(old["evaluations"]), evaluations_separable=r["evaluations"],
                    completion_linf_s=float(old["completion_s"]), completion_separable_s=r["completion_s"])
        paired.append(both)
        group = ("grid", "all", r["budget"]) if r["scope"] == "grid" else ("process", r["case"], r["budget"])
        conditions.setdefault(group, []).append(both)
    summary = []
    for (scope, case, budget), group in sorted(conditions.items()):
        summary.append(dict(
            scope=scope, case=case, budget=budget, runs=len(group),
            hits_linf=sum(g["hit_linf"] for g in group), hits_separable=sum(g["hit_separable"] for g in group),
            separable_only=sum(g["hit_separable"] and not g["hit_linf"] for g in group),
            linf_only=sum(g["hit_linf"] and not g["hit_separable"] for g in group),
            median_evaluations_linf=ms.quantile([g["evaluations_linf"] for g in group], 0.5),
            median_evaluations_separable=ms.quantile([g["evaluations_separable"] for g in group], 0.5),
            median_completion_linf_s=ms.quantile([g["completion_linf_s"] for g in group], 0.5),
            median_completion_separable_s=ms.quantile([g["completion_separable_s"] for g in group], 0.5)))
    return paired, summary


def run(args):
    started = datetime.now(timezone.utc).isoformat()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    with tempfile.TemporaryDirectory() as scratch:
        package, _ = ms.extract_package(ms.ARCHIVE, scratch)
        cpu = ms.pin_cpu(args.cpu, package)
        hit = ms.load_module("sealed_adopted_analysis", package / "adopted_analysis.py").hit
        dsda, protocol = nr.import_fixed_dsda()
        costs = nr.grid_costs()
        jobs = ms.read_json(package / "inputs/jobs.json")
        if len(jobs) != 1190:
            raise ValueError(f"Expected 1,190 D-SDA jobs, found {len(jobs)}")
        if args.jobs:
            jobs = [j for j in jobs if j["spec"]["job_id"] in set(args.jobs)]
        runs = output / "runs"
        runs.mkdir(parents=True)
        blocker = ms.SolverBlocker()
        sys.meta_path.insert(0, blocker)
        results, checks = [], []
        try:
            for job in map(separable, jobs):
                s = job["spec"]
                variant = "grid" if s["scope"] == "grid" else "single"
                result, points = nr.execute(job, variant, package, runs, dsda, protocol, hit, costs)
                results.append(result)
                check = dict(job_id=s["job_id"], variant=variant, separable=s["settings"]["diagonal"] is False,
                             no_repeats=len(points) == len(set(points)), ok=result["category"] != "execution_failed")
                check["passed"] = all(v for k, v in check.items() if isinstance(v, bool))
                checks.append(check)
                print(f"{s['job_id']:<40} {variant:<7} {result['status']:<17} hit={result['hit']!s:<5} "
                      f"evals={result['evaluations']}/{s['budget']} checks={'ok' if check['passed'] else 'FAILED'}",
                      flush=True)
        finally:
            sys.meta_path.remove(blocker)
    rows, summary = nr.summarize(results)
    ms.write_csv(output / "runs.csv", rows)
    ms.write_csv(output / "condition_summary.csv", summary)
    if not args.jobs:
        paired, comparison = compare(rows)
        ms.write_csv(output / "paired_runs.csv", paired)
        ms.write_csv(output / "comparison.csv", comparison)
    failures = [c for c in checks if not c["passed"]]
    ms.write_json(output / "checks.json", dict(passed=not failures, jobs=len(checks), failures=failures))

    def git(*a):
        return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()

    ms.write_json(output / "manifest.json", dict(
        started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(), head=git("rev-parse", "HEAD"),
        dirty=bool(git("status", "--porcelain", "--untracked-files=no")), host=platform.node(),
        python=sys.version.split()[0], cpu=cpu, archive=str(ms.ARCHIVE.relative_to(REPO)),
        archive_sha256=ms.sha(ms.ARCHIVE), neighborhood="separable", jobs=len(checks)))
    if not args.no_zip:
        with zipfile.ZipFile(output.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(output.rglob("*")):
                z.write(path, path.relative_to(output.parent))
    print(f"{len(checks)} runs, checks {'passed' if not failures else 'FAILED'}; output {output}")
    return 0 if not failures else 1


def main(argv=None):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default=str(REPO / f"results/dsda_separable_{stamp}_{os.getpid()}"))
    parser.add_argument("--cpu", default="auto", help="'auto' (observed idle core), an integer, or 'none'")
    parser.add_argument("--jobs", nargs="*", help="Restrict to these job identifiers (for testing)")
    parser.add_argument("--no-zip", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
