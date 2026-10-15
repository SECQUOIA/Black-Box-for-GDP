"""Audit the returned CSTR30 timing supplement; never evaluate a model or solver."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import statistics
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import measure_cstr30_structural_rejections as protocol

RETURN = "dantzig_cstr30_structural_20261015_214202_pgve882p"
RETURN_SHA = "3a5094a2e99c269cf830cd668c52853c2a3641d9fd4f176c0a7ca076ee110253"
PACKAGE = ROOT / "results/runners/cstr30_structural_rejections_20261015.zip"
PACKAGE_SHA = "76d219a0a7a03bb62700b08d8c2091849d50628d30a07f8aa030e81aa147be07"
LOCAL_ARCHIVE = ROOT / "results/dantzig_review/cstr30_structural_returns" / f"{RETURN}.zip"
DERIVED = ("structural_rejections.csv", "combined_cstr30_900.csv", "callbacks_with_timing_supplement.csv",
           "callbacks_with_timing_supplement.jsonl", "cstr30_run_time_comparison.csv", "remaining_time_gaps.json")
KEEP = ("structural_rejections.csv", "combined_cstr30_900.csv", "cstr30_run_time_comparison.csv",
        "remaining_time_gaps.json", "summary.json", "manifest.json")
require = protocol.require


def extract_verified(archive, temporary):
    require(protocol.sha(archive) == RETURN_SHA, "Unexpected returned archive")
    require(protocol.sha(PACKAGE) == PACKAGE_SHA, "Submitted ZIP changed")
    hashes = {}
    with zipfile.ZipFile(archive) as source:
        require(source.testzip() is None, "Return ZIP CRC failure")
        for entry in source.infolist():
            path = PurePosixPath(entry.filename)
            require(not path.is_absolute() and ".." not in path.parts and path.parts[0] == RETURN, "Unsafe ZIP member")
            require(not stat.S_ISLNK(entry.external_attr >> 16), "ZIP symlink")
            if entry.is_dir():
                continue
            name = "/".join(path.parts[1:])
            require(name and name not in hashes, "Duplicate ZIP member")
            data = source.read(entry)
            hashes[name] = hashlib.sha256(data).hexdigest()
            target = temporary / RETURN / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    directory = temporary / RETURN
    reproduction = directory / "reproduction"
    expected = {}
    with zipfile.ZipFile(PACKAGE) as source:
        for name in source.namelist():
            if name.endswith("/"):
                continue
            require(name.startswith("cstr30_structural_runner/"), "Unexpected submitted root")
            expected[name.split("/", 1)[1]] = source.read(name)
    actual = {p.relative_to(reproduction).as_posix(): p.read_bytes()
              for p in reproduction.rglob("*") if p.is_file()}
    require(actual == expected, "Returned execution bundle differs from submitted ZIP")
    require(protocol.sha(protocol.__file__) == protocol.sha(reproduction / "measure_cstr30_structural_rejections.py"),
            "Local report reconstructor differs from frozen execution code")
    return directory, hashes


def audit(directory, regenerated):
    root = directory / "reproduction"
    original, historical, jobs = protocol.check_inputs(root)
    manifest, summary = protocol.read(directory / "manifest.json"), protocol.read(directory / "summary.json")
    require(manifest["measurement_run_id"] == RETURN and manifest["bundle_sha256"] == protocol.sha(root / "SHA256SUMS"), "Run identity differs")
    require(manifest["code_and_input_provenance"] == protocol.read(root / "bundle_provenance.json")
            and manifest["historical_manifest"] == historical, "Run provenance differs")
    require(not manifest["solver_calls_permitted"] and not manifest["dfo_search_executed"]
            and summary["solver_calls"] == summary["forbidden_entry_attempts"] == 0, "Forbidden execution evidence")
    runtime, previous = manifest["runtime"], historical["runtime"]
    require(runtime["host"] == "dantzig.ecn.purdue.edu" and len(runtime["effective_cpu"]) == 1, "Wrong execution host/affinity")
    require(runtime["dependencies"] == previous["dependency_versions"] and runtime["python"] == previous["python_version"]
            and runtime["source"] == previous["source"] and runtime["initialization"] == previous["initialization"], "Original procedure/runtime differs")
    require(runtime["solver_version_or_availability_probes"] == runtime["common_preparation_test_models"] == 0, "Preflight evaluation was added")
    require(all(v == "1" for v in runtime["thread_environment"].values()), "Thread setting changed")
    invocations = {p.stem: protocol.read(p) for p in (directory / "invocations").glob("*.json")}
    require(invocations and all(not i["included_in_coordinate_times"] and i["common_preparation_wall_ns"] > 0
            and i["common_preparation_wall_s"] == i["common_preparation_wall_ns"] / 1e9 for i in invocations.values()), "Common preparation timing differs")
    measured = {}
    for path in sorted((directory / "records").glob("*.json")):
        record = protocol.read(path)
        point = tuple(record["point"])
        require(point not in measured and point in protocol.POINTS, "Duplicate/unexpected structural point")
        require(record["invocation_id"] in invocations and record["measurement_run_id"] == RETURN, "Measurement source differs")
        require(type(record["elapsed_ns"]) is int and record["elapsed_ns"] > 0
                and record["total_wall_s"] == record["elapsed_ns"] / 1e9
                and math.isfinite(record["total_wall_s"]), "Invalid high-resolution measurement")
        require(record["message"] == f"Unsatisfied GDP logic: cstr_if_recycle[{point[1]}]"
                and record["measurement_scope"] == protocol.SCOPE, "Unexpected rejection path")
        require(record["x1"] == point[0] and record["x2"] == point[1], "Coordinate labels differ")
        require(0 < record["inner_total_wall_s"] <= record["total_wall_s"], "Clock scope order differs")
        measured[point] = record
    require(len(measured) == 435, "Missing structural measurements")
    require((directory / "original_465.csv").read_bytes() == (root / "inputs/cstr_30/evaluations.csv").read_bytes(), "Original CSV bytes changed")
    # Rebuild reports in a disposable directory only; this calls no evaluator.
    regenerated.mkdir(parents=True)
    shutil.copytree(directory / "records", regenerated / "records")
    shutil.copyfile(directory / "original_465.csv", regenerated / "original_465.csv")
    rebuilt = protocol.report_results(root, regenerated, original, 0)
    for name in DERIVED:
        require((regenerated / name).read_bytes() == (directory / name).read_bytes(), "Recomputed report differs: " + name)
    require({k: v for k, v in rebuilt.items() if k != "updated_utc"}
            == {k: v for k, v in summary.items() if k != "updated_utc"}, "Summary differs from raw records")

    # Independently check every unchanged original event and each cost assignment.
    exported = [json.loads(line) for line in (directory / "callbacks_with_timing_supplement.jsonl").read_text().splitlines()]
    exported_by_job = defaultdict(list)
    for event in exported:
        exported_by_job[event["job_id"]].append(event)
    groups = defaultdict(lambda: {"callbacks": 0, "supplemented_callbacks": 0, "remaining_time_gaps": 0, "added_process_cost_s": 0.0})
    unique = set()
    for spec in jobs:
        job = root / "inputs/dfo/jobs" / spec["job_id"]
        before = [json.loads(line) for line in (job / "callbacks.jsonl").read_text().splitlines()]
        after = exported_by_job[spec["job_id"]]
        require(len(before) == len(after), "Lost/repeated callback")
        for old, new in zip(before, after):
            require(all(new[k] == v for k, v in old.items()), "Original event field changed")
            filled = old["evaluation_state"] == "logical_exclusion_unmeasured" and not old["budget_overrun"]
            require(new["timing_supplement_applied"] is filled, "Wrong callback supplemented")
            point = tuple(old["point"])
            expected = measured[point]["total_wall_s"] if filled else old["selected_attempt_nlp_s"]
            require(new["reconstructed_process_wall_s"] == expected, "Callback cost does not match selected coordinate")
            g = groups[spec["method"]]
            g["callbacks"] += 1
            g["remaining_time_gaps"] += expected is None
            if filled:
                g["supplemented_callbacks"] += 1
                g["added_process_cost_s"] += expected
                unique.add(point)
    require(set(exported_by_job) == {s["job_id"] for s in jobs}, "Unexpected DFO job")
    times = [r["total_wall_s"] for r in measured.values()]
    return {"archive_sha256": RETURN_SHA, "submitted_runner_sha256": PACKAGE_SHA,
        "reproduction_matches_submitted_runner": True, "code_commit": manifest["code_and_input_provenance"]["git_commit"],
        "original_rows_preserved": 465, "supplemental_rows": 435, "combined_unique_rows": 900,
        "all_csv_and_original_record_fields_verified": True, "all_total_times_positive_finite": True,
        "structural_time_s": {"sum": sum(times), "minimum": min(times), "median": statistics.median(times), "maximum": max(times)},
        "common_preparation_s": sum(i["common_preparation_wall_s"] for i in invocations.values()),
        "common_preparation_in_point_times": False, "solver_calls_reported": 0,
        "solver_evidence": "Byte-identical execution guard code, zero forbidden-entry attempts, all435 original logical rejections before solver construction",
        "dfo": summary["dfo"], "unique_structural_points_visited": len(unique), "by_method": dict(groups),
        "original_dfo_outcomes_penalties_paths_and_clocks_unchanged": True,
        "remaining_gap_policy": "Retain7 BAM B+1 protocol errors as execution_failed and costs unknown; no zero/borrowed times",
        "local_model_solver_or_DFO_calls": 0, "interpretation": "Separate process rejection timings and reconstructed per-callback costs, not new online DFO times"}


def report_text(info):
    t = info["structural_time_s"]
    return f"""Verified CSTR30 structural-rejection timing supplement

