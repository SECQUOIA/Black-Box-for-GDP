"""NOMAD and MISO on the stored Grid and process responses used by the published comparison.

Ploskas and Sahinidis (2022) identify NOMAD and MISO as the strongest mixed-integer
DFO solvers in their comparison.  This runner applies them to the same 1,050 Grid
and 140 process jobs as the published methods, with the same three shared initial
configurations, budgets, seeds, target rule, and point-cost accounting.

  nomad    NOMAD 4 (MADS) through PyNomadBBO, integer variables, started from the
           best shared initial configuration
  miso     MISO (CPTV of Mueller, 2016) as implemented by soogo.cptv, with the RBF
           model warm-started on the three shared initial configurations
  uniform  solver-free check of the lookup harness: uniform sampling without
           replacement after the shared starts

Responses come from the sealed input package of the adopted D-SDA rerun and point
costs from the stored measurements; no NLP solver or process model is invoked.
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
from contextlib import contextmanager  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
import importlib.metadata  # noqa: E402
import importlib.util  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
from pathlib import Path  # noqa: E402
import platform  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
GRID_COSTS = REPO / "results/grid_gdp_20261009/raw/point_timings.csv"
GRID_COSTS_SHA256 = "2490d8f8de368d9b54d6cd3d9082ace5c74dfa2ebb84fd266b0488a43a7fcd0f"
COVERAGE = REPO / "results/dsda_publication_20261028/tables/configuration_coverage.csv"
PUBLISHED = REPO / "results/dsda_publication_20261028/tables/run_records.csv"
PUBLISHED_METHODS = ["dsda", "rbfopt_msrsm_genetic", "bam", "fmqa_sa", "uniform_without_replacement"]
METHODS = ("nomad", "miso", "uniform")
PENALTY = 1e6
UNIFORM_STREAM = 20261031
NOMAD_EXTRA = []  # set from --nomad-param before workers fork


def load_shared():
    """Reuse the archive extraction and CPU pinning of the D-SDA restart experiment."""
    path = REPO / "experiments/dsda_process_multistart/run.py"
    spec = importlib.util.spec_from_file_location("dsda_process_multistart_shared", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shared = load_shared()


@contextmanager
def capture_native_output(path):
    """Send C/C++ writes to file descriptors 1 and 2 into the run log."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    with open(path, "a") as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        try:
            yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            for fd in saved:
                os.close(fd)


class Lookup:
    """Charged objective evaluations against stored responses; never raises in a callback."""

    def __init__(self, job, responses, costs, nlp_status, stream):
        self.spec = job["spec"]
        self.responses, self.costs, self.nlp_status = responses, costs, nlp_status
        self.events, self.overruns, self.invalid = [], 0, []
        self.stream = stream

    @property
    def budget(self):
        return self.spec["budget"]

    def point(self, coordinates):
        return tuple(int(round(float(x))) for x in coordinates)

    def evaluate(self, coordinates, origin):
        started = time.perf_counter()
        point = self.point(coordinates)
        if point not in self.responses:
            self.invalid.append(list(point))
            return PENALTY
        if len(self.events) >= self.budget:
            self.overruns += 1
            return PENALTY
        accepted, objective = self.responses[point]
        value = objective if accepted else PENALTY
        self.events.append(dict(
            index=len(self.events) + 1,
            point=list(point),
            origin=origin,
            accepted=accepted,
            raw_objective=objective if accepted else None,
            method_value=value,
            nlp_solve=self.nlp_status(point),
            point_cost_s=self.costs[point],
            lookup_wall_s=time.perf_counter() - started,
        ))
        with open(self.stream, "a") as f:
            f.write(json.dumps(self.events[-1]) + "\n")
        return value


def shared_starts(lookup):
    values = [lookup.evaluate(p, "shared_start") for p in lookup.spec["starts"]]
    order = sorted(range(len(values)), key=lambda i: values[i])
    return values, order


