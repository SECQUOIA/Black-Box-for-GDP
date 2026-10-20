"""Verify and replay a retained return; never launch a worker or a solver."""

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import json
import math
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import statistics
import tempfile
import zipfile

from .common import THREADS, check_settings, csvrows, read, save, sha, verify, writecsv


ARCHIVE_NAME = "review_comparison_20261020_124949_return_1792527395393579314.zip"
ARCHIVE_SHA256 = "659ddd3d1c1f62def4f8875399b63bdd4899f44ff848afb4ea45c079b3c1dc36"
REPO = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


@contextmanager
def verified_return(path, expected_sha256):
    require(sha(path) == expected_sha256, "Return ZIP SHA256 mismatch")
    with zipfile.ZipFile(path) as archive:
        seen = set()
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            require(
                not name.is_absolute()
                and ".." not in name.parts
                and "\\" not in item.filename
                and not stat.S_ISLNK(item.external_attr >> 16)
                and item.filename not in seen,
                "Unsafe or duplicate archive member: " + item.filename,
            )
            seen.add(item.filename)
        roots = {PurePosixPath(n).parts[0] for n in seen}
        require(len(roots) == 1, "Return must have exactly one root")
        require(archive.testzip() is None, "ZIP CRC failure")
        with tempfile.TemporaryDirectory(prefix="review-comparison-audit-") as temp:
            archive.extractall(temp)
            yield Path(temp) / roots.pop(), len(seen)


def close(actual, expected, label):
    # Python 3.12 changed float summation. This is a verification allowance for
    # retained clock sums, NOT a relaxation of the target or feasibility rule.
    require(
        math.isfinite(actual) and math.isfinite(expected)
        and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12),
        f"{label}: {actual!r} != {expected!r}",
    )


def audit_events(job, events, result, costs, prep):
    """Independently check keys, acceptance, budget, values, and charged costs."""
    require(0 < len(events) <= job["budget"], "Callback budget violation")
    require(len(events) == result["evaluations"], "Callback count differs")
    require([e["index"] for e in events] == list(range(1, len(events) + 1)),
            "Callback order differs")
    require([e["point"] for e in events[:3]] == job["starts"][:min(3, len(events))],
            "Shared initial order differs")
    for e in events:
        point = e["point"]
        require(len(point) == len(job["lower"]) and all(
            isinstance(x, int) and lo <= x <= hi
            for x, lo, hi in zip(point, job["lower"], job["upper"])
        ), "Out-of-domain callback")
        require(tuple(point) in costs, "Missing point cost")
        cost, source = costs[tuple(point)]
        require(cost is not None and math.isfinite(cost) and cost > 0,
                "Missing/nonpositive point time")
        require(e["historical_point_cost_s"] == cost, "Wrong callback cost")
        accepted = job["scope"] == "grid" or source["accepted"] == "True"
        require(e["accepted"] == accepted, "Wrong acceptance flag")
        if accepted:
            expected = float(source["csv_objective"] if job["scope"] == "grid"
                             else source["objective"])
            require(math.isclose(e["raw_objective"], expected, rel_tol=0,
                                 abs_tol=1e-12 if job["scope"] == "grid" else 0),
                    "Wrong accepted objective")
            require(e["method_value"] == e["raw_objective"], "Changed accepted response")
        else:
            require(e["raw_objective"] is None and e["failure_reason"],
                    "Missing failure provenance")
            if job["case"].startswith("cstr_"):
                require(e["method_value"] is None and e["method_value_kind"] == "+inf",
                        "Changed CSTR rejection penalty")
            else:
                require(e["method_value"] == 1e6, "Changed rejection penalty")
        require(math.isfinite(e["lookup_wall_s"]) and e["lookup_wall_s"] >= 0,
                "Invalid lookup time")
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    target = min(float(row["csv_objective"] if job["scope"] == "grid" else row["objective"])
                 for _, row in costs.values()
                 if job["scope"] == "grid" or row["accepted"] == "True")
    require(result["target"] == target, "Changed reporting target")
    require(result["best_objective"] == (best["raw_objective"] if best else None)
            and result["best_point"] == (best["point"] if best else None), "Wrong incumbent")
    hit = best is not None and abs(best["raw_objective"] - target) <= 1e-5 * max(1, abs(target))
    category = ("execution_failed" if result["status"] == "execution_failed" or best is None
                else "target_reached" if hit else "target_not_reached")
    require(result["target_observed"] == hit and result["category"] == category,
            "Changed target/category rule")
    require(result["missing_cost_callbacks"] == 0, "Missing callback costs")
    require(result["one_time_preparation_s"] == prep, "Wrong preparation cost")
    close(result["sum_point_cost_s"], math.fsum(e["historical_point_cost_s"] for e in events),
          "Point cost sum")
    close(result["lookup_wall_s"], math.fsum(e["lookup_wall_s"] for e in events), "Lookup sum")
    close(result["retained_search_wall_s"], result["recorded_search_wall_s"] - result["lookup_wall_s"],
          "Retained search")
    close(result["reconstructed_total_s"], result["retained_search_wall_s"] + result["sum_point_cost_s"] + prep,
          "Reconstructed cost")
    return {
        "callbacks": len(events), "accepted_callbacks": len(accepted),
        "unaccepted_callbacks": len(events) - len(accepted),
        "repeat_callbacks": len(events) - len({tuple(e["point"]) for e in events}),
        "initial_accepted": sum(e["accepted"] for e in events[:3]),
        "last_callback_delivered": events[-1]["value_returned_to_optimizer"],
    }


