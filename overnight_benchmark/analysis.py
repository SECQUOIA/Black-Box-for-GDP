"""Report original DFO clocks/coordinates and separately measured NLP costs."""

from collections import defaultdict
import math
from pathlib import Path
import statistics

from .common import csv_file, jsonl, point_key, read, save, sha


def lookup_runs(directory, plan, fmqa):
    from fmqa_benchmark.protocol import problem
    runs = []
    for spec in plan:
        job = directory / "lookup" / spec["job_id"]
        result = read(job / "result.json") if (job / "result.json").exists() else {}
        artifact = result.get("trace")
        paths = list((job / "lookup.traces").glob("*.jsonl"))
        if artifact:
            path = job / artifact["path"]
            if sha(path) != artifact["sha256"]:
                raise ValueError(f"Lookup trace changed: {job}")
        elif paths:
            if len(paths) != 1:
                raise ValueError(f"Ambiguous partial lookup trace: {job}")
            path = paths[0]
        else:
            path = job / "missing.jsonl"
        entries = jsonl(path)
        events = [e for e in entries if e.get("event") == "evaluation" and not e.get("exception_type")]
        oracle = problem(spec)
        for e in events:
            raw = oracle["objective"](e["point"])
            if math.isfinite(raw) and (e["value"] is None or not math.isclose(raw, e["value"], rel_tol=1e-12)):
                raise ValueError("Lookup trace value differs from frozen oracle")
        if result.get("status") == "completed":
            if [e["point"] for e in events[:spec["n_starts"]]] != spec["starting_points"]:
                raise ValueError("Lookup trace lost the original initial design")
            if len(events) != result["result_record"]["total_evals"]:
                raise ValueError("Lookup trace callback count mismatch")
        runs.append({"spec": spec, "events": events, "wall_time_s": result.get("wall_time_s"),
                     "status": result.get("status", "pending"), "target": oracle["target"],
                     "source": str(path.relative_to(directory)),
                     "dfo_wall_time_s": result.get("result_record", {}).get("wall_time_s"),
                     "recorded_best_value": result.get("result_record", {}).get("best_value"),
                     "recorded_best_point": result.get("result_record", {}).get("best_point")})
    return [*runs, *fmqa]


def requested_points(runs):
    return sorted({point_key(r["spec"]["case_name"], r["spec"]["grid_size"], e["point"])
                   for r in runs for e in r["events"]}, key=repr)


def point_costs(directory, historical):
    costs = dict(historical)
    for path in sorted((directory / "points").glob("*/result.json")):
        result = read(path)
        if result.get("status") != "completed":
            continue
        spec, record = result["spec"], result["record"]
        key = point_key(spec["case_name"], spec["grid_size"], spec["point"])
        costs[key] = {"record": record, "cost_s": record["total_wall_s"],
                      "source": str(path.relative_to(directory)), "source_kind": "new_point_measurement",
                      "source_sha256": sha(path), "preparation": result.get("preparation")}
    return costs


def timing_tables(runs, costs):
    """Keep DFO observations and NLP measurements in separate named columns."""
    run_rows, evaluations = [], []
    for run in runs:
        spec = run["spec"]
        identity = {"case": spec["case_name"], "cstr_size": spec["grid_size"],
                    "method": spec["method"], "seed": spec["seed"],
                    "budget": spec["max_evaluations"], "job_id": spec["job_id"]}
        missing, seen = 0, set()
        for e in run["events"]:
            key = point_key(spec["case_name"], spec["grid_size"], e["point"])
            item = costs.get(key)
            record = item["record"] if item else {}
            cost = item["cost_s"] if item else None
            if cost is not None and (not math.isfinite(cost) or cost <= 0):
                raise ValueError("Recorded NLP evaluation time must be positive")
            missing += item is None
            evaluations.append({**identity, "evaluation_index": e["evaluation_index"],
                "point": e["point"], "repeated_coordinate": key in seen,
                "dfo_started_elapsed_s": e.get("started_elapsed_s"),
                "dfo_completed_elapsed_s": e["completed_elapsed_s"],
                "dfo_lookup_call_wall_s": e["objective_wall_s"],
                "dfo_recorded_value": e.get("raw_value", e.get("value")),
                "nlp_evaluation_wall_s": cost, "nlp_solve_wall_s": record.get("solve_wall_s"),
                "nlp_status": record.get("status"), "nlp_termination": record.get("termination"),
                "nlp_accepted": record.get("accepted"), "nlp_objective": record.get("objective"),
                "nlp_measurement_source": item["source"] if item else None,
                "nlp_measurement_source_kind": item["source_kind"] if item else None,
                "nlp_time_measured_separately_from_dfo": True})
            seen.add(key)
        run_rows.append({**identity, "status": run["status"],
            "dfo_wall_time_s": run.get("dfo_wall_time_s"),
            "trace_runner_wall_s": run["wall_time_s"],
            "recorded_best_value": run.get("recorded_best_value"),
            "recorded_best_point": run.get("recorded_best_point"),
            "completed_evaluations": len(run["events"]), "distinct_coordinates": len(seen),
            "callbacks_missing_nlp_measurement": missing, "dfo_trace_source": run["source"]})
    return run_rows, evaluations