def run_uniform(lookup, seed, log):
    import numpy as np

    shared_starts(lookup)
    rng = np.random.default_rng([UNIFORM_STREAM, seed])
    s = lookup.spec
    domain = list(itertools.product(*(range(lo, hi + 1) for lo, hi in zip(s["lower"], s["upper"]))))
    while len(lookup.events) < lookup.budget:
        seen = {tuple(e["point"]) for e in lookup.events}
        unseen = [p for p in domain if p not in seen]
        if not unseen:
            break
        lookup.evaluate(unseen[int(rng.integers(len(unseen)))], "uniform")
    return dict(stop_reason="budget" if len(lookup.events) == lookup.budget else "domain_exhausted")


def run_nomad(lookup, seed, log):
    import PyNomad

    values, order = shared_starts(lookup)
    s = lookup.spec
    x0 = list(s["starts"][order[0]])
    replay = {"pending": True}

    def blackbox(x):
        try:
            point = [x.get_coord(i) for i in range(x.size())]
            if replay["pending"] and lookup.point(point) == tuple(x0):
                # The best shared start was already charged; NOMAD receives its stored value.
                replay["pending"] = False
                value = values[order[0]]
            else:
                value = lookup.evaluate(point, "nomad")
            x.setBBO(repr(float(value)).encode("UTF-8"))
            return 1
        except Exception:  # noqa: BLE001  The native callback cannot propagate exceptions.
            traceback.print_exc()
            return 0

    dimension = len(s["lower"])
    params = [
        "BB_OUTPUT_TYPE OBJ",
        "BB_INPUT_TYPE ( " + " ".join(["I"] * dimension) + " )",
        f"MAX_BB_EVAL {s['budget'] - 3 + 1}",
        f"SEED {seed}",
        "DISPLAY_DEGREE 0",
        *NOMAD_EXTRA,
    ]
    with capture_native_output(log):
        result = PyNomad.optimize(blackbox, x0, list(map(float, s["lower"])), list(map(float, s["upper"])), params)
    return dict(params=params, x0=x0, x0_replayed=not replay["pending"],
                **{k: result[k] for k in ("nb_evals", "run_flag", "stop_reason") if k in result})


def integer_dds(n, bounds, probability, mu, sigma_ref, rng):
    """Dynamically dimensioned search perturbations on an integer lattice.

    Each candidate perturbs every coordinate with the given probability (at least
    one), drawing from a normal distribution centred at mu and truncated to
    [lower, upper + 1) before flooring, as soogo does for the integer coordinates
    of mixed problems (Tolson and Shoemaker, 2007).
    """
    import numpy as np
    from scipy.stats import truncnorm

    lower = np.array([b[0] for b in bounds], dtype=float)
    upper = np.array([b[1] for b in bounds], dtype=float) + 1
    mu = np.asarray(mu, dtype=float)
    scale = sigma_ref * (upper - lower)
    a, b = (lower - mu) / scale, (upper - mu) / scale

    def draw(size):
        values = truncnorm.rvs(a, b, mu, scale, size=(size, len(mu)), random_state=rng)
        return np.minimum(np.floor(values), upper - 1)

    mask = rng.random((n, len(mu))) < probability
    empty = ~mask.any(axis=1)
    mask[empty, rng.integers(len(mu), size=int(empty.sum()))] = True
    sample = np.where(mask, draw(n), mu)
    # Candidates that did not move are redrawn in every coordinate.
    still = np.all(sample == mu, axis=1)
    if still.any():
        sample[still] = draw(int(still.sum()))
    return sample


