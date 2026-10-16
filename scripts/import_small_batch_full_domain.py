"""Verify and import the Dantzig full-domain Small Batch archive; run no solvers."""

import argparse
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import statistics
import tempfile
import zipfile

from benchmark_analysis import runs_to_target_probability
from overnight_benchmark.common import csv_file, jsonl, read, save, sha
import process_followup_runner as runner
import small_batch_full_domain as full

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/small_batch_full_domain_20261012"
FILES = ("run.json", "summary.json", "runs.csv", "trajectories.csv",
         "evaluation_costs.csv", "completion_estimates.csv", "runtime_dfo.json", "runtime_fmqa.json")


def verify_archive(archive, directory):
    """Check the full inventory before extracting any data; never execute ZIP code."""
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)) or zipped.testzip() is not None:
            raise ValueError("Duplicate members or damaged archive")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
                raise ValueError("Unsafe archive path")
        roots = {PurePosixPath(n).parts[0] for n in names}
        if len(roots) != 1:
            raise ValueError("Expected one run directory")
        prefix = roots.pop() + "/"
        hashes = dict((name, digest) for digest, name in
                      (line.split("  ", 1) for line in zipped.read(prefix + "SHA256SUMS").decode().splitlines()))
        if set(names) != {prefix + n for n in hashes} | {prefix + "SHA256SUMS"}:
            raise ValueError("Archive inventory is incomplete")
        for name, digest in hashes.items():
            if hashlib.sha256(zipped.read(prefix + name)).hexdigest() != digest:
                raise ValueError(f"Archive checksum mismatch: {name}")
        # Write regular bytes only, never restore archived symlinks or executable metadata.
        for name in hashes:
            destination = directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(zipped.read(prefix + name))
    return len(hashes)


