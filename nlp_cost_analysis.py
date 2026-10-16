"""Dantzig timing publication and fixed-coordinate NLP cost accounting.

The default CLI publishes the verified October 2 traces and all-outcome point
costs. Historical lookup-only comparisons require --legacy-lookup-only.
"""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

# Historical publication adapters are optional until their integration PRs land.
# Keep pure cost-ledger helpers importable without process or FMQA packages.
def grid_size(csv_name):
    from fmqa_benchmark.protocol import grid_size as implementation
    return implementation(csv_name)


def problem(spec):
    from fmqa_benchmark.protocol import problem as implementation
    return implementation(spec)


def enumeration_plan(*args, **kwargs):
    from gdp_models.domains import enumeration_plan as implementation
    return implementation(*args, **kwargs)



ROOT = Path(__file__).resolve().parent
METHODS = ("DSDA", "RBFOpt", "BAM 5.0.0", "FMQA-SA")
METHOD_NAMES = {"dsda": "DSDA", "rbfopt": "RBFOpt", "bam": "BAM 5.0.0", "fmqa_sa": "FMQA-SA"}
TOLERANCE = 1e-5


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No records for {path}")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def load_costs(directory, solver):
    directory = Path(directory)
    inventory = directory / "SHA256SUMS"
    for line in inventory.read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha(path) != digest:
            raise ValueError(f"Point-cost checksum mismatch: {name}")
    selected = [r for r in jsonl(directory / "points.jsonl") if r["solver"] == solver]
    costs = {(r["case"], r["cstr_size"], tuple(r["point"])): r for r in selected}
    if not selected or len(costs) != len(selected):
        raise ValueError("Missing or duplicate point costs")
    attempts = {a["attempt_id"]: a for a in jsonl(directory / "attempts.jsonl")}
    for row in selected:
        total = sum(attempts[a]["record"]["total_wall_s"] for a in row["attempt_ids"])
        if not math.isclose(total, row["all_attempts_total_wall_s"], rel_tol=1e-12):
            raise ValueError("Attempt-cost sum mismatch")
        if not 0 <= row["total_wall_s"] <= total or not math.isfinite(total):
            raise ValueError("Invalid point cost")
        selected_id = row["selected_attempt_id"]
        if selected_id not in row["attempt_ids"]:
            raise ValueError("Selected attempt missing from point history")
        selected_record = attempts[selected_id]["record"]
        objective, source_objective = row["objective"], selected_record["objective"]
        # These values describe one saved observation, not independent solves;
        # use only serialization-scale tolerance, not the target-hit tolerance.
        same_objective = ((objective is None and source_objective is None) or
                          (objective is not None and source_objective is not None and
                           math.isfinite(objective) and math.isfinite(source_objective) and
                           math.isclose(objective, source_objective, rel_tol=1e-12, abs_tol=1e-12)))
        if (any(selected_record.get(field) != row.get(field)
                for field in ("case", "cstr_size", "point", "solver")) or
                not same_objective or selected_record["accepted"] != row["accepted"] or
                not math.isclose(selected_record["total_wall_s"], row["total_wall_s"], rel_tol=1e-12)):
            raise ValueError("Selected point cost differs from its source attempt")
    prep = read_json(directory / "dynamic_preparation.json")
    by_id = {p["record"]["preparation_id"]: p["record"] for p in prep}
    if len(by_id) != 1 or next(iter(by_id.values()))["included_in_point_total_wall_s"]:
        raise ValueError("Expected one separately measured Dynamic preparation")
    return costs, next(iter(by_id.values()))["total_preparation_wall_s"]


