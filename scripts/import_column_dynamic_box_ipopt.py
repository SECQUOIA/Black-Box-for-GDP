"""Verify and preserve the full-box Column/Dynamic return without running solvers."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import itertools
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RETURN = "dantzig_column_dynamic_ipopt_20261015_205822_gG8bXK"
RETURN_SHA = "2f4389c41de2d2cdb83d7c6ed9f49077c53a947156a0b2318158771a826ac34c"
PACKAGE = ROOT / "results/runners/column_dynamic_box_ipopt_20261015.zip"
PACKAGE_SHA = "e22b6ed957ad518c0d675b8688247b57531197f89c5abaa1598fbb8f9c7f31d0"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def table(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def encoded(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return json.dumps(value)
    return str(value)


def audit(archive):
    require(sha(archive.read_bytes()) == RETURN_SHA, "Unexpected return archive")
    require(sha(PACKAGE.read_bytes()) == PACKAGE_SHA, "Submitted runner changed")
    files = {}
    with zipfile.ZipFile(archive) as source:
        require(source.testzip() is None, "ZIP CRC failure")
        for entry in source.infolist():
            path = PurePosixPath(entry.filename)
            require(not path.is_absolute() and ".." not in path.parts
                    and path.parts[0] == RETURN, "Unsafe archive member")
            require(not stat.S_ISLNK(entry.external_attr >> 16), "Archive symlink")
            if entry.is_dir():
                continue
            name = "/".join(path.parts[1:])
            require(name and name not in files, "Duplicate or empty archive member")
            files[name] = source.read(entry)
    with zipfile.ZipFile(PACKAGE) as package:
        expected = {}
        for name in package.namelist():
            if name.endswith("/"):
                continue
            require(name.startswith("column_dynamic_ipopt_runner/"), "Package root changed")
            relative = name.split("/", 1)[1]
            expected[relative] = package.read(name)
        actual = {k.removeprefix("reproduction/"): v for k, v in files.items()
                  if k.startswith("reproduction/")}
        require(expected == actual, "Returned reproduction differs from submitted ZIP")
    for line in actual["RUNNER_SHA256SUMS"].decode().splitlines():
        digest, name = line.split(maxsplit=1)
        require(sha(actual[name]) == digest, "Runner member checksum: " + name)

    reports = []
    for case, bounds in (("column", ((7, 15), (1, 9))), ("dynamic", ((1, 9), (2, 9)))):
        rows = table(files[f"{case}/evaluations.csv"])
        manifest = json.loads(files[f"{case}/manifest.json"])
        summary = json.loads(files[f"{case}/summary.json"])
        points = list(itertools.product(*(range(lo, hi + 1) for lo, hi in bounds)))
        require([tuple(json.loads(r["point"])) for r in rows] == points, "Missing/duplicate/order error")
        require(manifest["plan"]["points"] == [list(p) for p in points], "Manifest domain mismatch")
        require(manifest["config"] == {"solver": "gams_ipopt", "initialization": "auto",
                "time_limit_s": 60.0, "feasibility_tolerance": 1e-5}, "Changed evaluation settings")
        runtime = manifest["runtime"]
        require(runtime["host"] == "dantzig.ecn.purdue.edu", "Unexpected execution host")
        for name, digest in runtime["code_sha256"].items():
            require(sha(actual[name]) == digest, "Execution code differs: " + name)
        for name, digest in runtime["reference_sha256"].items():
            require(sha(actual[f"reference/{case}/{name}"]) == digest, "Reference hash mismatch")
        records = {n: json.loads(b) for n, b in files.items() if n.startswith(f"{case}/records/")}
        require(len(records) == len(points), "Unexpected checkpoint count")
        for index, (point, row) in enumerate(zip(points, rows), 1):
            record = records[f"{case}/records/point_{index:06d}.json"]
            require(record["point"] == list(point) and record["point_index"] == index,
                    "Checkpoint coordinate mismatch")
            require(record["case"] == case and record["solver"] == "gams_ipopt", "Wrong process/solver")
            for field, value in row.items():
                expected_value = point[int(field[1]) - 1] if field in ("x1", "x2") else record.get(field)
                require(value == encoded(expected_value), f"CSV/checkpoint mismatch: {case} {point} {field}")
            for field in ("total_wall_s", "setup_wall_s", "logic_wall_s"):
                require(math.isfinite(record[field]) and record[field] > 0, "Unmeasured coordinate time")
            for field in ("preprocess_wall_s", "solve_wall_s"):
                if record.get(field) is not None:
                    require(math.isfinite(record[field]) and record[field] >= 0, "Invalid stage time")
            logical = point[0] >= 8 and point[1] <= 8 if case == "column" else point[0] < point[1] or point == (9, 9)
            require(record["logical_allowed"] == logical, "Logical rule mismatch")
            if not logical:
                require(record["status"] == "logical_infeasible" and not record["solver_called"],
                        "Logical exclusion was not retained")
            if record["accepted"]:
                require(logical and record["status"] == "accepted" and math.isfinite(record["objective"]),
                        "Invalid accepted objective")
                require(record["termination"] in ("optimal", "locallyOptimal", "globallyOptimal")
                        and record["solver_status"] not in ("error", "aborted")
                        and record["gams_solve_status"] == 1 and record["gams_model_status"] in (1, 2)
                        and record["validation_performed"] and record["primal_feasible"]
                        and 0 <= record["max_primal_violation"] <= 1e-5, "Acceptance criteria violated")
            else:
                require(record["objective"] is None and record["status"] != "accepted", "Unaccepted objective leaked")
        historical = {tuple(json.loads(r["point"])): r for r in table(actual[f"reference/{case}/evaluations.csv"])}
        current = {tuple(json.loads(r["point"])): r for r in rows}
        acceptance_changes, differences = [], []
        for point, old in historical.items():
            new = current[point]
            if old["accepted"] != new["accepted"]:
                acceptance_changes.append(list(point))
            if old["accepted"] == new["accepted"] == "True":
                differences.append(float(new["objective"]) - float(old["objective"]))
        comparisons = table(files[f"{case}/comparison.csv"])
        require(len(comparisons) == len(rows), "Comparison rows missing")
        for row, comp in zip(rows, comparisons):
            point = tuple(json.loads(row["point"]))
            old = historical.get(point)
            require(comp["point"] == row["point"] and comp["new_total_wall_s"] == row["total_wall_s"]
                    and comp["new_objective"] == row["objective"] and comp["new_status"] == row["status"]
                    and comp["new_accepted"] == row["accepted"], "New comparison row mismatch")
            require(comp["old_record_exists"] == str(old is not None), "Historical membership mismatch")
            if old:
                for field in ("objective", "accepted", "status", "total_wall_s"):
                    require(comp[f"old_{field}"] == old[field], "Historical comparison row mismatch")
        counts = dict(Counter(r["status"] for r in rows))
        accepted = [r for r in rows if r["accepted"] == "True"]
        total = sum(float(r["total_wall_s"]) for r in rows)
        require(summary["complete"] and summary["status_counts"] == counts
                and summary["accepted_points"] == len(accepted)
                and summary["completed_points"] == len(rows)
                and summary["remaining_points"] == summary["missing_rows"] == summary["duplicate_rows"]
                == summary["missing_total_times"] == 0, "Reported completion differs")
        require(math.isclose(total, summary["sum_evaluation_wall_s"], rel_tol=1e-12), "Time total mismatch")
        best = min(accepted, key=lambda r: float(r["objective"]))
        timing = {}
        for status in counts:
            values = [float(r["total_wall_s"]) for r in rows if r["status"] == status]
            timing[status] = {"count": len(values), "sum_s": sum(values), "min_s": min(values), "max_s": max(values)}
        reports.append({"case": case, "rows": len(rows), "status_counts": counts,
                        "accepted": len(accepted), "best_point": json.loads(best["point"]),
                        "best_objective": float(best["objective"]), "all_total_times_measured": True,
                        "missing_or_duplicate_coordinates": 0, "csv_checkpoint_fields_match": True,
                        "timing_by_status": timing, "sum_total_wall_s": total,
                        "historical_overlap": len(historical), "acceptance_changed_points": acceptance_changes,
                        "max_absolute_accepted_objective_difference": max(map(abs, differences)),
                        "runtime": runtime})
    preparation = json.loads(files["dynamic/preparation.json"])
    require(all(p["total_preparation_wall_s"] > 0 and not p["included_in_point_total_wall_s"]
                for p in preparation), "Dynamic shared preparation accounting changed")
    report = {"archive_sha256": RETURN_SHA, "submitted_runner_sha256": PACKAGE_SHA,
              "original_archive_members": len(files), "reproduction_matches_submitted_runner": True,
              "attempt_selection": "One completed attempt per coordinate; no exclusions or retries",
              "cases": reports, "dynamic_shared_preparation": preparation,
              "historical_dfo_results_modified": False, "solver_calls_during_import": 0}
    return files, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results/column_dynamic_box_ipopt" / RETURN)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    files, report = audit(args.archive)
    if not args.check_only:
        output = args.output.resolve()
        require(not output.exists(), "Output already exists; use --check-only to verify the source")
        destination = ROOT / "results/archives" / f"{RETURN}.zip"
        if destination.exists():
            require(sha(destination.read_bytes()) == RETURN_SHA, "Existing archive differs")
        else:
            shutil.copyfile(args.archive, destination)
        destination.with_suffix(".zip.sha256").write_text(f"{RETURN_SHA}  {destination.name}\n")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
            staged = Path(temporary) / RETURN
            for name, data in files.items():
                target = staged / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            report["archive"] = destination.relative_to(ROOT).as_posix()
            report["original_download"] = str(args.archive.resolve())
            (staged / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
            (staged / "import_files_sha256.json").write_text(json.dumps({k: sha(v) for k, v in files.items()}, indent=2) + "\n")
            staged.rename(output)
    print(json.dumps({"output": str(args.output), "cases": [{k: c[k] for k in (
        "case", "rows", "accepted", "status_counts", "all_total_times_measured",
        "acceptance_changed_points", "max_absolute_accepted_objective_difference")} for c in report["cases"]]}, indent=2))


if __name__ == "__main__":
    main()