def run_miso(lookup, seed, log):
    import numpy as np
    from soogo import MedianLpfFilter, RbfModel, cptv
    from soogo.acquisition import BoundedParameter, CoordinatePerturbation
    from soogo.termination import RobustCondition, UnsuccessfulImprovement

    class IntegerCoordinatePerturbation(CoordinatePerturbation):
        """CPTV's coordinate perturbation applied to a pure-integer domain.

        soogo 2.1.0 requires a continuous variable in its DDS sampler; the
        configuration spaces here are pure-integer.
        """

        def generate_candidates(self, bounds, mu, iindex=()):
            return integer_dds(self.pool_size, bounds, self._perturbation_probability, mu,
                               self.sigma.value, self.rng)

    values, _ = shared_starts(lookup)
    s = lookup.spec
    dimension = len(s["lower"])
    model = RbfModel(iindex=tuple(range(dimension)), filter=MedianLpfFilter())
    model.update(np.array(s["starts"], dtype=float), np.array(values, dtype=float))
    # Same settings as the soogo.cptv default, without the continuous local search,
    # which has no coordinates to act on in a pure-integer problem.
    rng = np.random.default_rng([UNIFORM_STREAM, seed])
    perturbation = IntegerCoordinatePerturbation(
        pool_size=min(500 * dimension, 5000),
        weightpattern=(0.3, 0.5, 0.8, 0.95),
        sigma=BoundedParameter(0.2, 0.2 * 0.5**6, 0.2),
        termination=RobustCondition(UnsuccessfulImprovement(1e-3), max(5, dimension)),
        n_continuous_search=0,
        seed=int(rng.integers(np.iinfo(np.int32).max)),
    )

    def objective(points):
        return np.array([lookup.evaluate(p, "miso") for p in np.atleast_2d(points)], dtype=float)

    class Stalled(Exception):
        pass

    # On small domains the acquisition can run out of unevaluated candidates; CPTV
    # then alternates its steps without evaluating. Stop after ten such iterations.
    progress = dict(evaluations=len(lookup.events), idle=0)

    def callback(result):
        if len(lookup.events) > progress["evaluations"]:
            progress.update(evaluations=len(lookup.events), idle=0)
            return
        progress["idle"] += 1
        if progress["idle"] >= 10:
            raise Stalled

    stop = "budget"
    with capture_native_output(log):
        try:
            cptv(objective, [(lo, hi) for lo, hi in zip(s["lower"], s["upper"])], s["budget"] - 3,
                 surrogateModel=model, acquisitionFunc=perturbation, seed=seed, callback=callback)
        except Stalled:
            stop = "no_new_candidates"
    return dict(stop_reason=stop, coordinate_perturbation="integer_dds")


ADAPTERS = {"nomad": run_nomad, "miso": run_miso, "uniform": run_uniform}


def load_responses(job, package, grid_costs, coverage):
    s = job["spec"]
    if s["scope"] == "grid":
        rows = shared.read_csv(package / f"inputs/grids/{s['case']}.csv")
        responses = {tuple(json.loads(r["Point"])): (True, float(r["z_norm"])) for r in rows}
        costs = {p: grid_costs[s["case"], p] for p in responses}
        return responses, costs, lambda p: True
    rows = shared.read_csv(package / f"inputs/process/{s['case']}_full.csv")
    responses, costs = {}, {}
    for r in rows:
        p = tuple(json.loads(r["point"]))
        accepted = r["accepted"] == "True"
        responses[p] = (accepted, float(r["objective"]) if accepted else None)
        costs[p] = float(r["total_wall_s"])
    status = {p: coverage[s["case"], p] for p in responses}
    return responses, costs, lambda p: status[p] in ("accepted", "rejected", "solver_error")


def build_result(job, method, status, error, details, events, elapsed, invalid, overruns, hit):
    s = job["spec"]
    job_id = s["job_id"].rsplit("_dsda", 1)[0]
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    ok = status == "completed" and len(events) >= 3 and not invalid
    success = bool(ok and best and hit(best["raw_objective"], job["target"]))
    lookup_s = math.fsum(e["lookup_wall_s"] for e in events)
    point_cost = math.fsum(e["point_cost_s"] for e in events)
    prep_s = float(job["baseline"]["prep_s"])
    timed = elapsed is not None
    return dict(
        spec={**s, "method": method, "job_id": f"{job_id}_{method}"},
        status="invalid_point" if invalid else status,
        error=error,
        category="execution_failed" if not ok or best is None else "target_reached" if success else "target_not_reached",
        hit=success,
        target=job["target"],
        best_objective=best["raw_objective"] if best else None,
        best_point=best["point"] if best else None,
        evaluations=len(events),
        nlp_solves=sum(e["nlp_solve"] for e in events),
        first_hit=next((e["index"] for e in accepted if hit(e["raw_objective"], job["target"])), None)
        if success else None,
        overruns=overruns,
        invalid_points=invalid,
        solver=details,
        search_s=elapsed,
        lookup_s=lookup_s,
        retained_search_s=elapsed - lookup_s if timed else None,
        point_cost_s=point_cost,
        prep_s=prep_s,
        completion_s=elapsed - lookup_s + point_cost + prep_s if timed else None,
        penalty=PENALTY,
        process_nlp_calls=0,
        effective_cpus=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
    )