435/435 x2>x1 points measured, with finite positive total_wall_s and integer
elapsed_ns. Status preprocessing_infeasible; termination not_solved; objective
blank; accepted=False; solve_wall_s=0 because no solver was called.
Original465 objectives, statuses and times are unchanged in the combined900
unique-point table. No rows are missing, duplicated or replaced by retries.

Measured rejection time (seconds):
  Minimum {t['minimum']!r}; median {t['median']!r}; maximum {t['maximum']!r}.
  Sum across435 unique points: {t['sum']!r}.
  Separate common preparation: {info['common_preparation_s']!r}.
The interval includes the original fresh-model construction, initialization,
external fixing and GDP logic checks until rejection returns. Source preloading,
CSV reads/writes, progress output and common preparation are excluded.

508 callback costs for228 visited structural coordinates are filled, charging
each repeated visit. Missing times decrease from515 to7. All40 run outcomes
and all1,615 original callback fields remain unchanged, including objectives,
penalties, visit order, counts, DFO runtime and lookup runtime.
The remaining7 gaps are BAM B+1 protocol errors (seeds0,2,3,4,5,7,9), whose
process CSV rows were never read. These remain execution_failed with unknown
cost, not zero cost; all33 other runs have complete reconstructed process sums.

Use reconstructed_process_wall_s in callbacks_with_timing_supplement.csv.gz.
The original timing fields remain historical evidence. Per-run before/after
counts and process cost sums are in cstr30_run_time_comparison.csv. These are
reconstructed costs from separate measurements, not measured online DFO times.
Original DFO datasets, search results and success classifications are untouched.