def audit(directory, archived_files, *, experiment=full, files=FILES):
    run, summary = read(directory / "run.json"), read(directory / "summary.json")
    previous = runner.EXPERIMENT
    runner.EXPERIMENT = experiment
    try:
        if run["kind"] != experiment.KIND or run["plan"] != experiment.plan() or run["protocol"] != experiment.PROTOCOL:
            raise ValueError("Unexpected experiment or planned settings")
        for name, digest in run["source_files_sha256"].items():
            if sha(directory / "source" / name) != digest:
                raise ValueError(f"Executed source checksum mismatch: {name}")
        reference_path = directory / "source" / full.REFERENCE
        if sha(reference_path) != sha(ROOT / full.REFERENCE):
            raise ValueError("Point measurements or frozen designs changed")
        ref = full.reference()
        point_archive = ROOT / ref["archive"]
        if sha(point_archive) != ref["archive_sha256"]:
            raise ValueError("Original point-enumeration archive changed")
        with zipfile.ZipFile(point_archive) as zipped:
            for point in ref["points"]:
                raw = zipped.read(point["source_member"])
                if (hashlib.sha256(raw).hexdigest() != point["source_sha256"]
                        or json.loads(raw) != point["measurement"]):
                    raise ValueError("Point timing differs from the original enumeration record")
        for role in getattr(experiment, "RUNTIME_ROLES", ("dfo", "fmqa")):
            identity = read(directory / f"runtime_{role}.json")
            if (identity != run["runtime"][role] or identity["host"] != "dantzig.ecn.purdue.edu"
                    or identity["affinity"]["effective_cpus"] != [6]
                    or any(identity["thread_environment"].get(k) != v for k, v in runner.THREAD_ENV.items())):
                raise ValueError("Unexpected host, CPU, thread setting, or runtime identity")
        runs, all_events = [], []
        for spec in run["plan"]:
            runner.frozen_starts(spec)
            job = directory / "jobs" / spec["job_id"]
            result = runner.saved_result(job, spec)
            if result is None or result["status"] != "completed" or result["worker_returncode"] != 0:
                raise ValueError(f"Incomplete job: {spec['job_id']}")
            record = result["result_record"]
            events = jsonl(job / result["trace"]["path"])[1:-1]
            if len(events) != 10 or result["trace"]["evaluations"] != 10:
                raise ValueError("Expected ten recorded callbacks per run")
            target = full.problem(spec)["target"]
            hit = record["best_value"] <= target + 1e-5 * max(1, abs(target))
            if record["found_optimum"] != hit:
                raise ValueError("Recorded target outcome disagrees with objective")
            rows = [{**event, "job_id": spec["job_id"], "method": spec["method"]} for event in events]
            all_events.extend(rows)
            lookup = math.fsum(e["objective_wall_s"] for e in events)
            points = {tuple(p["point"]): p for p in ref["points"]}
            cost = math.fsum(points[tuple(e["point"])]["measurement"]["total_wall_s"] for e in events)
            feasible = sum(points[tuple(e["point"])]["lookup_value"] is not None for e in events)
            runs.append({"job_id": spec["job_id"], "method": spec["method"], "seed": spec["seed"],
                "evaluations": len(events), "unique_evaluations": record["unique_evals"],
                "feasible_evaluations": feasible, "infeasible_evaluations": len(events) - feasible,
                "repeated_evaluations": sum(e["repeated_point"] for e in events),
                "best_point": record["best_point"], "best_value": record["best_value"],
                "target": target, "target_hit": hit,
                "first_hit_evaluation": next((e["evaluation_index"] for e in events
                    if e["value"] is not None and e["value"] <= target + 1e-5 * max(1, abs(target))), None),
                "recorded_method_s": record["wall_time_s"], "lookup_s": lookup, "attached_point_s": cost,
                "estimated_completion_s": record["wall_time_s"] - lookup + cost,
                "worker_wall_s": result["worker_wall_s"],
                **({"auxiliary_solver_trace": result["solver_trace"]} if "solver_trace" in result else {})})
        # Regenerate aggregate CSVs from sealed raw traces, then compare every byte.
        original = {name: (directory / name).read_bytes() for name in files if name.endswith(".csv")}
        with redirect_stdout(io.StringIO()):
            regenerated = runner.report(directory)
        for name, content in original.items():
            if (directory / name).read_bytes() != content:
                raise ValueError(f"Aggregate CSV differs from its raw records: {name}")
        if {k: v for k, v in regenerated.items() if k != "updated_utc"} != {
                k: v for k, v in summary.items() if k != "updated_utc"}:
            raise ValueError("Summary differs from raw records")
        save(directory / "summary.json", summary)
        if not (summary["all_completed"] and summary["completed_runs"] == len(run["plan"])
                and summary["evaluation_callbacks"] == 10 * len(run["plan"])
                and summary["callbacks_missing_point_cost"] == 0):
            raise ValueError("Unexpected completion or cost coverage")
    finally:
        runner.EXPERIMENT = previous
    methods = []
    for method in dict.fromkeys(spec["method"] for spec in run["plan"]):
        group = [r for r in runs if r["method"] == method]
        hits = sum(r["target_hit"] for r in group)
        median = statistics.median(r["estimated_completion_s"] for r in group)
        repeats = runs_to_target_probability(hits / len(group))
        methods.append({"method": method, "runs": len(group), "target_hits": hits,
            "feasible_evaluations": sum(r["feasible_evaluations"] for r in group),
            "infeasible_evaluations": sum(r["infeasible_evaluations"] for r in group),
            "repeated_evaluations": sum(r["repeated_evaluations"] for r in group),
            "median_completion_s": median, "runs_99": repeats, "tts99_s": repeats * median})
    return {"archived_files_verified": archived_files, "executed_source_files_verified": len(run["source_files_sha256"]),
        "elapsed_run_s": (datetime.fromisoformat(summary["updated_utc"]) - datetime.fromisoformat(run["created_utc"])).total_seconds(),
        "methods": methods, "runs": runs, "callback_counts": dict(Counter(e["method"] for e in all_events)),
        "checks": ["ZIP CRC and complete SHA256 inventory", "executed source snapshot and original point-enumeration records",
            f"{len(runs)} sealed results, shared frozen starts, full bounds and method settings",
            f"{len(all_events)} callback coordinates, objectives, incumbents, clocks and repeats",
            "aggregate CSVs regenerated byte-for-byte from raw traces", "all point costs including infeasible and repeated callbacks",
            *(["auxiliary solver trace checksums, matched start/end events and actual Bonmin invocations"]
              if getattr(experiment, "RECORD_AUXILIARY_SOLVERS", False) else [])],
        "time_formula": "method wall time - lookup call time + measured point cost for every callback",
        "measured_online_runtime": False}


def build(archive, output=OUTPUT, *, experiment=full, files=FILES):
    archive = Path(archive).resolve()
    with tempfile.TemporaryDirectory(prefix="small_batch_import_") as temporary:
        directory = Path(temporary)
        count = verify_archive(archive, directory)
        result = audit(directory, count, experiment=experiment, files=files)
        destination = ROOT / "results/archives" / archive.name
        if destination.exists() and sha(destination) != sha(archive):
            raise ValueError("Refusing to replace an existing archive with different content")
        if destination != archive:
            shutil.copy2(archive, destination)
        destination.with_suffix(".zip.sha256").write_text(f"{sha(destination)}  {destination.name}\n")
        output.mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copy2(directory / name, output / name)
        csv_file(output / "method_summary.csv", result["methods"])
        result.update(archive=destination.relative_to(ROOT).as_posix(), archive_sha256=sha(destination),
                      point_reference=full.REFERENCE, point_reference_sha256=sha(ROOT / full.REFERENCE),
                      files_sha256={name: sha(output / name) for name in (*files, "method_summary.csv")})
        save(output / "audit.json", result)
    print(json.dumps({"output": str(output), "methods": result["methods"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.archive, args.output_dir)