def audit_runtime(job, runtime, config):
    expected = job["reference_runtime"]
    require(runtime["python"] == expected["python"]
            and runtime["versions"] == expected["versions"]
            and runtime["host"] == expected["host"], "Runtime version/host mismatch")
    require(runtime["threads"] == THREADS and runtime["concurrency"] == 1
            and runtime["affinity"]["effective_cpus"] == [config["cpu"]],
            "Thread/affinity mismatch")
    if job["method"] == "rbfopt_msrsm_genetic":
        for key, setting in (("bonmin", "minlp_solver_path"), ("ipopt", "nlp_solver_path")):
            expected_hash = expected.get(key + "_sha256", expected.get("solvers", {}).get(key))
            require(runtime["binary_sha256"][key] == expected_hash
                    and config[key] == job["reference_settings"][setting], "Solver identity mismatch")


def audit_raw_events(attempt, job, ledger):
    if job["scope"] == "process":
        raw = [json.loads(s) for s in (attempt / "callbacks.jsonl").read_text().splitlines()]
        require(len(raw) == len(ledger), "Native callback count mismatch")
        for before, after in zip(raw, ledger):
            require(all(after[k] == v for k, v in before.items()), "Native callback changed")
    else:
        paths = list((attempt / "lookup.traces").rglob("*.jsonl"))
        require(len(paths) == 1, "Expected one native Grid trace")
        raw = [json.loads(s) for s in paths[0].read_text().splitlines()]
        raw = [e for e in raw if e.get("event") == "evaluation"]
        require(len(raw) == len(ledger), "Native Grid callback count mismatch")
        mapping = {"evaluation_index": "index", "point": "point", "value": "raw_objective",
                   "objective_wall_s": "lookup_wall_s", "completed_elapsed_s": "elapsed_s"}
        for before, after in zip(raw, ledger):
            require(all(before[k] == after[v] for k, v in mapping.items()), "Native Grid callback changed")


