"""Audit and publish the complete QHD FMQA archive without running optimizers."""

# ruff: noqa: E402 -- permit direct execution from the repository root

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fmqa_qhd_experiment as qhd
import process_followup_runner as runner
from overnight_benchmark.common import csv_file, jsonl, read, save, sha
from scripts.import_small_batch_full_domain import verify_archive

OUTPUT = ROOT / "results/fmqa_qhd_20261012"
ARCHIVE_NAME = "fmqa_qhd_20261012_034123_8kcczd4b.zip"
ARCHIVE_SHA256 = "bdcb45af02cd8885b6740abbc00835cf6626a7921e8cafa06bcc85abb290b2e3"
FLOAT_EQUIVALENTS = set()


def validate_trace(events, record, spec):
    """Independently check CSV values with the legacy auditor's four-ULP rule."""
    original = runner.problem
    oracle, values = original(spec), {}
    for event in events:
        point, recorded = tuple(event["point"]), event["raw_value"]
        actual = oracle["objective"](point)
        if math.isfinite(actual):
            if (not isinstance(recorded, (int, float)) or not math.isfinite(recorded)
                    or abs(actual - recorded) > 4 * max(math.ulp(actual), math.ulp(recorded))):
                raise ValueError("Trace objective differs from the frozen CSV oracle")
            if actual != recorded:
                FLOAT_EQUIVALENTS.add((spec["job_id"], event["evaluation_index"]))
            values[point] = recorded
        else:
            if recorded is not None:
                raise ValueError("Infeasible oracle value differs from the trace")
            values[point] = actual
    runner.problem = lambda unused: {**oracle, "objective": lambda p: values[tuple(p)]}
    try:
        _ORIGINAL_VALIDATE(events, record, spec)
    finally:
        runner.problem = original


_ORIGINAL_VALIDATE = runner.validate_trace


def publication_points():
    """Extend the visited-point table using same-model original IPOPT records."""
    from overnight_benchmark.references import verified_archive
    points = dict(qhd.measured_points())
    reference = read(ROOT / qhd.PROCESS_MANIFEST)["runtime"]
    archive, prefix, verified = verified_archive("points")
    with archive:
        for member in sorted(verified):
            if not member.startswith(prefix + "gams_ipopt/") or not member.endswith("/manifest.json"):
                continue
            manifest = json.loads(archive.read(member))
            if manifest["plan"]["case"] not in ("column", "cstr"):
                continue
            old = manifest["runtime"]
            if (manifest["config"] != {"solver": "gams_ipopt", "initialization": "auto", "time_limit_s": 60, "feasibility_tolerance": 1e-5}
                    or old["host"] != reference["host"] or old["solver_executable_sha256"] != reference["gams_sha256"]
                    or old["pyomo_version"] != reference["versions"]["pyomo"]
                    or old["adapter_sha256"]["models.py"] != sha(ROOT / "gdp_models/models.py")
                    or any(sha(ROOT / "external/dsda-gdp" / name) != digest for name, digest in old["source"]["files_sha256"].items())):
                raise ValueError("Historical point protocol differs from the primary IPOPT measurements")
            folder = member.removesuffix("manifest.json") + "records/"
            for name in sorted(n for n in verified if n.startswith(folder) and n.endswith(".json")):
                raw = archive.read(name)
                row = json.loads(raw)
                key = row["case"], str(row.get("cstr_size") or ""), tuple(row["point"])
                if key in points:
                    continue  # Preserve the selected successful retry policy.
                if row["solver"] != "gams_ipopt" or not 0 < row["total_wall_s"] < math.inf:
                    raise ValueError("Invalid historical IPOPT point")
                points[key] = {"point_evaluation_s": row["total_wall_s"],
                    "point_outcome": "accepted" if row["accepted"] else row["status"],
                    "point_source": name, "point_source_sha256": hashlib.sha256(raw).hexdigest()}
    # A separately audited Dantzig supplement can fill logical-rejection costs.
    supplement = OUTPUT / "point_supplement.json"
    if supplement.exists():
        data = read(supplement)
        if sha(ROOT / data["archive"]) != data["archive_sha256"]:
            raise ValueError("Point supplement archive changed")
        for row in data["points"]:
            key = row["case"], str(row.get("cstr_size") or ""), tuple(row["point"])
            if key in points:
                raise ValueError("Point supplement must only fill missing coordinates")
            points[key] = {"point_evaluation_s": row["total_wall_s"], "point_outcome": "preprocessing_infeasible",
                           "point_source": row["source_member"], "point_source_sha256": row["source_sha256"]}
    return points


