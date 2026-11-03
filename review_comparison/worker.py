"""One isolated job; original wrappers and frozen inputs remain byte-preserved."""

import contextlib
import hashlib
import importlib
import importlib.metadata
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import sys
import time
import traceback

from .common import THREADS, check_settings, clean, csvrows, read, save, sha


def domain(job):
    return list(
        itertools.product(
            *(range(lo, hi + 1) for lo, hi in zip(job["lower"], job["upper"]))
        )
    )


def sampling_points(job):
    """Candidate generation sees bounds, starts and frozen prefix only; no oracle."""
    initial = [list(p) for p in job["starts"]]
    fixed = job["predetermined"] if job["method"] == "bam_predetermined_uniform" else []
    prefix = initial + [list(p) for p in fixed]
    remaining = sorted(set(domain(job)) - {tuple(p) for p in prefix})
    material = (
        f"review-sampling-v1:{job['scope']}:{job['case']}:{job['seed']}:{job['method']}"
    )
    seed = int(hashlib.sha256(material.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    # A separate deterministic stream, independent of historical initial-design generation.
    count = job["budget"] - len(prefix)
    if count < 0 or count > len(remaining):
        raise ValueError("Sampling budget incompatible with frozen prefix/domain")
    return prefix + [list(p) for p in rng.sample(remaining, count)], {
        "generator": "Python random.Random / MT19937; sample without replacement",
        "seed_material": material,
        "seed_integer": str(seed),
        "initial_design": "archived, no RNG call",
        "predetermined_count": len(fixed),
        "continuation_count": count,
    }


def runtime(job, config):
    from cpu_affinity import pin_cpu, affinity_record

    cpu = pin_cpu(config["cpu"])
    expected = job["reference_runtime"]
    versions = {name: importlib.metadata.version(name) for name in expected["versions"]}
    if (
        versions != expected["versions"]
        or platform.python_version() != expected["python"]
    ):
        raise ValueError(
            f"Historical environment mismatch: Python {platform.python_version()}, {versions}"
        )
    if platform.node() != expected["host"]:
        raise ValueError(
            f"Formal timings require original Dantzig host {expected['host']}"
        )
    if any(os.environ.get(k) != v for k, v in THREADS.items()):
        raise ValueError("Single-thread environment not set")
    hashes = {}
    if job["method"] == "rbfopt_msrsm_genetic":
        for key, setting in [
            ("bonmin", "minlp_solver_path"),
            ("ipopt", "nlp_solver_path"),
        ]:
            p = Path(config[key])
            want = expected.get(key + "_sha256", expected.get("solvers", {}).get(key))
            if (
                str(p) != job["reference_settings"][setting]
                or not os.access(p, os.X_OK)
                or sha(p) != want
            ):
                raise ValueError(f"Historical {key} executable path/hash mismatch: {p}")
            hashes[key] = sha(p)
        importlib.import_module("rbfopt")  # No trial solver invocation.
    return {
        "python": platform.python_version(),
        "versions": versions,
        "host": platform.node(),
        "platform": platform.platform(),
        "executable": sys.executable,
        "binary_sha256": hashes,
        "affinity": affinity_record(cpu),
        "threads": THREADS,
        "concurrency": 1,
    }


@contextlib.contextmanager
def audited_settings(job, output):
    import rbfopt

    original = rbfopt.RbfoptSettings
    original_algorithm = rbfopt.RbfoptAlgorithm

    def create(**kwargs):
        settings = original(**kwargs)
        actual = vars(settings).copy()
        difference = check_settings(job["reference_settings"], actual)
        save(
            output / "settings_comparison.json",
            {
                "historical": job["reference_settings"],
                "actual": actual,
                "difference": difference,
                "only_candidate_search_changed": True,
            },
        )
        return settings

    def create_algorithm(*args, **kwargs):
        algorithm = original_algorithm(*args, **kwargs)
        save(output / "effective_settings.json", vars(algorithm.l_settings))
        return algorithm

    rbfopt.RbfoptSettings = create
    rbfopt.RbfoptAlgorithm = create_algorithm
    try:
        yield
    finally:
        rbfopt.RbfoptSettings = original
        rbfopt.RbfoptAlgorithm = original_algorithm


def grid_job(root, job, config, output):
    from grid_dsda import load_grid_csv
    from evaluation_trace import EvaluationTrace
    from instrumentation import TrackedObjective
    from benchmark import run_rbfopt_benchmark_case, make_grid_objective

    csv_path = root / "frozen/grid/benchmark_grids" / f"{job['case']}.csv"
    _, values = load_grid_csv(csv_path)  # original pandas decimal parser
    reporting_target = min(values.values())
    record, error, status = None, None, "completed"
    with EvaluationTrace(output / "lookup.csv", job["original_spec"]) as trace:
        try:
            if job["method"] == "rbfopt_msrsm_genetic":
                with audited_settings(job, output):
                    record = run_rbfopt_benchmark_case(
                        csv_path,
                        values,
                        job["lower"],
                        job["upper"],
                        job["starts"],
                        job["seed"],
                        3,
                        job["budget"],
                        reporting_target,  # frozen wrapper uses this only in result_record
                        minlp_solver_path=config["bonmin"],
                        nlp_solver_path=config["ipopt"],
                        global_search_method="genetic",
                        verbose=True,
                    )["result_record"]
            else:
                objective = TrackedObjective(make_grid_objective(values))
                points, rng = sampling_points(job)
                save(output / "sampling_settings.json", rng)
                for point in points:
                    objective(point)
            # Match original grid trace endpoint: wrapper returned, before validation/export.
            elapsed = trace.timer() - trace.origin
        except Exception as exc:
            elapsed = trace.timer() - trace.origin
            status, error = "execution_failed", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        events = [dict(e) for e in trace.events]
        # Preserve partial JSONL even for exceptions; our final seal covers all raw outputs.
    normalized = [
        {
            "index": e["evaluation_index"],
            "point": e["point"],
            "raw_objective": e["value"],
            "accepted": e["value_kind"] == "finite",
            "method_value": e["value"],
            "method_value_kind": e["value_kind"],
            "lookup_wall_s": e["objective_wall_s"],
            "elapsed_s": e["completed_elapsed_s"],
            "value_returned_to_optimizer": e["exception_type"] is None,
            "callback_exit": e["exception_type"] or "return",
            "phase": e["phase"],
            "failure_reason": e["exception_type"],
        }
        for e in events
    ]
    return normalized, {
        "status": status,
        "error": error,
        "algorithm_result": record,
        "recorded_search_wall_s": elapsed,
    }


def process_job(root, job, config, output):
    module = importlib.import_module("ipopt_dfo_" + job["frozen_kind"])
    sys.meta_path.insert(0, module.ProcessModelImportBlocker())
    spec = {
        **job["original_spec"],
        "settings": {
            **job["original_spec"]["settings"],
            "global_search_method": "genetic",
        },
    }
    table, _ = module.load_table(root / "frozen" / job["frozen_kind"], job["case"])
    oracle = module.Oracle(spec, table, output)
    started = time.perf_counter()
    module.write(output / "started.json", {"pid": os.getpid(), "monotonic": started})
    status, error, result = "completed", None, None
    try:
        if job["method"] == "rbfopt_msrsm_genetic":
            with audited_settings(job, output):
                result = module.optimize(spec, oracle, config, output)
        else:
            points, rng = sampling_points(job)
            save(output / "sampling_settings.json", rng)
            for point in points:
                oracle(point)
    except module.BudgetStop:
        status = "budget_completed"
    except Exception as exc:
        if oracle.events and oracle.events[-1]["callback_exit"] == "budget_stop":
            status = "budget_completed"
            result = {"terminal_budget_exception": f"{type(exc).__name__}: {exc}"}
        else:
            status, error = "execution_failed", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
    if getattr(oracle, "budget_overrun", False) or any(
        e.get("budget_overrun") for e in oracle.events
    ):
        status, error = (
            "execution_failed",
            "Backend continued beyond B; original callback records preserved",
        )
    # Same endpoint as the historical process worker; summarize/export are measured separately.
    elapsed = time.perf_counter() - started
    return oracle.events, {
        "status": status,
        "error": error,
        "algorithm_result": clean(result),
        "recorded_search_wall_s": elapsed,
    }


def cost_data(root, job):
    if job["scope"] == "grid":
        rows = [
            r
            for r in csvrows(root / "data/grid_point_timings.csv")
            if r["grid_name"] == job["case"]
        ]
        return {
            tuple(json.loads(r["point"])): (float(r["point_wall_s"]), r) for r in rows
        }, 0.0
    rows = csvrows(root / "data" / f"cost_table_{job['case']}.csv")
    costs = {
        tuple(json.loads(r["point"])): (
            float(r["total_wall_s"]) if r["total_wall_s"] else None,
            r,
        )
        for r in rows
    }
    prep = 0.0
    if job["case"] == "dynamic":
        data = read(root / "frozen/non_cstr/inputs/dynamic/preparation.json")
        prep = float(data[0]["total_preparation_wall_s"])
    return costs, prep


def summarize_events(root, job, events, result):
    start = time.perf_counter()
    accepted = [e for e in events if e["accepted"] and e["index"] <= job["budget"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    extraction_wall_s = time.perf_counter() - start
    costs, prep = cost_data(root, job)
    target = (
        min(float(r["csv_objective"]) for _, r in costs.values())
        if job["scope"] == "grid"
        else min(
            float(r["objective"]) for _, r in costs.values() if r["accepted"] == "True"
        )
    )
    ledger = []
    for e in events:
        cost, row = costs.get(tuple(e["point"]), (None, None))
        if row is not None and e["accepted"]:
            obj = float(
                row["csv_objective"] if job["scope"] == "grid" else row["objective"]
            )
            if not math.isclose(
                obj,
                e["raw_objective"],
                rel_tol=0,
                abs_tol=1e-12 if job["scope"] == "grid" else 0,
            ):
                raise ValueError(
                    "Accepted callback differs from frozen point-cost objective"
                )
        ledger.append(
            {
                **e,
                "selection_phase": (
                    "shared_initial"
                    if e["index"] <= 3
                    else "archived_bam_predetermined"
                    if job["method"] == "bam_predetermined_uniform"
                    and e["index"] <= 3 + len(job["predetermined"])
                    else "uniform_without_replacement"
                    if job["method"] != "rbfopt_msrsm_genetic"
                    else "adaptive"
                ),
                "historical_point_cost_s": cost,
                "point_cost_source": f"data/{'grid_point_timings.csv' if job['scope'] == 'grid' else 'cost_table_' + job['case'] + '.csv'}",
                "source_status": row.get("status") if row else None,
                "cost_source_kind": row.get("cost_source", "original")
                if row
                else "missing",
            }
        )
    if (
        len(events) > job["budget"]
        or [e["point"] for e in events[:3]] != job["starts"][: min(3, len(events))]
    ):
        result.update(
            status="execution_failed", error="Callback budget/initial order violation"
        )
    hit = best is not None and abs(best["raw_objective"] - target) <= 1e-5 * max(
        1, abs(target)
    )
    category = (
        "execution_failed"
        if result["status"] == "execution_failed" or best is None
        else "target_reached"
        if hit
        else "target_not_reached"
    )
    if best is None and not result.get("error"):
        result["error"] = "no_accepted_observation"
    missing = sum(e["historical_point_cost_s"] is None for e in ledger)
    lookup = sum(e["lookup_wall_s"] for e in events)
    retained = result["recorded_search_wall_s"] - lookup
    total_cost = None if missing else sum(e["historical_point_cost_s"] for e in ledger)
    result.update(
        category=category,
        target_observed=hit,
        target=target,
        best_objective=best["raw_objective"] if best else None,
        best_point=best["point"] if best else None,
        evaluations=len(events),
        lookup_wall_s=lookup,
        retained_search_wall_s=retained,
        sum_point_cost_s=total_cost,
        one_time_preparation_s=prep,
        missing_cost_callbacks=missing,
        reconstructed_total_s=retained + total_cost + prep
        if total_cost is not None
        else None,
        target_rule="abs(best-target) <= 1e-5*max(1,abs(target)); reporting only",
        timing_kind="recorded search endpoint plus retained point costs; not online NLP",
        incumbent_extraction_wall_s=extraction_wall_s,
        incumbent_extraction_and_cost_join_wall_s=time.perf_counter() - start,
    )
    return ledger, result


def run(root, job, config, output, *, validate_runtime=True):
    output.mkdir(parents=True, exist_ok=True)
    save(output / "job.json", job)
    if validate_runtime:
        save(output / "runtime.json", runtime(job, config))
    sys.path.insert(0, str(root / "frozen" / job["frozen_kind"]))
    try:
        events, result = (grid_job if job["scope"] == "grid" else process_job)(
            root, job, config, output
        )
        ledger, result = summarize_events(root, job, events, result)
    except Exception as exc:
        traceback.print_exc()
        save(
            output / "adapter_failure.json",
            {"type": type(exc).__name__, "message": str(exc)},
        )
        raise
    start = time.perf_counter()
    with (output / "evaluations.jsonl").open("x") as stream:
        for row in ledger:
            stream.write(json.dumps(clean(row), allow_nan=False) + "\n")
    result["ledger_export_wall_s"] = time.perf_counter() - start
    save(output / "result.json", result)
    save(
        output / "seal.json",
        {
            p.relative_to(output).as_posix(): sha(p)
            for p in output.rglob("*")
            if p.is_file() and p.name not in ("process.json", "run.log", "seal.json")
        },
    )
    return result