def child(job, method, package, directory, grid_costs, coverage, hit, extra):
    """One run in a forked process, so a native solver crash cannot stop the campaign."""
    NOMAD_EXTRA.extend(extra)
    status, error, details, lookup = "completed", None, {}, None
    started = time.perf_counter()
    try:
        responses, costs, nlp_status = load_responses(job, package, grid_costs, coverage)
        lookup = Lookup(job, responses, costs, nlp_status, directory / "callbacks.jsonl")
        details = ADAPTERS[method](lookup, job["spec"]["seed"], directory / "search.log")
    except Exception:  # noqa: BLE001
        status, error = "execution_failed", traceback.format_exc()
    elapsed = time.perf_counter() - started
    result = build_result(job, method, status, error, details, lookup.events if lookup else [], elapsed,
                          lookup.invalid if lookup else [], lookup.overruns if lookup else 0, hit)
    shared.write_json(directory / "result.json", result)


# NOMAD 4.6.0 can crash while it cycles through cached points after its last
# evaluation; a rerun with a larger total-evaluation cap must reproduce the path.
NOMAD_RERUNS = (["MAX_EVAL 5000"], ["MAX_EVAL 20000"])


def attempt(job, method, package, directory, grid_costs, coverage, hit, timeout, extra):
    import multiprocessing

    directory.mkdir(parents=True)
    (directory / "callbacks.jsonl").touch()
    process = multiprocessing.get_context("fork").Process(
        target=child, args=(job, method, package, directory, grid_costs, coverage, hit, extra))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.kill()
        process.join()
        status = f"timeout_after_{timeout}s"
    elif process.exitcode == 0 and (directory / "result.json").exists():
        return shared.read_json(directory / "result.json")
    else:
        status = f"crashed_exit_{process.exitcode}"
    events = [json.loads(x) for x in (directory / "callbacks.jsonl").read_text().splitlines()]
    result = build_result(job, method, status, f"Worker {status}", {}, events, None, [], 0, hit)
    shared.write_json(directory / "result.json", result)
    return result


def points(directory):
    return [json.loads(x)["point"] for x in (directory / "callbacks.jsonl").read_text().splitlines()]


def execute(job, method, package, runs, grid_costs, coverage, hit, timeout):
    job_id = job["spec"]["job_id"].rsplit("_dsda", 1)[0]
    directory = runs / f"{job_id}__{method}"
    result = attempt(job, method, package, directory, grid_costs, coverage, hit, timeout, [])
    if method != "nomad" or not result["status"].startswith("crashed"):
        return result
    history = [dict(extra=[], status=result["status"], evaluations=result["evaluations"])]
    crashed_path = points(directory)
    for k, extra in enumerate(NOMAD_RERUNS, 1):
        rerun_dir = directory / f"rerun_{k}"
        rerun = attempt(job, method, package, rerun_dir, grid_costs, coverage, hit, timeout, extra)
        same = points(rerun_dir) == crashed_path
        history.append(dict(extra=extra, status=rerun["status"], evaluations=rerun["evaluations"],
                            same_path_as_crash=same))
        if rerun["status"] == "completed" and same:
            rerun["status"] = "completed_after_verified_rerun"
            rerun["solver"]["reruns"] = history
            shared.write_json(directory / "result.json", rerun)
            return rerun
        if not rerun["status"].startswith("crashed"):
            break
    result["solver"] = dict(reruns=history)
    shared.write_json(directory / "result.json", result)
    return result


