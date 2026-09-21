"""Validate process evaluation traces and inventory GDP timing measurements.

Legacy CSV Time is solver user_time, not measured end-to-end runtime.
Missing or ambiguous point costs remain missing; Global_Time is never summed.
"""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import zipfile

import case_study_benchmark as cases
from case_studies.common import generate_lhc_starting_points
from case_studies.column_case import COLUMN_FEASIBLE_OBJECTIVES
from case_studies.cstr_case import load_cstr_case_data
from case_studies.dynamic_case import DYNAMIC_FEASIBLE_OBJECTIVES
from case_studies.small_batch_case import SMALL_BATCH_FEASIBLE_OBJECTIVES
from evaluation_trace import finite_value, validate_trace_artifacts


def reference_audit(reference):
    """Require identical original designs/data and unchanged optimizer wrappers."""
    reference = Path(reference)
    name = "process_case_studies.manifest.json"
    if reference.is_dir():
        raw = (reference / name).read_bytes()
    else:
        with zipfile.ZipFile(reference) as archive:
            matches = [p for p in archive.namelist() if p.endswith("/" + name) or p == name]
            if len(matches) != 1:
                raise ValueError("Expected one original process manifest")
            raw = archive.read(matches[0])
    old = json.loads(raw)
    if old["run"]["status"] != "completed":
        raise ValueError("Original reference is incomplete")
    matrix = cases.build_run_matrix()
    designs = cases._initial_design_hashes(matrix, 3)
    if designs != old["provenance"]["initial_design"]["designs"]:
        raise ValueError("Starting points differ from the original Dantzig designs")
    if cases._planned_run_keys(matrix, cases.DEFAULT_METHODS, 3) != old["run"]["completed_run_keys"]:
        raise ValueError("Run matrix differs from original Dantzig matrix")
    permitted = {"instrumentation.py", "case_study_benchmark.py"}
    changed = []
    for category in ("source_files_sha256", "data_files_sha256"):
        for relative, expected in old["provenance"][category].items():
            actual = hashlib.sha256((cases.BASE_DIR / relative).read_bytes()).hexdigest()
            if actual != expected:
                if category == "source_files_sha256" and relative in permitted:
                    changed.append(relative)
                else:
                    raise ValueError(f"Original algorithm/data changed: {relative}")
    return {"reference_manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "matched_initial_designs": len(designs), "planned_runs": 417,
            "instrumentation_changes": changed,
            "note": "New trajectories; identical starts do not prove identical old paths."}


def case_data(key):
    case = key["case_name"]
    if case == "dynamic":
        return DYNAMIC_FEASIBLE_OBJECTIVES, {}
    if case == "cstr":
        objectives = load_cstr_case_data(key["grid_size"])["feasible_objectives"]
    elif case == "column":
        objectives = COLUMN_FEASIBLE_OBJECTIVES
    else:
        objectives = SMALL_BATCH_FEASIBLE_OBJECTIVES
    rows = defaultdict(list)
    path = cases.BASE_DIR / "case_study_data" / case / key["csv_name"]
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            point = tuple(int(row[k]) for k in ("x", "y", "z") if k in row)
            rows[point].append(row)
    return objectives, rows


def legacy_cost(rows, case):
    """Use the enumeration call; exclude the writer's extra Final re-solve."""
    if case == "dynamic":
        return None, "no_timing_table"
    if not rows:
        return None, "missing_record"
    enumeration_rows = [row for row in rows if row.get("Status") != "Final"]
    if not enumeration_rows:
        return None, "final_only"
    if len(enumeration_rows) != 1:
        return None, "duplicate_records"
    try:
        cost = float(enumeration_rows[0]["Time"])
    except (KeyError, TypeError, ValueError):
        return None, "invalid_time"
    if not math.isfinite(cost) or cost < 0:
        return None, "invalid_time"
    return cost, "single_record" if len(rows) == 1 else "enumeration_record_excluding_final"


