"""Verify and optionally extract every RBFOpt callback trajectory; no solves.

Requires pandas for the historical CSV parser. Archived Python is never run.
Default mode verifies saved files; --extract creates the byte-preserved copies.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = HERE.parent / "archives/grid_trace_rbfopt_20261008_190603_og2app39.zip"
sys.path.insert(0, str(ROOT))
from evaluation_trace import validate_events


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def table(raw):
    return list(csv.DictReader(io.StringIO(raw.decode())))


def cell(value):
    return json.dumps(value) if isinstance(value, (list, dict)) else "" if value is None else str(value)


def publish(relative, content, extract):
    path = HERE / relative
    if extract:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            require(path.read_bytes() == content, f"Refusing to overwrite different data: {path}")
        else:
            path.write_bytes(content)
    require(path.read_bytes() == content, f"Saved file differs: {path}")


def main(extract=False):
    archive_hash = sha(ARCHIVE.read_bytes())
    require(archive_hash == Path(str(ARCHIVE) + ".sha256").read_text().split()[0], "Archive hash")
    with zipfile.ZipFile(ARCHIVE) as z:
        names = z.namelist()
        prefix = ARCHIVE.stem + "/"
        require(len(names) == len(set(names)), "Duplicate ZIP members")
        for item in z.infolist():
            path = PurePosixPath(item.filename)
            require(item.filename.startswith(prefix) and not path.is_absolute()
                    and ".." not in path.parts and not stat.S_ISLNK(item.external_attr >> 16),
                    "Unsafe archive member")
        require(z.testzip() is None, "ZIP CRC")
        data = {name[len(prefix):]: z.read(name) for name in names}
    manifest = {}
    for line in data["SHA256SUMS"].decode().splitlines():
        expected, name = line.split("  ", 1)
        require(name not in manifest, "Duplicate manifest entry")
        manifest[name] = expected
        require(sha(data[name]) == expected, f"Member hash: {name}")
    require(set(manifest) == set(data) - {"SHA256SUMS"}, "Manifest coverage")
    run = json.loads(data["run.json"])
    require(run["kind"] == "grid_dfo_callback_trace_v1" and run["config"]["method"] == "rbfopt", "Run identity")
    for name, expected in run["source_sha256"].items():
        require(sha(data["source/" + name]) == expected, f"Frozen source: {name}")
    require((ROOT / "evaluation_trace.py").read_bytes() == data["source/evaluation_trace.py"], "Local trace validator changed")
    metadata = json.loads(data["source/fmqa_benchmark/reference/grid/reference.json"])
    for name, expected in metadata["data_files_sha256"].items():
        require(sha(data["source/" + name]) == expected, f"Reference grid hash: {name}")
    for name, expected in metadata["files_sha256"].items():
        require(sha(data["source/fmqa_benchmark/reference/grid/" + name]) == expected, f"Reference hash: {name}")
    designs = json.loads(data["source/fmqa_benchmark/reference/grid/comparison_audit.json"])["grid_designs"]
    designs = {(d["csv_name"], d["seed"]): d["starting_points"] for d in designs}
    historical = [r for r in table(data["source/fmqa_benchmark/reference/grid/original.csv"]) if r["method"] == "RBFOpt"]
    expected_plan = []
    for row in historical:
        name, seed, budget = row["csv_name"], int(row["seed"]), int(row["max_evals"])
        points = designs[name, seed]
        expected_plan.append({"csv_name": name, "case_name": "grid", "grid_size": None,
            "method": "rbfopt", "seed": seed, "n_starts": 3, "max_evaluations": budget,
            "starting_points": points,
            "initial_design_sha256": sha(json.dumps(points, separators=(",", ":")).encode()),
            "job_id": f"grid_{PurePosixPath(name).stem}_B{budget}_seed{seed}_rbfopt"})
    require(run["plan"] == expected_plan and len(expected_plan) == 1050, "Frozen ordered plan")
    grids, decimals = {}, {}
    for name, raw in data.items():
        if name.startswith("source/benchmark_grids/") and name.endswith(".csv"):
            key = PurePosixPath(name).name
            grids[key] = {(int(r.x), int(r.y)): float(r.z_norm) for r in pd.read_csv(io.BytesIO(raw)).itertuples(index=False)}
            decimals[key] = {(int(r["x"]), int(r["y"])): float(r["z_norm"]) for r in table(raw)}
            require(set(grids[key]) == {(x, y) for x in range(31) for y in range(31)}, "Grid coverage")
    require(len(grids) == 21, "Grid count")
    require({(s["csv_name"], s["seed"], s["max_evaluations"]) for s in run["plan"]}
            == {(n, s, b) for n in grids for s in range(10) for b in [10, 30, 50, 70, 100]}, "Matrix coverage")
    benchmarks, evaluations = table(data["benchmark.csv"]), table(data["evaluations.csv"])
    require(len(benchmarks) == 1050 and len(evaluations) == 54600, "Export row counts")
    markers = defaultdict(list)
    for name in data:
        if name.startswith("jobs/") and name.endswith("/complete.json"):
            markers[PurePosixPath(name).parts[1]].append(name)
    require(set(markers) == {s["job_id"] for s in run["plan"]}, "Completed job coverage")
    require(not any(n.endswith(".partial.jsonl") for n in data), "Unexpected partial trace")
    trajectories, index, expected_evaluations, differences = {}, [], [], []
    per_grid, per_budget, phases = defaultdict(Counter), defaultdict(Counter), Counter()
    all_points, observed_values, repeated = set(), {}, 0
    for position, spec in enumerate(run["plan"]):
        job, name, budget = spec["job_id"], spec["csv_name"], spec["max_evaluations"]
        require(len(markers[job]) == 1, f"Completed attempts: {job}")
        attempt = str(PurePosixPath(markers[job][0]).parent)
        raw_result = data[attempt + "/result.json"]
        require(sha(raw_result) == json.loads(data[markers[job][0]])["result_sha256"], f"Result seal: {job}")
        result = json.loads(raw_result)
        require(result["spec"] == spec and result["status"] == "completed" and not result["budget_exceeded"], f"Result: {job}")
        path = attempt + "/" + result["trace"]["path"]
        raw = data[path]
        require(sha(raw) == result["trace"]["sha256"], f"Trace seal: {job}")
        entries = [json.loads(line) for line in raw.splitlines()]
        record, events = result["result_record"], entries[1:-1]
        require(entries[0]["event"] == "run_start" and entries[0]["run_key"] == spec
                and entries[0]["trace_version"] == 1, f"Header: {job}")
        require(entries[-1]["event"] == "run_complete" and entries[-1]["result_record"] == record, f"Footer: {job}")
        validate_events(events, record)
        require(len(events) == budget == result["trace"]["evaluations"] == record["solver_evalcount"], f"Budget/native count: {job}")
        require(record["csv_name"] == name and record["method"] == "RBFOpt" and record["seed"] == spec["seed"]
                and record["max_evals"] == budget and record["n_starts"] == 3
                and record["initial_evals"] == 3 and record["adaptive_evals"] == budget - 3, f"Record identity: {job}")
        require(benchmarks[position] == {k: cell(v) for k, v in record.items()}, f"Benchmark export: {job}")
        require([e["point"] for e in events[:3]] == spec["starting_points"], f"Initial design: {job}")
        require(result["lookup_wall_s"] == sum(e["objective_wall_s"] for e in events), f"Lookup sum: {job}")
        require(events[-1]["completed_elapsed_s"] <= result["search_wall_s"] <= entries[-1]["runner_elapsed_s"], f"Search clock: {job}")
        seen, best, previous = set(), math.inf, 0.0
        for j, event in enumerate(events):
            point = tuple(event["point"])
            require(len(point) == 2 and all(type(x) is int and 0 <= x <= 30 for x in point), f"Point: {job}")
            requested = event["requested_point"]
            require(len(requested) == 2 and all(math.isfinite(x) for x in requested)
                    and [int(round(x)) for x in requested] == list(point), f"Requested point: {job}")
            require(event["event"] == "evaluation" and event["phase"] == ("initial" if j < 3 else "adaptive"), f"Phase: {job}")
            value, reference = event["value"], grids[name][point]
            require(event["value_kind"] == event["incumbent_kind"] == "finite" and math.isfinite(value), f"Finite value: {job}")
            delta = abs(value - reference)
            require(delta <= 2 * math.ulp(reference), f"Grid CSV value: {job}, {j+1}")
            if delta:
                decimal = decimals[name][point]
                require(abs(value - decimal) <= 2 * math.ulp(decimal), f"Raw decimal value: {job}, {j+1}")
                differences.append({"job_id": job, "evaluation_index": j + 1, "point": list(point),
                    "recorded": value, "local_parser": reference, "raw_decimal": decimal,
                    "abs_difference": delta, "ulps": delta / math.ulp(reference)})
            key = (name, *point)
            require(key not in observed_values or observed_values[key] == value, f"Cross-run value: {job}")
            observed_values[key] = value
            best = min(best, value)
            require(event["incumbent"] == best and event["repeated_point"] == (point in seen), f"Incumbent/repeat: {job}")
            seen.add(point)
            start, end, duration = (event[k] for k in ["started_elapsed_s", "completed_elapsed_s", "objective_wall_s"])
            require(all(math.isfinite(v) for v in [start, end, duration]) and previous <= start <= end
                    and 0 <= duration <= end - start + 1e-9, f"Callback clock: {job}")
            previous = end
            expected = {"job_id": job, "csv_name": name, "method": "rbfopt", "seed": spec["seed"],
                        "max_evals": budget, "trace_path": path, **event}
            expected_evaluations.append({k: cell(v) for k, v in expected.items()})
            all_points.add(key)
            phases[event["phase"]] += 1
            repeated += event["repeated_point"]
        require(record["unique_evals"] == len(seen) and record["best_value"] == best, f"Final objective: {job}")
        best_point = tuple(record["best_point"])
        require(best_point in seen and observed_values[(name, *best_point)] == best, f"Best point: {job}")
        saved_path = f"trajectories/{job}.jsonl"
        trajectories[saved_path] = raw
        index.append({"job_id": job, "csv_name": name, "seed": spec["seed"], "max_evals": budget,
            "callbacks": len(events), "unique_points": len(seen), "trajectory_path": saved_path,
            "archive_trace_path": path, "trajectory_sha256": sha(raw), "result_sha256": sha(raw_result),
            "search_wall_s": result["search_wall_s"], "lookup_wall_s": result["lookup_wall_s"]})
        per_grid[name].update(runs=1, callbacks=len(events))
        per_budget[budget].update(runs=1, callbacks=len(events))
    require(evaluations == expected_evaluations, "Combined evaluations differ from per-run traces")
    require({r["archive_trace_path"] for r in index} == {n for n in data if n.endswith(".jsonl")}, "Unaccounted trace")
    require(json.loads(data["visited_points.json"]) == [{"csv_name": n, "point": [x, y]} for n, x, y in sorted(all_points)], "Unique point export")
    require(len(all_points) == 7514, "Unique point count")
    summary = json.loads(data["summary.json"])
    expected_summary = {"planned_runs": 1050, "completed_runs": 1050, "evaluation_callbacks": 54600,
                        "unique_grid_points": 7514, "all_completed": True}
    require(all(summary[k] == v for k, v in expected_summary.items()), "Summary counts")
    report = {"status": "PASS", "archive": str(ARCHIVE.relative_to(HERE.parent)), "archive_sha256": archive_hash,
        "checksummed_files": len(manifest), "verified_source_files": len(run["source_sha256"]), **expected_summary,
        "saved_trajectory_files": len(trajectories), "missing_cases": [], "callback_sequence_gaps": 0,
        "initial_callbacks": phases["initial"], "adaptive_callbacks": phases["adaptive"],
        "within_run_repeated_callbacks": repeated, "combined_csv_mismatches": 0,
        "local_csv_parser": {"pandas": pd.__version__, "differing_callbacks": len(differences),
            "maximum_abs_difference": max((d["abs_difference"] for d in differences), default=0),
            "maximum_ulp_difference": max((d["ulps"] for d in differences), default=0),
            "tolerance": "Two binary64 ULPs against local pandas; differing values also within two ULPs of raw decimal. Exact checks for traces, exports, incumbents and cross-run values."},
        "per_grid": {n: dict(c, unique_points=sum(k[0] == n for k in all_points)) for n, c in sorted(per_grid.items())},
        "per_budget": {str(b): dict(c) for b, c in sorted(per_budget.items())},
        "scope": "Actual objective callbacks, preserving order, initial points and repeats. Coordinates are grid indices 0..30. These are fresh reruns, not reconstructed historical trajectories. Internal candidates/cache operations without callbacks are absent. Lookup timings do not include GDP/NLP solves."}
    for name in ["benchmark.csv", "evaluations.csv", "visited_points.json", "run.json", "summary.json", "progress.json"]:
        publish("raw/" + name, data[name], extract)
    for name, content in trajectories.items():
        publish(name, content, extract)
    require({p.name for p in (HERE / "trajectories").iterdir()} == {PurePosixPath(p).name for p in trajectories}, "Saved trajectory coverage")
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(index[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(index)
    publish("trajectory_index.csv", out.getvalue().encode(), extract)
    if extract:
        for name, obj in [("verification.json", report), ("parser_roundoff.json", differences)]:
            publish(name, (json.dumps(obj, indent=2, allow_nan=False) + "\n").encode(), True)
    else:
        # The original audit records the publishing host's parser differences.
        # A different platform may parse these same decimal strings differently.
        saved = json.loads((HERE / "verification.json").read_text())
        require({k: v for k, v in saved.items() if k != "local_csv_parser"}
                == {k: v for k, v in report.items() if k != "local_csv_parser"}, "Saved audit counts")
        saved_differences = json.loads((HERE / "parser_roundoff.json").read_text())
        require(len(saved_differences) == saved["local_csv_parser"]["differing_callbacks"], "Saved roundoff audit")
        for row in saved_differences:
            case = next(s for s in run["plan"] if s["job_id"] == row["job_id"])
            value = observed_values[(case["csv_name"], *row["point"])]
            require(value == row["recorded"] and abs(value - row["local_parser"]) == row["abs_difference"]
                    and row["abs_difference"] <= 2 * math.ulp(row["local_parser"]), "Saved parser observation")
    print(json.dumps({k: report[k] for k in ["status", "checksummed_files", "saved_trajectory_files", "evaluation_callbacks",
          "unique_grid_points", "within_run_repeated_callbacks", "local_csv_parser"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true")
    main(parser.parse_args().extract)