Raw archive retained locally, excluded from the published result:
results/dantzig_review/cstr30_structural_returns/{RETURN}.zip
All1,133 archive members, including435 individual records, original465.csv,
the full JSONL ledger and frozen execution sources, remain in that unchanged ZIP.
The curated CSV/JSON files are exact copies; the callback CSV is losslessly
gzip-compressed. audit.json and file-hash inventories document the checks.
Historical inputs/execution sources are not duplicated as loose files here.

Executed code commit: {info['code_commit']}
Runtime: Dantzig CPU0, Python3.11.16, Pyomo6.10.0. Model/source identities,
all input hashes and the nanosecond clock are retained in manifest.json.
No local model construction, solver calls, DFO search or timing measurement
was performed during import. Reports were regenerated in a temporary folder
and checked byte-for-byte against the returned reports.

Recheck without writing repository files:
python3 scripts/import_cstr30_structural_rejections.py \\
  /path/to/{RETURN}.zip --check-only
Import into another new directory using --output /new/path.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results/cstr30_structural_rejections" / RETURN)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.check_only:
        require(not args.output.exists(), "Output exists; use --check-only")
    with tempfile.TemporaryDirectory(prefix="cstr30-structural-import-") as temporary:
        temp = Path(temporary)
        directory, hashes = extract_verified(args.archive, temp / "extracted")
        info = audit(directory, temp / "regenerated" / RETURN)
        info.update(original_download=str(args.archive.resolve()), local_archive=str(LOCAL_ARCHIVE.relative_to(ROOT)),
                    archive_published=False, archive_members=len(hashes), importer_sha256=protocol.sha(__file__))
        if not args.check_only:
            stage = temp / "curated"
            stage.mkdir()
            for name in KEEP:
                shutil.copyfile(directory / name, stage / name)
            shutil.copytree(directory / "invocations", stage / "invocations")
            callback_bytes = (directory / "callbacks_with_timing_supplement.csv").read_bytes()
            compressed = gzip.compress(callback_bytes, mtime=0)
            require(gzip.decompress(compressed) == callback_bytes, "Lossy callback export")
            (stage / "callbacks_with_timing_supplement.csv.gz").write_bytes(compressed)
            protocol.write(stage / "audit.json", info)
            protocol.write(stage / "archive_members_sha256.json", hashes)
            (stage / "README.txt").write_text(report_text(info))
            protocol.write(stage / "import_files_sha256.json", {p.relative_to(stage).as_posix(): protocol.sha(p)
                for p in sorted(stage.rglob("*")) if p.is_file()})
            archive = LOCAL_ARCHIVE
            archive.parent.mkdir(parents=True, exist_ok=True)
            require(not archive.exists() or protocol.sha(archive) == RETURN_SHA, "Existing archive differs")
            if not archive.exists():
                shutil.copyfile(args.archive, archive)
            archive.with_suffix(".zip.sha256").write_text(f"{RETURN_SHA}  {archive.name}\n")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(stage, args.output)
        print(json.dumps({k: info[k] for k in ("supplemental_rows", "combined_unique_rows", "structural_time_s", "dfo")}, indent=2))


if __name__ == "__main__":
    main()