def audit_directory(directory, output):
    from .runner import check_inputs, selected_result, snapshot
    from .worker import cost_data, sampling_points

    root = directory / "reproduction"
    identity = verify(root)
    run = read(directory / "run.json")
    require(identity == run["package_identity"], "Execution input/source identity changed")
    jobs = read(root / "plan.json")
    inputs = check_inputs(root)
    require(not inputs["missing_costs"], "Incomplete point costs")
    require({p.name for p in (directory / "jobs").iterdir()} == {j["job_id"] for j in jobs},
            "Missing or extra job directory")
    records, cache, auxiliary = [], {}, Counter()
    auxiliary_events = Counter()
    callback_states = Counter()
    runtime_signatures = {}
    sealed_files = 0
    for job in jobs:
        candidates = list((directory / "jobs" / job["job_id"]).glob("attempt_*"))
        require(len(candidates) == 1, "This published return must contain one attempt per slot")
        selected = selected_result(directory, job)
        require(selected is not None, "Unsealed job: " + job["job_id"])
        attempt, result = selected
        sealed_files += len(read(attempt / "seal.json"))
        runtime = read(attempt / "runtime.json")
        audit_runtime(job, runtime, run["config"])
        runtime_signatures[job["scope"]] = runtime
        process = read(attempt / "process.json")
        require(process["returncode"] == 0 and not process["watchdog_timeout"]
                and process["hard_seconds"] == job["hard_seconds"], "Worker/watchdog failure")
        require(math.isfinite(process["worker_wall_s"]) and process["worker_wall_s"] > 0,
                "Missing worker time")
        if job["method"] == "rbfopt_msrsm_genetic":
            settings = read(attempt / "settings_comparison.json")
            require(settings["historical"] == job["reference_settings"], "Changed settings reference")
            require(check_settings(settings["historical"], settings["actual"]) == settings["difference"],
                    "Changed settings audit")
        events = [json.loads(line) for line in (attempt / "evaluations.jsonl").read_text().splitlines()]
        callback_states.update(e["source_status"] for e in events)
        audit_raw_events(attempt, job, events)
        if job["method"] != "rbfopt_msrsm_genetic":
            points, settings = sampling_points(job)
            require([e["point"] for e in events] == points, "Sampling path differs from frozen design")
            require(read(attempt / "sampling_settings.json") == settings, "Sampling settings differ")
        key = job["scope"], job["case"]
        if key not in cache:
            cache[key] = cost_data(root, job)
        counters = audit_events(job, events, result, *cache[key])
        if job["scope"] == "process":
            require(len(events) == job["budget"] and events[-1]["callback_exit"] == "budget_stop"
                    and not events[-1]["value_returned_to_optimizer"], "Changed Process terminal policy")
        calls = attempt / "auxiliary_solver_calls.jsonl"
        if calls.exists():
            for line in calls.read_text().splitlines():
                call = json.loads(line)
                auxiliary_events[call["event"]] += 1
                if call["event"] == "start":
                    require(call["scope"] == "RBFOpt surrogate only", "Unexpected auxiliary solve scope")
                    auxiliary[call["solver"]] += 1
        records.append({k: job[k] for k in ("job_id", "scope", "case", "budget", "seed", "method")}
                       | counters | {k: result[k] for k in ("status", "category", "best_objective",
                           "recorded_search_wall_s", "retained_search_wall_s", "lookup_wall_s",
                           "sum_point_cost_s", "reconstructed_total_s", "missing_cost_callbacks")}
                       | {"worker_wall_s": process["worker_wall_s"], "attempt_count": 1})
    progress = snapshot(directory, jobs)
    require(progress == read(directory / "progress.json") == read(directory / "status_final.json"),
            "Retained progress differs from replay")
    report = {
        "verified_jobs": len(records), "verified_sealed_files": sealed_files,
        "verified_callbacks": sum(r["callbacks"] for r in records),
        "status_counts": progress["status_counts"],
        "outcome_counts": progress["completed_outcome_counts"],
        "jobs_with_short_budget": sum(r["callbacks"] < r["budget"] for r in records),
        "repeat_callbacks": sum(r["repeat_callbacks"] for r in records),
        "unaccepted_callbacks": sum(r["unaccepted_callbacks"] for r in records),
        "callback_source_status_counts": dict(callback_states),
        "missing_cost_callbacks": sum(r["missing_cost_callbacks"] for r in records),
        "jobs_with_zero_accepted_initial_points": sum(r["initial_accepted"] == 0 for r in records),
        "worker_wall_sum_s": math.fsum(r["worker_wall_s"] for r in records),
        "recorded_search_wall_sum_s": math.fsum(r["recorded_search_wall_s"] for r in records),
        "package_inventory_sha256": identity,
        "runtime_examples": runtime_signatures,
        "process_surrogate_solver_starts": dict(auxiliary),
        "process_surrogate_solver_events": dict(auxiliary_events),
        "grid_auxiliary_solver_audit": "Grid wrapper retains stdout, not a structured solver-call ledger; no call count inferred",
        "execution_provenance": read(root / "evidence/source_provenance.json"),
        "new_optimization_or_nlp_experiments_during_audit": False,
        "verification_clock_sum_tolerance": "1e-12 absolute/relative for float sums only; target tolerance unchanged",
        "audit_python": platform.python_version(),
    }
    controller_ids = {"START": [], "END": []}
    for path in (directory / "controller_logs").glob("*.log"):
        for line in path.read_text().splitlines():
            for kind in controller_ids:
                if line.startswith(kind + " "):
                    controller_ids[kind].append(line.split()[1].rstrip(":"))
    for kind, ids in controller_ids.items():
        require(Counter(ids) == Counter(j["job_id"] for j in jobs), "Controller log job inventory: " + kind)
    report["controller_starts_and_ends"] = {k: len(v) for k, v in controller_ids.items()}
    writecsv(output / "new_run_audit.csv", records)
    return report, jobs


