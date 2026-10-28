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
ARCHIVE = ROOT / "results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip"
ARCHIVE_SHA256 = "e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e"
PREFIX = "dsda_abs1e5_rerun_20261028_020753_2004611/"
PREVIOUS_ARCHIVE = ROOT / "results/archives/dsda_abs1e5_sharedcpu_v2_return.zip"
PREVIOUS_SHA256 = "555445b52d2fb40c58cc6e4a4a5321592dd6f2bd5cb48ead6ca31fc8174a8964"
PREVIOUS_PREFIX = "dsda_abs1e5_20261027_234349_1812319/"


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


def algorithm_without_times(value):
    """Ignore measured durations, retaining the number of objective timings."""
    if isinstance(value, dict):
        return {
            k: len(v) if k == "objective_wall_times" else algorithm_without_times(v)
            for k, v in value.items()
            if k != "wall_time_s"
        }
    if isinstance(value, list):
        return [algorithm_without_times(v) for v in value]
    return value


def result_without_times_and_cpu(value):
    return {
        k: algorithm_without_times(v) if k == "algorithm_result" else v
        for k, v in value.items()
        if k not in ("search_s", "lookup_s", "effective_cpus")
    }


def callback_without_times(value):
    return {k: v for k, v in value.items() if k not in ("lookup_wall_s", "elapsed_s")}


def compare_repeat(previous, result, previous_events, events):
    require(
        result_without_times_and_cpu(previous) == result_without_times_and_cpu(result),
        "Repeated search result differs beyond measured times and CPU affinity",
    )
    require(
        [callback_without_times(e) for e in previous_events]
        == [callback_without_times(e) for e in events],
        "Repeated callback responses or paths differ beyond measured times",
    )
    return {
        **{k: result["spec"][k] for k in ("scope", "case", "budget", "seed")},
        "first_run_hit": previous["hit"],
        "rerun_hit": result["hit"],
        "first_run_best_objective": previous["best_objective"],
        "rerun_best_objective": result["best_objective"],
        "first_run_callbacks": previous["evaluations"],
        "rerun_callbacks": result["evaluations"],
        "first_run_first_hit": previous["first_hit"],
        "rerun_first_hit": result["first_hit"],
        "first_run_termination": previous["termination"],
        "rerun_termination": result["termination"],
        "objective_and_outcome_identical": True,
        "full_callback_responses_identical_excluding_times": True,
        "movement_path_and_algorithm_state_identical_excluding_times": True,
        "first_run_search_s": previous["search_s"],
        "rerun_search_s": result["search_s"],
    }