def summarize(results):
    rows, groups = [], {}
    for r in results:
        s = r["spec"]
        rows.append(dict(scope=s["scope"], case=s["case"], budget=s["budget"], seed=s["seed"], method=s["method"],
                         status=r["status"], hit=r["hit"], best_objective=r["best_objective"],
                         evaluations=r["evaluations"], nlp_solves=r["nlp_solves"], first_hit=r["first_hit"],
                         retained_search_s=r["retained_search_s"], point_cost_s=r["point_cost_s"],
                         prep_s=r["prep_s"], completion_s=r["completion_s"]))
        key = (s["scope"], s["case"] if s["scope"] == "process" else "all_grid", s["budget"], s["method"])
        groups.setdefault(key, []).append(r)
    summary = []
    for (scope, case, budget, method), group in sorted(groups.items()):
        completion = [g["completion_s"] for g in group if g["completion_s"] is not None] or [math.nan]
        search = [g["retained_search_s"] for g in group if g["retained_search_s"] is not None] or [math.nan]
        summary.append(dict(scope=scope, case=case, budget=budget, method=method, runs=len(group),
                            hits=sum(g["hit"] for g in group),
                            failures=sum(g["category"] == "execution_failed" for g in group),
                            crashes=sum(g["status"].startswith(("crashed", "timeout")) for g in group),
                            verified_reruns=sum(g["status"] == "completed_after_verified_rerun" for g in group),
                            median_evaluations=statistics.median(g["evaluations"] for g in group),
                            median_nlp_solves=statistics.median(g["nlp_solves"] for g in group),
                            median_search_s=shared.quantile(search, 0.5),
                            median_completion_s=shared.quantile(completion, 0.5),
                            q25_completion_s=shared.quantile(completion, 0.25),
                            q75_completion_s=shared.quantile(completion, 0.75)))
    return rows, summary


def comparison(summary):
    """Target hits of the new methods next to the published methods, per condition."""
    published = {}
    for r in shared.read_csv(PUBLISHED):
        if r["method"] in PUBLISHED_METHODS:
            key = (r["scope"], r["case"] if r["scope"] == "process" else "all_grid", int(r["budget"]), r["method"])
            published[key] = published.get(key, 0) + (r["hit"] == "True")
    out = []
    for key in sorted({(s["scope"], s["case"], s["budget"]) for s in summary}):
        row = dict(scope=key[0], case=key[1], budget=key[2])
        row.update({m: published.get((*key, m)) for m in PUBLISHED_METHODS})
        row.update({s["method"]: s["hits"] for s in summary if (s["scope"], s["case"], s["budget"]) == key})
        out.append(row)
    return out


