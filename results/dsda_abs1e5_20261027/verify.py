"""Independently audit retained D-SDA records without executing archived code."""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = ROOT / "results/archives/dsda_abs1e5_sharedcpu_v2_return.zip"
ARCHIVE_SHA256 = "555445b52d2fb40c58cc6e4a4a5321592dd6f2bd5cb48ead6ca31fc8174a8964"
PREFIX = "dsda_abs1e5_20261027_234349_1812319/"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def csv_rows(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def key(row):
    return row["scope"], row["case"], int(row["budget"]), int(row["seed"])


def hit(value, target):
    return (
        value is not None
        and math.isfinite(value)
        and abs(value - target) <= 1e-5 * max(1, abs(target))
    )


def optional_number(value):
    if value is None or value == "":
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def verify():
    require(sha(ARCHIVE.read_bytes()) == ARCHIVE_SHA256, "Return ZIP hash mismatch")
    with zipfile.ZipFile(ARCHIVE) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate ZIP member")
        require(
            all(
                not PurePosixPath(n).is_absolute()
                and ".." not in PurePosixPath(n).parts
                for n in names
            ),
            "Unsafe ZIP member",
        )

        def read(name):
            return archive.read(PREFIX + name)

        def data(name):
            return json.loads(read(name))

        hashes = data("OUTPUT_SHA256SUMS.json")
        for name, expected in hashes.items():
            require(
                sha(read(name)) == expected, "Returned output hash mismatch: " + name
            )
        input_hashes = data("reproduction/SHA256SUMS.json")
        for name, expected in input_hashes.items():
            require(
                sha(read("reproduction/" + name)) == expected,
                "Execution input/source hash mismatch: " + name,
            )
        for path in (HERE / "returned").iterdir():
            member = (
                "repair_diagnostics/repair_status.json"
                if path.name == "repair_status.json"
                else PREFIX + path.name
            )
            require(
                path.read_bytes() == archive.read(member),
                "Extracted evidence changed: " + path.name,
            )
        adopted = ROOT / "results/column_publication_20261025/tables/run_records.csv"
        require(
            adopted.read_bytes() == read("reproduction/inputs/adopted_all_methods.csv"),
            "Adopted baseline changed",
        )
        original_rows = csv_rows(adopted.read_bytes())
        originals = {key(r): r for r in original_rows if r["method"] == "dsda"}
        pair_rows = csv_rows(read("paired_comparison.csv"))
        pairs = {key(r): r for r in pair_rows}
        jobs = data("reproduction/inputs/jobs.json")
        job_keys = [key(j["spec"]) for j in jobs]
        require(
            len(pairs) == len(pair_rows) == len(jobs) == len(set(job_keys)) == 1190,
            "Missing or duplicated pairing",
        )
        require(set(pairs) == set(originals) == set(job_keys), "Pairing cohort differs")
        require(
            Counter(k[0] for k in pairs) == {"grid": 1050, "process": 140},
            "Scope count differs",
        )
        conditions = {(k[1], k[2]) for k in pairs if k[0] == "process"}
        require(len(conditions) == 14, "Process conditions differ")
        for scope, case, budget in {k[:3] for k in pairs}:
            require(
                {k[3] for k in pairs if k[:3] == (scope, case, budget)}
                == set(range(10)),
                "Seed cohort differs",
            )
        rebuilt = []
        for job in jobs:
            spec = job["spec"]
            pair = pairs[key(spec)]
            require(
                job["baseline"] == originals[key(spec)], "Historical record mismatch"
            )
            directory = "runs/" + spec["job_id"] + "/"
            result = data(directory + "result.json")
            process = data(directory + "process.json")
            events = [
                json.loads(line)
                for line in read(directory + "callbacks.jsonl").splitlines()
            ]
            old_events = job["baseline_events"]
            require(
                result["spec"] == spec and result["improvement_abs_tol"] == 1e-5,
                "Experimental settings mismatch",
            )
            require(
                spec["settings"]
                == {"diagonal": True, "tie_break": "first", "tol": 1e-12},
                "Tie/target settings changed",
            )
            require(
                result["status"] in ("completed", "budget_completed"),
                "Failed execution",
            )
            require(
                process["returncode"] == 0 and not process["watchdog_timeout"],
                "Worker failure or watchdog",
            )
            require(
                process["watchdog_seconds"] == job["hard_seconds"], "Watchdog changed"
            )
            require(
                result["process_nlp_calls"] == 0
                and not result["blocked_solver_or_process_attempts"],
                "Solver/process attempt recorded",
            )
            require(result["effective_cpus"] == [2], "Unexpected actual CPU affinity")
            require(
                [e["index"] for e in events] == list(range(1, len(events) + 1)),
                "Callback sequence differs",
            )
            require(
                [e["point"] for e in events[:3]] == spec["starts"],
                "Initial order differs",
            )
            require(len(events) <= spec["budget"], "Budget exceeded")
            require(
                len(events) == result["evaluations"] == int(pair["new_callbacks"]),
                "New callback count differs",
            )
            require(
                len(old_events) == int(pair["old_callbacks"]),
                "Old callback count differs",
            )
            best = min(e["raw_objective"] for e in events if e["accepted"])
            old_best = min(e["raw_objective"] for e in old_events if e["accepted"])
            require(
                best == result["best_objective"] == float(pair["new_best_objective"]),
                "New objective differs",
            )
            require(
                old_best == float(pair["old_best_objective"]), "Old objective differs"
            )
            old_hit, new_hit = hit(old_best, job["target"]), hit(best, job["target"])
            require(old_hit == (pair["old_hit"] == "True"), "Old success differs")
            require(
                new_hit == result["hit"] == (pair["new_hit"] == "True"),
                "New success differs",
            )
            require(
                result["category"]
                == pair["new_category"]
                == ("target_reached" if new_hit else "target_not_reached"),
                "New category differs",
            )
            require(
                pair["old_category"] == originals[key(spec)]["category"],
                "Old category differs",
            )
            for group, success, column in [
                (events, new_hit, "new_first_hit"),
                (old_events, old_hit, "old_first_hit"),
            ]:
                first = (
                    next(
                        (
                            e["index"]
                            for e in group
                            if e["accepted"] and hit(e["raw_objective"], job["target"])
                        ),
                        None,
                    )
                    if success
                    else None
                )
                require(
                    first == optional_number(pair[column]), "First-hit callback differs"
                )
                if column == "new_first_hit":
                    require(
                        first == result["first_hit"],
                        "Result first-hit callback differs",
                    )
            path_changed = [e["point"] for e in events] != [
                e["point"] for e in old_events
            ]
            require(
                path_changed == (pair["callback_path_changed"] == "True"),
                "Callback path change differs",
            )
            if spec["scope"] == "process":
                require(
                    all(e["method_value"] == 1e6 for e in events if not e["accepted"]),
                    "Finite penalty changed",
                )
            rebuilt.append(
                dict(
                    scope=spec["scope"],
                    case=spec["case"],
                    budget=spec["budget"],
                    seed=spec["seed"],
                    old_hit=old_hit,
                    new_hit=new_hit,
                    old_callbacks=len(old_events),
                    new_callbacks=len(events),
                    old_objective=old_best,
                    new_objective=best,
                    path_changed=path_changed,
                )
            )

        def aggregate(rows):
            return dict(
                runs=len(rows),
                old_hits=sum(r["old_hit"] for r in rows),
                new_hits=sum(r["new_hit"] for r in rows),
                old_only=sum(r["old_hit"] and not r["new_hit"] for r in rows),
                new_only=sum(r["new_hit"] and not r["old_hit"] for r in rows),
                old_callbacks=sum(r["old_callbacks"] for r in rows),
                new_callbacks=sum(r["new_callbacks"] for r in rows),
                changed_callback_counts=sum(
                    r["old_callbacks"] != r["new_callbacks"] for r in rows
                ),
                changed_callback_paths=sum(r["path_changed"] for r in rows),
            )

        totals = {
            scope: aggregate([r for r in rebuilt if r["scope"] == scope])
            for scope in ("grid", "process")
        }
        totals["cstr"] = aggregate(
            [r for r in rebuilt if r["case"].startswith("cstr_")]
        )
        for row in data("summary.json")["totals"]:
            require(
                all(row[k] == v for k, v in totals[row["scope"]].items()),
                "Summary mismatch",
            )
        for filename, scope in [
            ("grid_budget_summary.csv", "grid"),
            ("process_condition_summary.csv", "process"),
        ]:
            for row in csv_rows(read(filename)):
                group = [
                    r
                    for r in rebuilt
                    if r["scope"] == scope
                    and r["budget"] == int(row["budget"])
                    and (scope == "grid" or r["case"] == row["case"])
                ]
                require(
                    all(int(row[k]) == v for k, v in aggregate(group).items()),
                    "Condition summary differs",
                )
        relation_changes = 0
        for row in csv_rows(read("unchanged_method_comparison.csv")):

            def selected(r):
                return (
                    r["scope"] == row["scope"]
                    and int(r["budget"]) == int(row["budget"])
                    and (row["case"] == "all" or r["case"] == row["case"])
                )

            others = [
                r for r in original_rows if r["method"] == row["method"] and selected(r)
            ]
            our = [r for r in rebuilt if selected(r)]
            require(
                len(others) == len(our) == int(row["runs"]),
                "Other-method denominator differs",
            )
            other_hits = sum(r["hit"] == "True" for r in others)
            require(
                other_hits == int(row["unchanged_other_hits"]),
                "Other-method results changed",
            )

            def relation(n):
                return (
                    "more" if n > other_hits else "fewer" if n < other_hits else "equal"
                )

            old_relation = relation(sum(r["old_hit"] for r in our))
            new_relation = relation(sum(r["new_hit"] for r in our))
            require(
                old_relation == row["old_relation"]
                and new_relation == row["new_relation"],
                "Method ordering differs",
            )
            relation_changes += old_relation != new_relation
        environment = data("execution_manifest.json")
        require(
            environment["cpu_allocation"]["execution_mode"]
            == "shared_cpu_explicitly_requested_by_user",
            "Execution provenance differs",
        )
        require(
            "Ran 11 tests" in read("unit_tests.log").decode(), "Protocol tests absent"
        )
        repair_log = archive.read("repair_diagnostics/server.log").decode()
        require(
            "Ran 5 tests" in repair_log and "Ran 4 tests" in repair_log,
            "Repair tests absent",
        )
        objective_changes = {}
        for scope in ("grid", "process"):
            differences = [
                r["new_objective"] - r["old_objective"]
                for r in rebuilt
                if r["scope"] == scope
            ]
            objective_changes[scope] = dict(
                exactly_equal=sum(d == 0 for d in differences),
                better=sum(d < 0 for d in differences),
                worse=sum(d > 0 for d in differences),
                max_absolute_change=max(map(abs, differences)),
            )
        return dict(
            status="PASS",
            archive_sha256=ARCHIVE_SHA256,
            archived_output_hashes_verified=len(hashes),
            execution_input_hashes_verified=len(input_hashes),
            exact_pairs=1190,
            missing=0,
            duplicate_pairs=0,
            failed=0,
            totals=totals,
            objective_changes=objective_changes,
            method_hit_order_changes=relation_changes,
            process_nlp_calls=0,
            solver_or_child_process_attempts=0,
            archived_protocol_tests=11,
            archived_repair_tests=9,
            server_revision=environment["server_revision"],
            source_base_revision=environment["source_manifest"]["source_base_revision"],
            effective_cpus=environment["effective_cpus"],
            execution_mode=environment["cpu_allocation"]["execution_mode"],
            verification_mode="Read archived data only; no optimizer, solver, subprocess, or archived-code execution",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional new JSON output; existing files are never overwritten",
    )
    args = parser.parse_args()
    result = verify()
    rendered = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(rendered)
    print(rendered, end="")