def verify(repeat_rows=None):
    if repeat_rows is None:
        repeat_rows = []
    require(sha(ARCHIVE.read_bytes()) == ARCHIVE_SHA256, "Return ZIP hash mismatch")
    require(
        sha(PREVIOUS_ARCHIVE.read_bytes()) == PREVIOUS_SHA256, "Previous ZIP changed"
    )
    with (
        zipfile.ZipFile(ARCHIVE) as archive,
        zipfile.ZipFile(PREVIOUS_ARCHIVE) as previous,
    ):
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

        def previous_read(name):
            return previous.read(PREVIOUS_PREFIX + name)

        hashes = data("OUTPUT_SHA256SUMS.json")
        require(
            set(names)
            == {PREFIX + n for n in hashes} | {PREFIX + "OUTPUT_SHA256SUMS.json"},
            "Output inventory does not cover every ZIP member",
        )
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
            require(
                path.read_bytes() == read(path.name),
                "Extracted evidence changed: " + path.name,
            )
        scientific_files = [
            n
            for n in input_hashes
            if n.startswith(("inputs/", "frozen/", "original/", "validation/legacy/"))
        ]
        previous_hashes = json.loads(previous_read("reproduction/SHA256SUMS.json"))
        require(
            set(scientific_files)
            == {
                n
                for n in previous_hashes
                if n.startswith(
                    ("inputs/", "frozen/", "original/", "validation/legacy/")
                )
            },
            "Scientific input/source inventory changed",
        )
        for name in scientific_files:
            require(
                read("reproduction/" + name) == previous_read("reproduction/" + name),
                "Scientific input/source differs from first run: " + name,
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
        previous_pairs = {
            key(r): r for r in csv_rows(previous_read("paired_comparison.csv"))
        }
        require(set(pairs) == set(previous_pairs), "Repeat pairing cohort differs")

        def keep_pair_fields(row):
            return {
                f: v
                for f, v in row.items()
                if f not in ("new_search_s", "new_lookup_s")
            }

        for k, row in pairs.items():
            require(
                keep_pair_fields(row) == keep_pair_fields(previous_pairs[k]),
                "Repeat paired comparison differs",
            )
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
            require(result["effective_cpus"] == [10], "Unexpected actual CPU affinity")
            previous_result = json.loads(previous_read(directory + "result.json"))
            previous_events = [
                json.loads(line)
                for line in previous_read(directory + "callbacks.jsonl").splitlines()
            ]
            repeat_rows.append(
                compare_repeat(previous_result, result, previous_events, events)
            )
            require(
                result["termination"] == pair["new_termination"], "Termination differs"
            )
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
        allocation = data("cpu_allocation.json")
        require(allocation == environment["cpu_allocation"], "CPU records disagree")
        require(
            allocation["execution_mode"] == "observed_idle_physical_core_then_pinned",
            "Execution provenance differs",
        )
        selection = allocation["selection"]
        require(
            allocation["cpu"] == selection["selected_cpu"] == 10
            and allocation["effective_cpus"] == environment["effective_cpus"] == [10]
            and selection["smt_siblings"] == [10, 58]
            and selection["physical_core_observed_idle"] is True
            and allocation["exclusive_reservation"] is False
            and selection["exclusive_reservation"] is False,
            "Idle-core observation or reservation provenance differs",
        )
        require(
            all(
                len(selection["smt_sibling_busy_percent"][str(cpu)]) == 3
                and all(v <= 5 for v in selection["smt_sibling_busy_percent"][str(cpu)])
                for cpu in (10, 58)
            ),
            "Selected SMT pair was not idle in all three observations",
        )
        require(
            selection == data("reproduction/CPU_SELECTION.json"),
            "Sealed CPU selection differs",
        )
        require(
            all(
                environment["threads"][name] == "1"
                for name in (
                    "OMP_NUM_THREADS",
                    "OMP_THREAD_LIMIT",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "BLIS_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS",
                    "GOTO_NUM_THREADS",
                    "NUMEXPR_MAX_THREADS",
                )
            ),
            "Numerical-library thread limit differs",
        )
        require(
            "Ran 11 tests" in read("unit_tests.log").decode(), "Protocol tests absent"
        )
        preparation = data("reproduction/PREPARATION.json")
        require(
            preparation["status"] == "ready"
            and len(preparation["preparation_commands"]) == 6
            and all(c["returncode"] == 0 for c in preparation["preparation_commands"]),
            "Preparation failed",
        )
        for index, count in enumerate((5, 4, 9, 3, 11), 2):
            log = read(f"reproduction/preparation_check_{index}.log").decode()
            require(
                f"Ran {count} tests" in log and "\nOK\n" in log,
                "Preparation tests absent",
            )
        for name in (
            "summary.json",
            "grid_budget_summary.csv",
            "process_condition_summary.csv",
            "descriptive_totals.csv",
            "unchanged_method_comparison.csv",
        ):
            require(
                read(name) == previous_read(name), "Repeat summary differs: " + name
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
            previous_archive_sha256=PREVIOUS_SHA256,
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
            archived_preparation_tests=32,
            scientific_input_source_files_identical=len(scientific_files),
            repeat_results_identical_excluding_times_and_cpu=len(repeat_rows),
            repeat_callbacks_identical_excluding_times=sum(
                r["new_callbacks"] for r in rebuilt
            ),
            repeat_changed_hits=0,
            repeat_changed_objectives=0,
            repeat_changed_counts=0,
            repeat_changed_paths=0,
            repeat_changed_terminations=0,
            server_revision=environment["server_revision"],
            source_base_revision=environment["source_manifest"]["source_base_revision"],
            effective_cpus=environment["effective_cpus"],
            execution_mode=environment["cpu_allocation"]["execution_mode"],
            exclusive_reservation=False,
            utc_started=environment["utc_started"],
            utc_finished=environment["utc_finished"],
            verification_mode="Read archived data only; no optimizer, solver, subprocess, or archived-code execution",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional new JSON output; existing files are never overwritten",
    )
    parser.add_argument(
        "--paired-output", type=Path, help="Optional new repeat comparison CSV"
    )
    args = parser.parse_args()
    repeat_rows = []
    result = verify(repeat_rows)
    rendered = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(rendered)
    if args.paired_output:
        with args.paired_output.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(repeat_rows[0]))
            writer.writeheader()
            writer.writerows(repeat_rows)
    print(rendered, end="")