def build(archive, output=OUTPUT):
    if sha(archive) != ARCHIVE_SHA256:
        raise ValueError("Unexpected QHD archive; refusing a different experiment")
    output.mkdir(parents=True, exist_ok=True)
    previous_experiment, previous_validator = runner.EXPERIMENT, runner.validate_trace
    runner.EXPERIMENT, runner.validate_trace = qhd, validate_trace
    qhd.configure("all")
    FLOAT_EQUIVALENTS.clear()
    try:
        with tempfile.TemporaryDirectory(prefix="fmqa_qhd_import_") as temp:
            directory = Path(temp)
            count = verify_archive(archive, directory)
            run, summary = read(directory / "run.json"), read(directory / "summary.json")
            if (run["kind"] != qhd.KIND or run["plan"] != qhd.plan()
                    or run["protocol"] != qhd.PROTOCOL or not summary["all_completed"]):
                raise ValueError("QHD frozen protocol, plan or completion mismatch")
            for name, digest in run["source_files_sha256"].items():
                if sha(directory / "source" / name) != digest:
                    raise ValueError(f"Archived source checksum: {name}")
            # Executed sources remain immutable; current plotting/runner edits may differ.
            for name in (qhd.FROZEN_PLAN, qhd.PROCESS_COSTS, qhd.PROCESS_MANIFEST,
                         qhd.GRID_COSTS, qhd.COLUMN_EXTRA, qhd.small.REFERENCE):
                if sha(ROOT / name) != run["source_files_sha256"][name]:
                    raise ValueError(f"Frozen scientific input changed: {name}")
            runtime = read(directory / "runtime_fmqa.json")
            if (runtime != run["runtime"]["fmqa"] or runtime["host"] != "dantzig.ecn.purdue.edu"
                    or runtime["pytorch"]["threads"] != 1 or runtime["pytorch"]["interop_threads"] != 1):
                raise ValueError("Unexpected QHD runtime")
            points = publication_points()
            preparation = read(ROOT / qhd.PROCESS_MANIFEST)["point_reuse_audit"]["preparations"][0]["total_preparation_wall_s"]
            process, callbacks, missing = [], [], []
            proposals, hits = 0, Counter()
            for spec in run["plan"]:
                job = directory / "jobs" / spec["job_id"]
                result = runner.saved_result(job, spec)
                if not result or result["status"] != "completed" or result["worker_returncode"] != 0:
                    raise ValueError("Incomplete QHD job")
                events = [e for e in jsonl(job / "evaluations.jsonl") if e["event"] == "evaluation"]
                candidates = jsonl(job / "proposals.jsonl")
                if (len(events) != spec["max_evaluations"] or len(candidates) != len(events) - 3
                        or [e["point"] for e in events[3:]] != [c["selected_point"] for c in candidates]):
                    raise ValueError("Evaluation/proposal budget mismatch")
                proposals += len(candidates)
                record = result["result_record"]
                target = qhd.problem(spec)["target"]
                hit = result["fmqa_state"]["has_feasible_solution"] and abs(record["best_value"] - target) <= 1e-5 * max(1, abs(target))
                hits["grid" if spec["case_name"] == "grid" else "process"] += hit
                size = Path(spec["csv_name"]).stem if spec["case_name"] == "grid" else str(spec.get("grid_size") or "")
                accepted, rejected, lookup, missing_count = [], [], [], 0
                for event in events:
                    measurement = points.get((spec["case_name"], size, tuple(event["point"])))
                    entry = {"job_id": spec["job_id"], "case": spec["case_name"], "size": size,
                             "seed": spec["seed"], "budget": spec["max_evaluations"], **event,
                             **(measurement or {"point_evaluation_s": None, "point_outcome": "measurement_missing"})}
                    callbacks.append(entry)
                    lookup.append(event["objective_wall_s"])
                    if measurement is None:
                        missing.append(entry)
                        missing_count += 1
                    else:
                        (accepted if measurement["point_outcome"] == "accepted" else rejected).append(measurement["point_evaluation_s"])
                    entry["cumulative_point_evaluation_s"] = None if missing_count else math.fsum([*accepted, *rejected])
                if spec["case_name"] != "grid":
                    overhead = record["wall_time_s"] - math.fsum(lookup)
                    prep = preparation if spec["case_name"] == "dynamic" else 0.
                    process.append({"case": spec["case_name"], "cstr_size": size, "budget": spec["max_evaluations"],
                        "method": "fmqa_sa", "backend": "pytorch_qhd_data", "job_id": spec["job_id"],
                        "seed": spec["seed"], "lookup_target_hit": hit, "recorded_dfo_s": record["wall_time_s"],
                        "recorded_lookup_s": math.fsum(lookup), "search_overhead_s": overhead,
                        "accepted_nlp_s": math.fsum(accepted), "unaccepted_nlp_s": math.fsum(rejected),
                        "dynamic_preparation_s": prep, "missing_point_costs": missing_count,
                        "cost_complete": not missing_count,
                        "estimated_total_s": None if missing_count else math.fsum([overhead, *accepted, *rejected, prep]),
                        "recorded_best_value": record["best_value"], "target_value": target,
                        "source": str((output / "process_runs.csv").relative_to(ROOT))})
            if len(process) != 140 or len(callbacks) != 58030 or proposals != 54460:
                raise ValueError("Incomplete publication inventory")
            destination = ROOT / "results/archives" / ARCHIVE_NAME
            if destination.exists() and sha(destination) != ARCHIVE_SHA256:
                raise ValueError("Conflicting existing archive")
            if archive.resolve() != destination.resolve():
                shutil.copy2(archive, destination)
            destination.with_suffix(".zip.sha256").write_text(f"{ARCHIVE_SHA256}  {ARCHIVE_NAME}\n")
            for name in ("run.json", "summary.json", "runtime_fmqa.json", "runs.csv", "completion_estimates.csv"):
                shutil.copy2(directory / name, output / name)
            for name in ("trajectories.csv", "evaluation_costs.csv"):
                (output / (name + ".gz")).write_bytes(gzip.compress((directory / name).read_bytes(), mtime=0))
            csv_file(output / "process_runs.csv", process)
            stream = io.StringIO(newline="")
            fields = list(dict.fromkeys(k for row in callbacks for k in row))
            writer = csv.DictWriter(stream, fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in callbacks)
            (output / "publication_evaluation_costs.csv.gz").write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))
            csv_file(output / "missing_point_costs.csv", missing)
            unique = {}
            for row in missing:
                key = row["case"], row["size"], tuple(row["point"])
                unique.setdefault(key, {"case": key[0], "cstr_size": key[1], "point": list(key[2]), "callbacks": 0})["callbacks"] += 1
            csv_file(output / "missing_unique_points.csv", list(unique.values()))
            files = [p for p in output.iterdir() if p.suffix in (".csv", ".gz", ".json") and p.name != "audit.json"]
            save(output / "audit.json", {
                "backend": "pytorch_qhd_data", "display_label": "FMQA-SA", "upstream_commit": qhd.COMMIT,
                "archive": str(destination.relative_to(ROOT)), "archive_sha256": ARCHIVE_SHA256,
                "archived_files_verified": count, "source_files_verified": len(run["source_files_sha256"]),
                "completed_runs": 1190, "callbacks": len(callbacks), "proposals": proposals, "target_hits": dict(hits),
                "target_tolerance": "abs(best-target) <= 1e-5 * max(1, abs(target)); feasible required",
                "missing_callbacks": len(missing), "missing_unique_points": len(unique),
                "point_sources": {"overnight_benchmark/reference_archives.json": sha(ROOT / "overnight_benchmark/reference_archives.json")},
                "process_runs_missing_cost": sum(not r["cost_complete"] for r in process),
                "csv_parse_differences_within_four_ulps": len(FLOAT_EQUIVALENTS),
                "missing_time_policy": "Unavailable, never zero or a replacement from another backend; partial groups have no aggregate time/profile",
                "files_sha256": {p.name: sha(p) for p in files},
                "import_script_sha256": sha(Path(__file__))})
    finally:
        runner.EXPERIMENT, runner.validate_trace = previous_experiment, previous_validator
    print(json.dumps({"output": str(output), "runs": 1190, "callbacks": len(callbacks), "missing_unique_points": len(unique)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    build(args.archive)