def normalize_run(spec, events, completion, source, host):
    if host != "dantzig.ecn.purdue.edu":
        raise ValueError("NLP timing publication requires an original Dantzig trace")
    spec = {**spec, "grid_size": grid_size(spec["csv_name"])}
    oracle = problem(spec)
    if not events or not math.isfinite(completion) or completion < events[-1]["completed_elapsed_s"]:
        raise ValueError("Invalid run clock")
    previous = 0.0
    for i, event in enumerate(events, 1):
        elapsed, duration = event["completed_elapsed_s"], event["objective_wall_s"]
        if event["evaluation_index"] != i or duration < 0 or elapsed < previous or duration > elapsed - previous + 1e-9:
            raise ValueError("Invalid evaluation order/clock")
        value = oracle["objective"](event["point"])
        recorded = event.get("raw_value", event.get("value"))
        if math.isfinite(value) and (recorded is None or not math.isclose(value, recorded, rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError("Trace objective differs from the original lookup")
        previous = elapsed
    return {"spec": spec, "events": events, "completion": completion,
            "source": str(source), "overhead_host": host, "target": oracle["target"]}


def target_hit(value, target):
    return value is not None and math.isfinite(value) and abs(value - target) <= TOLERANCE * max(1, abs(target))


def reconstruct(run, costs, preparation, *, cstr_policy="exact", cache=False):
    """Charge each actual callback by default; repeated callbacks are not cache hits.

    Every selected recorded evaluation is charged regardless of lookup or NLP
    feasibility. Distinct retry attempts are not an observed callback retry
    sequence. Missing measurements stay missing. strict_* require exact size.
    Neither path replaces objectives or changes the original search path.
    """
    spec, events = run["spec"], run["events"]
    case, size = spec["case_name"], spec["grid_size"]
    measured_size = 30 if case == "cstr" and cstr_policy == "cstr30_transfer" else size
    plan = enumeration_plan(case, cstr_size=size or 30)
    logical = set(map(tuple, plan["points"]))
    box = set(map(tuple, enumeration_plan(case, cstr_size=size or 30, domain="box")["points"]))
    oracle = problem(spec)["objective"]
    identity = {"case_name": case, "grid_size": size, "csv_name": spec["csv_name"],
                "method": METHOD_NAMES[spec["method"]], "seed": spec["seed"],
                "n_starts": spec["n_starts"], "max_evals": spec["max_evaluations"],
                "cstr_cost_policy": cstr_policy, "cache_policy": "unique_point_cache" if cache else "each_callback",
                "point_cost_policy": "selected_recorded_evaluation_all_outcomes",
                "overhead_host": run["overhead_host"]}
    setup = preparation if case == "dynamic" else 0.0
    counters = Counter()
    cumulative_lookup = measured_total = screen_total = 0.0
    first_hit = first_measured_hit = None
    lookup_best = measured_best = None
    seen, ledger = set(), []
    for event in events:
        point = tuple(event["point"])
        row = costs.get((case, measured_size, point))
        value = oracle(point)
        feasible = math.isfinite(value)
        repeated = point in seen
        cache_hit = cache and repeated
        seen.add(point)
        counters["repeated_calls"] += repeated
        cumulative_lookup += event["objective_wall_s"]
        search = event["completed_elapsed_s"] - cumulative_lookup
        if search < -1e-9:
            raise ValueError("Objective time exceeds run clock")
        search = max(search, 0.0)
        known = row is not None
        logic_reject = point in box and point not in logical
        if logic_reject and feasible:
            raise ValueError("GDP logic contradicts a finite lookup value")
        if cache_hit:
            status, cost, chosen = "cache_lookup_proxy", event["objective_wall_s"], 0.0
            screen_total += cost
            counters["cache_hit_calls"] += 1
        elif known:
            status = "cstr30_transferred_measurement" if case == "cstr" and size != measured_size else "exact_model_measurement"
            cost = chosen = row["total_wall_s"]
            if not math.isfinite(cost) or cost <= 0:
                raise ValueError("Recorded point evaluation time must be positive")
            measured_total += cost
            counters["measured_calls"] += 1
            counters["unsuccessful_point_calls"] += not row["accepted"]
            counters["cstr30_transferred_calls"] += status == "cstr30_transferred_measurement"
        else:
            status = "unmeasured_point"
            cost = chosen = None
            counters["unmeasured_calls"] += 1
        if feasible:
            lookup_best = value if lookup_best is None else min(lookup_best, value)
        accepted_value = row["objective"] if known and row["accepted"] else None
        if accepted_value is not None:
            measured_best = accepted_value if measured_best is None else min(measured_best, accepted_value)
        agrees = (target_hit(accepted_value, value) if feasible else not row["accepted"]) if known else None
        counters["objective_disagreement_calls"] += agrees is False
        subtotal = setup + search + measured_total + screen_total
        scenario_time = subtotal if not counters["unmeasured_calls"] else None
        strict_time = scenario_time if not counters["cstr30_transferred_calls"] else None
        item = {**identity, "evaluation_index": event["evaluation_index"], "phase": event["phase"],
                "point": list(point), "repeated_point": repeated, "cost_status": status,
                "cost_model_cstr_size": measured_size, "recorded_lookup_wall_s": event["objective_wall_s"],
                "measured_point_all_attempts_s": row["all_attempts_total_wall_s"] if known else None,
                "charged_cost_s": cost, "selected_attempt_cost_s": chosen,
                "charged_attempt_id": row["selected_attempt_id"] if known and not cache_hit else None,
                "charged_successful_attempt_id": row["selected_attempt_id"] if feasible and known and row["accepted"] and not cache_hit else None,
                "attempt_ids": row["attempt_ids"] if known else [],
                "lookup_objective": value if feasible else None,
                "measured_nlp_objective": accepted_value, "objective_agrees": agrees,
                "lookup_incumbent": lookup_best, "measured_path_incumbent": measured_best,
                "search_prefix_s": search, "nlp_prefix_s": measured_total,
                "screen_cache_proxy_prefix_s": screen_total, "preparation_s": setup,
                "known_cost_subtotal_s": subtotal, "scenario_elapsed_s": scenario_time,
                "strict_elapsed_s": strict_time, "lookup_elapsed_s": event["completed_elapsed_s"]}
        ledger.append(item)
        if first_hit is None and target_hit(lookup_best, run["target"]):
            first_hit = {"event": item}
        if first_measured_hit is None and target_hit(measured_best, run["target"]):
            first_measured_hit = item
    search = run["completion"] - cumulative_lookup
    if search < ledger[-1]["search_prefix_s"] - 1e-9:
        raise ValueError("Completion before final objective callback")
    total = setup + search + measured_total + screen_total
    scenario_total = total if not counters["unmeasured_calls"] else None
    strict_total = scenario_total if not counters["cstr30_transferred_calls"] else None
    fh = first_hit["event"] if first_hit else {}
    summary = {**identity, "target_value": run["target"], "total_evals": len(events), "unique_points": len(seen),
               "lookup_best_value": lookup_best, "lookup_solved": target_hit(lookup_best, run["target"]),
               "measured_path_best_value": measured_best, "measured_path_target_hit": target_hit(measured_best, run["target"]),
               "lookup_completion_s": run["completion"], "search_overhead_s": search,
               "nlp_selected_attempts_s": measured_total, "screen_cache_proxy_s": screen_total,
               "preparation_s": setup, "known_cost_subtotal_s": total,
               "scenario_total_s": scenario_total, "strict_total_s": strict_total,
               "first_hit_evaluation": fh.get("evaluation_index"),
               "lookup_first_hit_s": fh.get("lookup_elapsed_s"),
               "scenario_first_hit_s": fh.get("scenario_elapsed_s"),
               "strict_first_hit_s": fh.get("strict_elapsed_s"),
               "measured_path_first_hit_s": first_measured_hit.get("scenario_elapsed_s") if first_measured_hit else None,
               "source": run["source"],
               **{name: counters[name] for name in ("measured_calls", "repeated_calls", "cache_hit_calls",
                   "cstr30_transferred_calls", "unsuccessful_point_calls",
                   "unmeasured_calls", "objective_disagreement_calls")}}
    return summary, ledger


def performance_ratios(rows, time_field):
    """Keep all-failed instances in the denominator and reject unpaired data."""
    groups = {}
    for row in rows:
        key = (row["csv_name"], row["seed"], row["n_starts"], row["max_evals"])
        groups.setdefault(key, []).append(row)
    output = []
    for key, group in groups.items():
        if Counter(r["method"] for r in group) != Counter(METHODS):
            raise ValueError(f"Unpaired performance profile: {key}")
        if any(r["scenario_total_s"] is None for r in group):
            raise ValueError("Unmeasured costs cannot enter a complete time profile")
        values = [r[time_field] if r["lookup_solved"] and r[time_field] is not None else math.inf for r in group]
        best = min(values)
        for row, value in zip(group, values):
            output.append({**row, "profile_time_field": time_field,
                           "time_ratio": value / best if math.isfinite(value) else None})
    return output


def baseline_record(row, target):
    objective = row.get("objective") if row.get("has_feasible_solution") else None
    record = {k: row.get(k) for k in ("case", "cstr_size", "instance_id", "method", "status", "termination", "has_feasible_solution",
                                       "objective", "method_wall_s", "template_wall_s", "worker_wall_s", "global_optimality_certified")}
    # Killed workers have no returned method timer; preserve the watchdog timer.
    duration = row.get("method_wall_s", row.get("worker_wall_s"))
    if duration is None or not math.isfinite(duration) or duration < 0:
        raise ValueError("Invalid GDP completion clock")
    record.update({"target_value": target, "target_hit": target_hit(objective, target),
                   "target_attained": objective is not None and math.isfinite(objective)
                                      and objective <= target + TOLERANCE * max(1, abs(target)),
                   "target_hit_definition": "absolute objective match within tolerance",
                   "target_attained_definition": "minimization objective at or below target plus tolerance",
                   "measured_total_with_preparation_s": duration + row.get("template_wall_s", 0),
                   "clock_source": "method_wall_s" if "method_wall_s" in row else "worker_wall_s_watchdog",
                   "time_kind": "measured_completion_not_first_hit"})
    return record


def baseline_comparison(directory, output, trace_runs):
    directory = Path(directory)
    selection = directory / "selection.json"
    sources = (read_json(selection)["sources"] if selection.exists()
               else [{"directory": str(directory), "methods": None}])
    records, evidence = [], []
    targets = {(r["spec"]["case_name"], r["spec"]["grid_size"]): r["target"] for r in trace_runs}
    for source in sources:
        path = Path(source["directory"])
        if selection.exists() and not path.is_absolute():
            path = ROOT / path
        summary = read_json(path / "summary.json")
        run = read_json(path / "run.json")
        for row in summary["results"]:
            if row.get("status") == "running":
                continue
            target = targets[(row["case"], row["cstr_size"])]
            record = baseline_record(row, target)
            record.update({"reported_lower_bound": row.get("reported_lower_bound"),
                           "source_cpu": run.get("cpu"), "source_host": run.get("host"),
                           "source_created_utc": run.get("created_utc"),
                           "source_directory": str(source["directory"]),
                           "nlp_solver": row.get("solver_policy", {}).get("nlp"),
                           "mip_solver": row.get("solver_policy", {}).get("mip"),
                           "solver_policy": row.get("solver_policy", {})})
            evidence.append(record)
            if source["methods"] is None or row["method"] in source["methods"]:
                records.append(record)
    keys = [(r["instance_id"], r["method"]) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate GDP instance/method across selected sources")
    flag_bound_conflicts(records, evidence)
    write_csv(output / "gdp_baseline_comparison.csv", records)
    return records


def flag_bound_conflicts(records, evidence=None):
    """Retain reported flags; reject certificates contradicted by saved incumbents."""
    if evidence is None:
        evidence = records
    for row in records:
        peers = [r for r in evidence if r["instance_id"] == row["instance_id"]
                 and r["has_feasible_solution"] and r["objective"] is not None]
        best = min((r["objective"] for r in peers), default=None)
        lower = row.get("reported_lower_bound")
        conflict = (row["method"] in {"bigm", "hull"} and lower is not None and best is not None
                    and lower > best + TOLERANCE * max(1, abs(best)))
        row["best_saved_feasible_objective"] = best
        witness = min(peers, key=lambda r: r["objective"]) if peers else {}
        row["bound_evidence_method"] = witness.get("method")
        row["bound_evidence_source_directory"] = witness.get("source_directory")
        row["bound_conflict_with_saved_solution"] = conflict
        row["solver_reported_global_optimality_certified"] = row["global_optimality_certified"]
        row["global_optimality_certified"] = bool(row["global_optimality_certified"] and not conflict)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-lookup-only", action="store_true",
                        help="Rebuild September lookup clocks only; no separate NLP estimates")
    parser.add_argument("--trace-archive", type=Path,
                        default=ROOT / "results/archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip")
    parser.add_argument("--original-archive", type=Path, default=ROOT / "results/archives/dantzig_20260910_170759_slN8tv.zip")
    parser.add_argument("--bam-archive", type=Path, default=ROOT / "dantzig_bam_20260916_231228_FNzbAA.zip")
    parser.add_argument("--fmqa", type=Path, default=ROOT / "results/archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip")
    parser.add_argument("--costs", type=Path, default=ROOT / "results/gdp_point_timings_20260922")
    parser.add_argument("--solver", choices=("gams_ipopt", "ipopth", "conopt"), default="gams_ipopt")
    parser.add_argument("--gdp-results", type=Path, default=ROOT / "results/gdp_comparison_current")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.legacy_lookup_only:
        from dantzig_timing_analysis import build
        build(args)
    else:
        if args.solver != "gams_ipopt":
            parser.error("The current trace report uses recorded GAMS/IPOPT measurements only")
        from dfo_trace_analysis import build
        build(args.trace_archive, args.output)


if __name__ == "__main__":
    main()