def summarize(directory, fmqa, historical, reuse_audit):
    directory = Path(directory)
    run = read(directory / "run.json")
    traces = lookup_runs(directory, run["lookup_plan"], fmqa)
    keys = requested_points(traces)
    costs = point_costs(directory, historical)
    rows, evaluations = timing_tables(traces, costs)
    output = directory / "analysis"
    csv_file(output / "dfo_runs.csv", rows)
    csv_file(output / "evaluation_timings.csv", evaluations)
    point_rows = []
    for key in keys:
        item = costs.get(key)
        record = item["record"] if item else {}
        point_rows.append({"case": key[0], "cstr_size": key[1], "point": list(key[2]),
            "nlp_evaluation_wall_s": item["cost_s"] if item else None,
            "nlp_solve_wall_s": record.get("solve_wall_s"), "status": record.get("status"),
            "termination": record.get("termination"), "accepted": record.get("accepted"),
            "objective": record.get("objective"), "candidate_objective": record.get("candidate_objective"),
            "gams_model_status": record.get("gams_model_status"),
            "gams_solve_status": record.get("gams_solve_status"),
            "source": item["source"] if item else None,
            "source_kind": item["source_kind"] if item else None,
            "source_sha256": item["source_sha256"] if item else None})
    csv_file(output / "point_timings.csv", point_rows)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["case"], row["cstr_size"], row["budget"], row["method"])].append(row)
    summary = []
    for (case, size, budget, method), group in grouped.items():
        clocks = [r["dfo_wall_time_s"] for r in group if r["dfo_wall_time_s"] is not None]
        summary.append({"case": case, "cstr_size": size, "budget": budget, "method": method,
                        "planned": len(group), "recorded_dfo_clocks": len(clocks),
                        "mean_dfo_wall_time_s": statistics.mean(clocks) if clocks else None,
                        "errors": sum(r["status"] in {"error", "setup_error"} for r in group)})
    csv_file(output / "dfo_time_summary.csv", summary)
    lines = ["# Original DFO runtime and separate coordinate NLP timings", "",
        "The original DSDA/RBFOpt/BAM lookup implementations and settings are unchanged. Existing Dantzig FMQA traces are reused. NLP results are never supplied back to the search.", "",
        "- `dfo_runs.csv`: recorded DFO run time, result and trace identity.",
        "- `evaluation_timings.csv`: actual ordered coordinates, DFO timestamps and linked separate NLP measurements.",
        "- `point_timings.csv`: one recorded NLP evaluation time per visited coordinate, including unsuccessful/preprocessing-infeasible points.", "",
        "`nlp_evaluation_wall_s` includes model preparation, preprocessing, solver invocation and validation. `nlp_solve_wall_s` is a subset, not an additional cost. Preprocessing rejection can have zero solver time but positive evaluation time. Missing measurements remain blank. Solver failures are not proofs of global infeasibility.", "",
        "Repeated coordinates reference the same separate point measurement; this is not an NLP solve inside each DFO callback. DFO time and NLP costs are not relabelled as a measured combined runtime. Dynamic one-time preparation is saved separately in `dynamic_preparations.json`.", "",
        "| Case | Size | Budget | Method | Recorded/planned | Mean DFO seconds |",
        "|---|---:|---:|---|---:|---:|"]
    for row in summary:
        mean = row["mean_dfo_wall_time_s"]
        duration = f"{mean:.6f}" if mean is not None else "pending"
        lines.append(f"| {row['case']} | {row['cstr_size'] or ''} | {row['budget']} | {row['method']} | {row['recorded_dfo_clocks']}/{row['planned']} | {duration} |")
    (output / "README.md").write_text("\n".join(lines) + "\n")
    preparations = list(reuse_audit.get("preparations", []))
    preparations += [item["preparation"] for key, item in costs.items() if key in keys and item.get("preparation")]
    save(output / "dynamic_preparations.json", preparations)
    audit = {"new_dfo_runs_planned": len(run["lookup_plan"]), "original_fmqa_traces_reused": len(fmqa),
             "dfo_jobs_finished": sum(r["status"] != "pending" for r in traces) - len(fmqa),
             "visited_coordinates": len(keys), "coordinates_with_nlp_measurement": sum(k in costs for k in keys),
             "missing_coordinate_measurements": sum(k not in costs for k in keys),
             "reused_coordinate_measurements": sum(k in historical for k in keys),
             "point_reuse_audit": reuse_audit}
    save(output / "audit.json", audit)
    return audit