def comparisons(analysis, output):
    rows = csvrows(analysis / "completed_runs.csv")
    by_method = defaultdict(list)
    for r in rows:
        by_method[r["scope"], r["method"]].append(r)
    summary = []
    for (scope, method), rr in sorted(by_method.items()):
        counts = Counter(r["category"] for r in rr)
        summary.append({"scope": scope, "method": method, "runs": len(rr), **counts,
                        "target_rate": counts["target_reached"] / len(rr),
                        "median_retained_search_s": statistics.median(float(r["search_s"]) for r in rr),
                        "median_reconstructed_cost_s": statistics.median(
                            float(r["search_s"]) + float(r["point_cost_s"]) + float(r["prep_s"]) for r in rr)})
    writecsv(output / "method_summary.csv", summary)
    budget_rows = []
    for budget in (10, 30, 50, 70, 100):
        for (scope, method), rr in sorted(by_method.items()):
            if scope != "grid":
                continue
            selected = [r for r in rr if int(r["budget"]) == budget]
            budget_rows.append({"budget": budget, "method": method, "runs": len(selected),
                                "target_reached": sum(r["category"] == "target_reached" for r in selected)})
    writecsv(output / "grid_budget_summary.csv", budget_rows)
    index = {(r["scope"], r["case"], r["budget"], r["seed"], r["method"]): r for r in rows}
    paired = []
    for r in rows:
        if r["method"] != "rbfopt_msrsm_genetic":
            continue
        old = index[r["scope"], r["case"], r["budget"], r["seed"], "rbfopt_msrsm_solver"]
        a = float(old["search_s"])
        b = float(r["search_s"])
        ac = a + float(old["point_cost_s"]) + float(old["prep_s"])
        bc = b + float(r["point_cost_s"]) + float(r["prep_s"])
        paired.append({k: r[k] for k in ("scope", "case", "budget", "seed")}
                      | {"solver_hit": old["category"] == "target_reached", "genetic_hit": r["category"] == "target_reached",
                         "solver_search_s": a, "genetic_search_s": b, "solver_over_genetic_search_ratio": a / b,
                         "solver_cost_s": ac, "genetic_cost_s": bc, "solver_over_genetic_cost_ratio": ac / bc,
                         "solver_evaluations": old["evaluations"], "genetic_evaluations": r["evaluations"]})
    writecsv(output / "rbfopt_paired_runs.csv", paired)
    timing = []
    for scope in ("grid", "process"):
        rr = [r for r in paired if r["scope"] == scope]
        timing.append({"scope": scope, "pairs": len(rr),
                       "median_paired_search_ratio": statistics.median(r["solver_over_genetic_search_ratio"] for r in rr),
                       "median_paired_cost_ratio": statistics.median(r["solver_over_genetic_cost_ratio"] for r in rr),
                       "genetic_faster_search_runs": sum(r["genetic_search_s"] < r["solver_search_s"] for r in rr),
                       "genetic_cheaper_total_runs": sum(r["genetic_cost_s"] < r["solver_cost_s"] for r in rr),
                       "both_hit": sum(r["genetic_hit"] and r["solver_hit"] for r in rr),
                       "genetic_only_hit": sum(r["genetic_hit"] and not r["solver_hit"] for r in rr),
                       "solver_only_hit": sum(r["solver_hit"] and not r["genetic_hit"] for r in rr)})
    writecsv(output / "rbfopt_timing_summary.csv", timing)


def run(archive, output, expected=ARCHIVE_SHA256):
    output.mkdir(parents=True, exist_ok=False)
    with verified_return(archive, expected) as (directory, members):
        report, jobs = audit_directory(directory, output)
        report["archive"] = {"name": archive.name, "sha256": expected, "members": members,
                             "bytes": archive.stat().st_size}
        original = list(directory.glob("analysis_*"))
        require(len(original) == 1, "Expected one retained server analysis")
        original = original[0]
        # Execute only repository analysis code, after matching its executed bytes.
        for name in ("analysis.py", "runner.py", "common.py"):
            require(sha(Path(__file__).with_name(name)) == sha(directory / "reproduction/review_comparison" / name),
                    "Analysis source differs from execution snapshot: " + name)
        from .analysis import summarize

        replay = summarize(directory / "reproduction", directory, jobs)
        comparison = []
        for p in sorted(original.iterdir()):
            if p.suffix == ".csv" or p.name in ("interpretation.json", "progress.json"):
                require(p.read_bytes() == (replay / p.name).read_bytes(), "Analysis replay differs: " + p.name)
                comparison.append({"file": p.name, "sha256": sha(p), "byte_identical": True})
        report["analysis_replay"] = comparison
        report["retained_analysis_member"] = directory.name + "/" + original.name
        retained = output / "tables"
        retained.mkdir()
        for p in original.iterdir():
            if p.suffix == ".csv" or p.name == "interpretation.json":
                shutil.copyfile(p, retained / p.name)
        comparisons(original, retained)
        save(output / "verification.json", report)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=REPO / "results/archives" / ARCHIVE_NAME)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing outputs refused")
    args = parser.parse_args()
    print(run(args.archive.resolve(), args.output.resolve()))


if __name__ == "__main__":
    main()
