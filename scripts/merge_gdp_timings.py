"""Publish checked GDP point timings; retain attempts and never mix solvers."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil


SOLVERS = ("gams_ipopt", "ipopth", "conopt")
CASES = {"column": 64, "cstr_30": 465, "small_batch": 27, "dynamic": 37}
RETRY_POINTS = {(5, 1), (5, 3), (6, 2), (6, 4), (23, 2), (26, 2), (29, 3)}
TIMERS = ("setup_wall_s", "preprocess_wall_s", "feasible_initialization_wall_s",
          "solve_wall_s", "total_wall_s", "worker_process_wall_s")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def json_lines(path, rows):
    path.write_text("".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows))


def checked_source(directory):
    directory = Path(directory).resolve()
    checks = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        name = PurePosixPath(relative)
        path = directory / relative
        if name.is_absolute() or ".." in name.parts or not path.resolve().is_relative_to(directory):
            raise ValueError(f"Unsafe source path: {relative}")
        if relative in checks or digest(path) != expected:
            raise ValueError(f"Duplicate source or checksum mismatch: {relative}")
        checks[relative] = expected
    if "run.json" not in checks:
        raise ValueError("Missing checked run manifest")
    return directory, checks, json.loads((directory / "run.json").read_text())


def checked_json(directory, checks, relative):
    if relative not in checks:
        raise ValueError(f"Source was not checksummed: {relative}")
    return json.loads((directory / relative).read_text())


def point_key(record):
    return (record["case"], record.get("cstr_size"), tuple(record["point"]), record["solver"])


def validate_record(record):
    if record["case"] == "cstr" and record.get("cstr_size") != 30:
        raise ValueError("Only CSTR30 measurements belong in this dataset")
    if record["solver"] not in SOLVERS:
        raise ValueError("Unexpected solver")
    for field in TIMERS:
        value = record.get(field)
        if value is not None and (not isinstance(value, (float, int)) or
                                  not math.isfinite(value) or value < 0):
            raise ValueError(f"Invalid timing: {field}")
    if record.get("total_wall_s") is None:
        raise ValueError("Missing evaluation time; do not substitute zero")
    if record["accepted"]:
        objective, violation = record.get("objective"), record.get("max_primal_violation")
        if (objective is None or not math.isfinite(objective) or violation is None or
                not math.isfinite(violation) or violation > record["feasibility_tolerance"] or
                record.get("gams_solve_status") != 1 or record.get("gams_model_status") not in (1, 2)):
            raise ValueError("Accepted record failed objective/primal/GAMS validation")


def attempt(directory, checks, relative, kind):
    record = checked_json(directory, checks, relative)
    validate_record(record)
    return {"attempt_id": f"{directory.name}/{relative}", "run_id": directory.name,
            "source_record": relative, "source_record_sha256": checks[relative],
            "attempt_kind": kind, "record": record}


def select_points(attempts):
    """Original per-solver measurement, overridden only by its explicit retry."""
    groups = defaultdict(list)
    identifiers = set()
    for item in attempts:
        if item["attempt_id"] in identifiers:
            raise ValueError("Duplicate attempt ID")
        identifiers.add(item["attempt_id"])
        validate_record(item["record"])
        groups[point_key(item["record"])].append(item)
    selected = []
    for key, group in sorted(groups.items()):
        initial = [a for a in group if a["attempt_kind"] == "initial"]
        retries = [a for a in group if a["attempt_kind"] == "retry"]
        if len(initial) != 1 or len(retries) > 1 or len(initial) + len(retries) != len(group):
            raise ValueError(f"Ambiguous attempt history: {key}")
        original = initial[0]
        chosen = original
        if retries:
            retry = retries[0]
            if key[:2] != ("cstr", 30) or key[2] not in RETRY_POINTS or key[3] != "gams_ipopt":
                raise ValueError("Unexpected retry coordinate or solver")
            if original["record"]["accepted"] or not retry["record"]["accepted"]:
                raise ValueError("Retry must repair a previously nonaccepted point")
            if original["record"].get("source") != retry["record"].get("source"):
                raise ValueError("Original model source differs across attempts")
            chosen = retry
        record = chosen["record"]
        selected.append({
            **{k: record.get(k) for k in ("case", "cstr_size", "point", "solver", "accepted",
                "objective", "candidate_objective", "status", "termination", "initialization",
                "max_primal_violation", "preparation_id", "gams_solve_status", "gams_model_status", *TIMERS)},
            "selected_attempt_id": chosen["attempt_id"],
            "selection": "successful_retry" if retries else "original",
            "attempt_ids": [a["attempt_id"] for a in initial + retries],
            "attempt_count": len(group),
            "all_attempts_total_wall_s": sum(a["record"]["total_wall_s"] for a in group),
        })
    return selected


def summarize(points, attempts):
    groups = defaultdict(list)
    for row in points:
        groups[(row["case"], row["cstr_size"], row["solver"])].append(row)
    return {"schema_version": 1, "point_solver_records": len(points), "attempt_records": len(attempts),
            "retry_records": sum(a["attempt_kind"] == "retry" for a in attempts),
            "groups": [{"case": key[0], "cstr_size": key[1], "solver": key[2],
                        "points": len(rows), "accepted": sum(r["accepted"] for r in rows),
                        "statuses": dict(Counter(r["status"] for r in rows)),
                        "selected_total_wall_s": sum(r["total_wall_s"] for r in rows),
                        "all_attempts_total_wall_s": sum(r["all_attempts_total_wall_s"] for r in rows)}
                       for key, rows in sorted(groups.items())]}


def publish(parent_dir, retry_dir, output):
    parent, pc, pm = checked_source(parent_dir)
    retry, rc, rm = checked_source(retry_dir)
    if pm["kind"] != "gdp_external_integer_enumeration" or rm["kind"] != "cstr30_seven_point_isolated_retry":
        raise ValueError("Unexpected run kind")
    if rm["parent_run"] != parent.name or set(map(tuple, rm["points"])) != RETRY_POINTS:
        raise ValueError("Retry parent or point list differs")
    if rm["runtime"]["host"] != "dantzig.ecn.purdue.edu" or rm["runtime"]["solver_version"][:2] != [52, 2]:
        raise ValueError("Use the returned Dantzig GAMS 52.2 retry, not the local validation run")
    attempts, jobs, preparations = [], {}, {}
    expected_jobs = {f"{solver}/{case}" for solver in SOLVERS for case in CASES}
    if not expected_jobs <= {j["name"] for j in pm["jobs"]}:
        raise ValueError("Missing solver/case job")
    for name in sorted(expected_jobs):
        manifest = checked_json(parent, pc, f"{name}/manifest.json")
        plan = manifest["plan"]
        solver, case = name.split("/")
        rows = [attempt(parent, pc, p.relative_to(parent).as_posix(), "initial")
                for p in sorted((parent / name / "records").glob("*.json"))]
        expected = set(map(tuple, plan["points"]))
        observed = [tuple(a["record"]["point"]) for a in rows]
        if (len(rows) != CASES[case] or len(expected) != CASES[case] or
                len(set(observed)) != len(rows) or set(observed) != expected or
                any(a["record"]["solver"] != solver or a["record"]["case"] != plan["case"]
                    or a["record"].get("cstr_size") != plan["cstr_size"] for a in rows)):
            raise ValueError(f"Coordinate coverage mismatch: {name}")
        attempts.extend(rows)
        jobs[name] = manifest
        if case == "dynamic":
            relative = f"{name}/preparation.json"
            for record in checked_json(parent, pc, relative):
                pid = record["preparation_id"]
                if pid in preparations and preparations[pid]["record"] != record:
                    raise ValueError("Conflicting Dynamic preparation records")
                entry = preparations.setdefault(pid, {"run_id": parent.name, "record": record, "source_files": []})
                entry["source_files"].append(relative)
    new = [attempt(retry, rc, p.relative_to(retry).as_posix(), "retry")
           for p in sorted((retry / "records").glob("*.json"))]
    if len(new) != 7 or {tuple(a["record"]["point"]) for a in new} != RETRY_POINTS:
        raise ValueError("Expected exactly seven retry records")
    attempts.extend(new)
    points = select_points(attempts)
    for row in points:
        if row["case"] == "dynamic" and row["preparation_id"] not in preparations:
            raise ValueError("Unresolved Dynamic preparation ID")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new output folder; existing data will not be overwritten")
    output.mkdir(parents=True, exist_ok=True)
    json_lines(output / "attempts.jsonl", attempts)
    json_lines(output / "points.jsonl", points)
    dump(output / "dynamic_preparation.json", list(preparations.values()))
    summary = summarize(points, attempts)
    dump(output / "summary.json", summary)
    # Keep selected job identities and original runner code; no shell files or old CSTR jobs.
    parent_meta = {k: v for k, v in pm.items() if k not in {"jobs", "runtime"}}
    parent_meta["jobs"] = [j for j in pm["jobs"] if j["name"] in expected_jobs]
    parent_meta["runtime"] = {k: v for k, v in pm["runtime"].items() if k in expected_jobs}
    provenance = {"schema_version": 1, "parent_run": parent.name, "retry_run": retry.name,
                  "parent_archive_sha256_recorded_by_retry": rm["parent_zip_sha256"],
                  "parent_protocol_selected_jobs": parent_meta, "job_manifests": jobs,
                  "retry_protocol": rm, "source_verification": {},
                  "merge_script_sha256": digest(Path(__file__))}
    for directory, checks in ((parent, pc), (retry, rc)):
        provenance["source_verification"][directory.name] = {
            "verified_file_count": len(checks), "run_json_sha256": checks["run.json"],
            "checksums_file_sha256": digest(directory / "SHA256SUMS")}
        for relative in sorted(checks):
            path = PurePosixPath(relative)
            if path.parts[0] == "source" and (path.suffix == ".py" or path.name in {"requirements-gdp.txt", "LICENSE"}):
                destination = output / "sources" / directory.name / Path(*path.parts[1:])
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(directory / relative, destination)
    dump(output / "provenance.json", provenance)
    # The README is maintained separately; these cover deterministic machine data and source snapshots.
    paths = sorted(p for p in output.rglob("*") if p.is_file())
    (output / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.relative_to(output).as_posix()}\n" for p in paths))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path, help="Extracted original GAMS result directory")
    parser.add_argument("--retry", required=True, type=Path, help="Extracted seven-point Dantzig retry directory")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.parent, args.retry, args.output), indent=2))


if __name__ == "__main__":
    main()