def provenance(args, cpu, started, finished, archive_sha):
    def git(*a):
        out = subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else None

    versions = {}
    for name in ("numpy", "pandas", "scipy", "PyNomadBBO", "soogo"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return dict(command=sys.argv, arguments={k: str(v) for k, v in vars(args).items()},
                started_utc=started, finished_utc=finished, archive_sha256=archive_sha,
                grid_costs_sha256=GRID_COSTS_SHA256, script_sha256=shared.sha(HERE),
                git_head=git("rev-parse", "HEAD"), git_status=git("status", "--porcelain"),
                host=platform.node(), platform=platform.platform(), python=platform.python_version(),
                versions=versions, threads=THREADS, cpu=cpu, penalty=PENALTY, process_nlp_calls=0)


def run(args):
    NOMAD_EXTRA[:] = args.nomad_param
    started = datetime.now(timezone.utc).isoformat()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if shared.sha(GRID_COSTS) != GRID_COSTS_SHA256:
        raise ValueError("Grid point-cost table changed")
    grid_costs = {(r["grid_name"], tuple(json.loads(r["point"]))): float(r["point_wall_s"])
                  for r in shared.read_csv(GRID_COSTS)}
    coverage = {(r["case"], tuple(json.loads(r["coordinates"]))): r["status"] for r in shared.read_csv(COVERAGE)}
    with tempfile.TemporaryDirectory() as scratch:
        package, _ = shared.extract_package(args.archive, scratch)
        cpu = shared.pin_cpu(args.cpu, package)
        jobs = [j for j in shared.read_json(package / "inputs/jobs.json") if j["spec"]["scope"] in args.scopes]
        if args.budgets:
            jobs = [j for j in jobs if j["spec"]["budget"] in set(args.budgets) or j["spec"]["scope"] == "process"]
        if args.jobs:
            jobs = [j for j in jobs if j["spec"]["job_id"].rsplit("_dsda", 1)[0] in set(args.jobs)]
            if len(jobs) != len(set(args.jobs)):
                raise ValueError("Unknown job identifier requested")
        runs = output / "runs"
        runs.mkdir(parents=True)
        results = []
        with shared.sealed_modules(package) as (_, hit):
            for n, job in enumerate(jobs, 1):
                for method in args.methods:
                    r = execute(job, method, package, runs, grid_costs, coverage, hit, args.timeout)
                    results.append(r)
                    print(f"[{n}/{len(jobs)}] {r['spec']['job_id']:<44} {r['category']:<18} "
                          f"evals={r['evaluations']}/{job['spec']['budget']} {r['status']}", flush=True)
        rows, summary = summarize(results)
        shared.write_csv(output / "runs.csv", rows)
        shared.write_csv(output / "condition_summary.csv", summary)
        shared.write_csv(output / "comparison_hits.csv", comparison(summary))
        failures = [r["spec"]["job_id"] for r in results if r["category"] == "execution_failed"]
        crashes = [r["spec"]["job_id"] for r in results if r["status"].startswith(("crashed", "timeout"))]
        overruns = [r["spec"]["job_id"] for r in results if r["overruns"]]
        checks = dict(failures=failures, solver_crashes=crashes, budget_overruns=overruns,
                      over_budget=[r["spec"]["job_id"] for r in results if r["evaluations"] > r["spec"]["budget"]],
                      shared_start_order=all(
                          [json.loads(line)["point"] for line in
                           (runs / f"{r['spec']['job_id'].rsplit('_', 1)[0]}__{r['spec']['method']}" / "callbacks.jsonl")
                           .read_text().splitlines()[:3]] == r["spec"]["starts"]
                          for r in results if r["evaluations"] >= 3))
        shared.write_json(output / "checks.json", checks)
        shared.write_json(output / "manifest.json", provenance(
            args, cpu, started, datetime.now(timezone.utc).isoformat(), shared.ARCHIVE_SHA256))
    # Native solver crashes are recorded as failed runs; harness errors fail the check.
    passed = not (set(failures) - set(crashes)) and not checks["over_budget"] and checks["shared_start_order"]
    print("CHECKS", "PASSED" if passed else "FAILED",
          json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in checks.items()}))
    if not args.no_zip:
        archive = shutil.make_archive(str(output), "zip", output.parent, output.name)
        print("RETURN_ARCHIVE", archive)
        print("SCP_RETURN_ARCHIVE", f"{platform.node()}:{archive}")
    return 0 if passed else 1


def main(argv=None):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", default=str(shared.ARCHIVE))
    parser.add_argument("--output", default=str(REPO / f"results/mixed_integer_dfo_{stamp}_{os.getpid()}"))
    parser.add_argument("--cpu", default="auto", help="'auto' (observed idle core), an integer, or 'none'")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=["nomad", "miso"])
    parser.add_argument("--scopes", nargs="+", choices=["grid", "process"], default=["grid", "process"])
    parser.add_argument("--budgets", nargs="*", type=int, help="Restrict Grid jobs to these budgets")
    parser.add_argument("--timeout", type=float, default=2100, help="Seconds per run before the worker is killed")
    parser.add_argument("--nomad-param", action="append", default=[], help="Extra NOMAD parameter line")
    parser.add_argument("--jobs", nargs="*", help="Restrict to these job identifiers, e.g. cstr_30_B43_seed0")
    parser.add_argument("--no-zip", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
