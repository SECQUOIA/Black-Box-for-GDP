"""Validate original Dantzig evidence; never borrow another model's timings."""

import hashlib
import json
import math
import zipfile

from .common import ROOT, point_key, read, sha


def verified_archive(name):
    metadata = read(ROOT / "overnight_benchmark/reference_archives.json")[name]
    path = ROOT / metadata["path"]
    if sha(path) != metadata["sha256"]:
        raise ValueError(f"Reference archive checksum mismatch: {path}")
    archive = zipfile.ZipFile(path)
    inventory = [n for n in archive.namelist() if n.count("/") == 1 and n.endswith("/SHA256SUMS")]
    if len(inventory) != 1:
        raise ValueError("Reference archive has no unique checksum inventory")
    prefix = inventory[0].split("/")[0] + "/"
    verified = set()
    for line in archive.read(inventory[0]).decode().splitlines():
        digest, relative = line.split("  ", 1)
        name_in_zip = prefix + relative
        if hashlib.sha256(archive.read(name_in_zip)).hexdigest() != digest:
            raise ValueError(f"Corrupt reference evidence: {name_in_zip}")
        verified.add(name_in_zip)
    return archive, prefix, verified


def archived_fmqa():
    from fmqa_benchmark.protocol import problem, reference_plan
    archive, prefix, verified = verified_archive("fmqa")
    with archive:
        def get(relative):
            name = prefix + relative
            if name not in verified:
                raise ValueError(f"Unverified archived FMQA file: {relative}")
            return json.loads(archive.read(name))
        run = get("run.json")
        # Host evidence is recorded in run.json; preserve the original config.
        serialized = json.dumps(run)
        if "dantzig.ecn.purdue.edu" not in serialized:
            raise ValueError("Original FMQA archive lacks Dantzig host evidence")
        if run["plan"] != reference_plan():
            raise ValueError("Original FMQA plan differs from frozen reference")
        results = []
        for spec in run["plan"]:
            root = f"jobs/{spec['job_id']}/"
            result = get(root + "result.json")
            event_name = prefix + root + "evaluations.jsonl"
            if event_name not in verified:
                raise ValueError("Unverified FMQA trace")
            events = [json.loads(line) for line in archive.read(event_name).splitlines()]
            if len(events) != result["total_evals"] or result["spec"] != spec:
                raise ValueError("FMQA result/trace mismatch")
            if [e["point"] for e in events[:spec["n_starts"]]] != spec["starting_points"]:
                raise ValueError("FMQA initial design mismatch")
            oracle = problem(spec)
            previous = 0.0
            for i, e in enumerate(events, 1):
                value = oracle["objective"](e["point"])
                if e["evaluation_index"] != i or e["completed_elapsed_s"] < previous:
                    raise ValueError("Invalid archived event order")
                if math.isfinite(value):
                    if e["raw_value"] is None or not math.isclose(value, e["raw_value"], rel_tol=1e-12):
                        raise ValueError("FMQA objective/source mismatch")
                elif e["raw_value"] is not None:
                    raise ValueError("FMQA invalid-point value mismatch")
                previous = e["completed_elapsed_s"]
            if previous > result["wall_time_s"]:
                raise ValueError("FMQA run ends before its final callback")
            results.append({"spec": spec, "events": events, "wall_time_s": result["wall_time_s"],
                            "status": result["status"], "source": "original_dantzig_fmqa_20260925",
                            "dfo_wall_time_s": result["wall_time_s"],
                            "recorded_best_value": result["best_value"],
                            "recorded_best_point": result["best_point"],
                            "target": oracle["target"]})
    return run["config"], results


def historical_costs(config, runtime):
    """Reuse ONLY original attempts with matching model/init/solver options.

    Successful retries from a different initialization are not substituted.
    Every status retains its nonzero measured cost. These are historical point
    measurements, not timing observations of the new algorithm runs.
    """
    from gdp_models._sources import source_root
    from gdp_models.solvers import solve_options, option_file_lines
    if config["solver"] != "gams_ipopt" or config["initialization"] != "auto":
        return {}, {"reason": "No historical costs for selected solver/initialization", "reused": 0}
    archive, prefix, verified = verified_archive("points")
    costs, rejected, preparations = {}, [], []
    with archive:
        for member in sorted(verified):
            if not member.startswith(prefix + "gams_ipopt/") or not member.endswith("/manifest.json"):
                continue
            manifest = json.loads(archive.read(member))
            old = manifest["runtime"]
            cfg = manifest["config"]
            source = old["source"]
            root = source_root("ld-sda-dynamic" if manifest["plan"]["case"] == "dynamic" else "dsda-gdp")
            matching = (
                cfg == {"solver": "gams_ipopt", "initialization": "auto",
                        "time_limit_s": config["nlp_seconds"], "feasibility_tolerance": 1e-5}
                and old["host"] == "dantzig.ecn.purdue.edu"
                and old["solver_executable_sha256"] == runtime["gams_sha256"]
                and old["pyomo_version"] == runtime["versions"]["pyomo"]
                and all(sha(root / name) == digest for name, digest in source["files_sha256"].items())
                and old["adapter_sha256"]["models.py"] == sha(ROOT / "gdp_models/models.py"))
            if not matching:
                rejected.append(member)
                continue
            directory = member.rsplit("/", 1)[0] + "/"
            prep_name = directory + "preparation.json"
            if prep_name in verified:
                prep = json.loads(archive.read(prep_name))
                preparations.extend(prep if isinstance(prep, list) else [prep])
            for record_name in sorted(verified):
                if not record_name.startswith(directory + "records/") or not record_name.endswith(".json"):
                    continue
                record = json.loads(archive.read(record_name))
                if record.get("solver_options") is not None and (
                    record["solver_options"] != solve_options("gams_ipopt", config["nlp_seconds"])
                    or record["solver_option_file"] != option_file_lines("gams_ipopt")
                ):
                    raise ValueError("Archived solver options differ from requested policy")
                duration = record["total_wall_s"]
                if not math.isfinite(duration) or duration <= 0:
                    raise ValueError("Invalid archived point time")
                key = point_key(record["case"], record.get("cstr_size"), record["point"])
                if key in costs:
                    raise ValueError("Duplicate historical original attempt")
                costs[key] = {"record": record, "cost_s": duration,
                              "source": record_name, "source_kind": "historical_original_attempt",
                              "source_sha256": hashlib.sha256(archive.read(record_name)).hexdigest()}
    return costs, {"reused": len(costs), "excluded_manifests": rejected, "preparations": preparations,
                   "note": "Mixed-date fixed-path cost estimates; not online runtime or a fallback/retry sequence."}