def read_completed_runs(path):
    path = Path(path)
    manifest = json.loads(path.with_suffix(".manifest.json").read_text())
    if not manifest["protocol"].get("trace_evaluations"):
        raise ValueError("Input was not run with --trace-evaluations")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["output"]["csv_sha256"]:
        raise ValueError("Result CSV checksum mismatch")
    oracle_hashes = dict(manifest["provenance"]["data_files_sha256"])
    oracle_hashes.update({name: digest for name, digest in manifest["provenance"]["source_files_sha256"].items()
                          if name.endswith("_case.py")})
    for name, expected in oracle_hashes.items():
        if hashlib.sha256((cases.BASE_DIR / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Lookup/timing input changed since the run: {name}")
    with path.open(newline="") as handle:
        records = [cases._deserialize_result_record(row) for row in csv.DictReader(handle)]
    validate_trace_artifacts(manifest, path, records)
    for artifact, key, record in zip(manifest["evaluation_traces"],
                                     manifest["run"]["completed_run_keys"], records):
        trace_path = path.parent / artifact["path"]
        entries = [json.loads(line) for line in trace_path.read_text().splitlines()]
        yield key, record, entries[1:-1]


def analyze(inputs, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    evaluations, runs, requests = [], [], {}
    seen_runs = set()
    for path in inputs:
        for key, record, events in read_completed_runs(path):
            identity = json.dumps(key, sort_keys=True)
            if identity in seen_runs:
                raise ValueError(f"Duplicate run across inputs: {identity}")
            seen_runs.add(identity)
            objectives, source_rows = case_data(key)
            target = min(objectives.values())
            lb, ub = (cases.CSTR_LOWER_BOUNDS, [key["grid_size"]] * 2) if key["case_name"] == "cstr" else cases.CASE_BOUNDS[key["case_name"]]
            starts = generate_lhc_starting_points(len(lb), key["n_starts"], lb, ub, key["seed"])
            if [e["point"] for e in events[:key["n_starts"]]] != [list(p) for p in starts]:
                raise ValueError("Recorded initial coordinates differ from shared design")
            prefix = {k: key[k] for k in ("case_name", "csv_name", "method", "seed", "n_starts", "max_evaluations")}
            first_hit, costs, unique_costs, seen_points = None, [], {}, set()
            for event in events:
                point = tuple(event["point"])
                if event["repeated_point"] != (point in seen_points):
                    raise ValueError("Incorrect repeated-point flag")
                seen_points.add(point)
                penalty = math.nan if key["method"] == "bam" else (1e6 if key["case_name"] in ("column", "dynamic") else math.inf)
                expected, kind = finite_value(objectives.get(point, penalty))
                if event["value"] != expected or event["value_kind"] != kind:
                    raise ValueError(f"Callback value differs from lookup objective: {point}")
                historical_rows = source_rows.get(point, [])
                cost, cost_status = legacy_cost(historical_rows, key["case_name"])
                enumeration_rows = [row for row in historical_rows if row.get("Status") != "Final"]
                legacy_row = enumeration_rows[0] if len(enumeration_rows) == 1 else {}
                legacy_value, legacy_kind = finite_value(float(legacy_row["Objective"])) if legacy_row else (None, "missing")
                if point in objectives and legacy_row and legacy_value != objectives[point]:
                    cost, cost_status = None, "objective_mismatch"
                costs.append(cost)
                unique_costs[point] = cost
                if first_hit is None and point in objectives and abs(objectives[point] - target) <= 1e-5 * max(1, abs(target)):
                    first_hit = event
                metadata = {
                    "point": json.dumps(list(point)),
                    "lookup_has_finite_value": point in objectives,
                    "lookup_value": objectives.get(point),
                    "legacy_row_count": len(historical_rows),
                    "legacy_objective": legacy_value, "legacy_objective_kind": legacy_kind,
                    "legacy_status": legacy_row.get("Status"),
                    "legacy_solver_user_time_s": cost,
                    "legacy_time_status": cost_status,
                }
                evaluations.append({**prefix, **metadata,
                    **{k: event[k] for k in ("evaluation_index", "phase", "repeated_point", "value", "value_kind", "objective_wall_s", "completed_elapsed_s")}})
                request_key = (key["csv_name"], point)
                if request_key not in requests:
                    requests[request_key] = {"case_name": key["case_name"], "csv_name": key["csv_name"], **metadata, "callback_count": 0}
                requests[request_key]["callback_count"] += 1
            complete = all(c is not None for c in costs)
            runs.append({**prefix, "total_evals": len(events),
                "unique_points": len(unique_costs),
                "lookup_run_wall_s": record["wall_time_s"],
                "first_hit_evaluation": first_hit["evaluation_index"] if first_hit else None,
                "first_hit_lookup_elapsed_s": first_hit["completed_elapsed_s"] if first_hit else None,
                "legacy_cost_covered_calls": sum(c is not None for c in costs),
                "legacy_known_cost_sum_s": sum(c for c in costs if c is not None),
                "legacy_full_call_cost_estimate_s": sum(costs) if complete else None,
                "legacy_unique_point_cost_estimate_s": sum(unique_costs.values()) if complete else None,
            })
    for name, rows in (("evaluation_points.csv", evaluations), ("run_summary.csv", runs),
                       ("nlp_point_requests.csv", list(requests.values()))):
        if not rows:
            raise ValueError("No completed traced runs to analyze")
        with (output / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summary = {"runs": len(runs), "objective_calls": len(evaluations),
               "distinct_problem_points": len(requests),
               "runs_with_all_legacy_costs": sum(r["legacy_full_call_cost_estimate_s"] is not None for r in runs),
               "inputs": [{"path": str(p), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                           "manifest_sha256": hashlib.sha256(Path(p).with_suffix(".manifest.json").read_bytes()).hexdigest()} for p in inputs],
               "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "timing_note": "Legacy Time is solver user_time; sums are historical estimates, not measured GDP wall time. Missing/duplicate costs are not zero. First-hit timestamps measure new lookup runs only."}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-reference", type=Path)
    args = parser.parse_args()
    if args.check_reference:
        print(json.dumps(reference_audit(args.check_reference), indent=2))
    if args.inputs:
        if args.output is None:
            parser.error("--output is required with result CSV inputs")
        print(json.dumps(analyze(args.inputs, args.output), indent=2))
    elif not args.check_reference:
        parser.error("Supply input CSVs or --check-reference")


if __name__ == "__main__":
    main()
