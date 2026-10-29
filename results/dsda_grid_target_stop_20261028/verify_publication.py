"""Cross-check both return archives and reproduce publication summaries from data."""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORKFLOW = REPO / "experiments/dsda_grid_target_stop"
sys.path.insert(0, str(WORKFLOW))

from protocol import require  # noqa: E402
from verify import verify as verify_saved_data  # noqa: E402

NEW_ARCHIVE = (
    REPO / "results/archives/dsda_grid_target_stop_20261028_032943_2346732.zip"
)
NEW_SHA = "3611ba036df02ef8b155e32be7557c4bf7b88dfa1a5aff6e91c6d82fe7fb135a"
NEW_PREFIX = "dsda_grid_target_stop_20261028_032943_2346732/"
OLD_ARCHIVE = REPO / "results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip"
OLD_SHA = "e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e"
OLD_PREFIX = "dsda_abs1e5_rerun_20261028_020753_2004611/"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rows(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def csv_bytes(records):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(records[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode()


def audit():
    require(digest(NEW_ARCHIVE.read_bytes()) == NEW_SHA, "New archive hash differs")
    require(
        digest(OLD_ARCHIVE.read_bytes()) == OLD_SHA,
        "Direct baseline archive hash differs",
    )
    with ZipFile(NEW_ARCHIVE) as new, ZipFile(OLD_ARCHIVE) as old:
        names = new.namelist()
        require(len(names) == len(set(names)), "Duplicate return member")
        require(
            all(
                not PurePosixPath(n).is_absolute()
                and ".." not in PurePosixPath(n).parts
                and n.startswith(NEW_PREFIX)
                for n in names
            ),
            "Unsafe or unexpected return member",
        )

        def new_read(name):
            return new.read(NEW_PREFIX + name)

        def data(name):
            return json.loads(new_read(name))

        manifest = data("reproduction/INPUT_MANIFEST.json")
        copied = manifest["copied_baseline_members"]
        for name, record in copied.items():
            actual = new_read("reproduction/" + name)
            require(
                digest(actual) == record["sha256"]
                and actual == old.read(record["archive_member"]),
                "Copied baseline evidence differs: " + name,
            )
        baseline_jobs = json.loads(
            old.read(OLD_PREFIX + "reproduction/inputs/jobs.json")
        )
        selected = [
            {k: j[k] for k in ("spec", "target", "hard_seconds")}
            for j in baseline_jobs
            if j["spec"]["scope"] == "grid"
        ]
        require(
            data("reproduction/inputs/jobs.json") == selected,
            "Grid cohort, targets, starts, or order differs",
        )
        for name, expected in manifest["source_sha256"].items():
            source = (WORKFLOW / name).read_bytes()
            require(
                digest(source) == expected
                and source == new_read("reproduction/" + name),
                "Published execution source differs: " + name,
            )
        for name in ("paired_runs.csv", "grid_budget_summary.csv", "verification.json"):
            require(
                (HERE / name).read_bytes() == new_read(name),
                "Published output differs: " + name,
            )
        for path in (HERE / "returned").rglob("*"):
            if path.is_file():
                name = path.relative_to(HERE / "returned").as_posix()
                require(
                    path.read_bytes() == new_read(name),
                    "Published evidence differs: " + name,
                )
        with tempfile.TemporaryDirectory(
            prefix="dsda-grid-publication-audit-"
        ) as temporary:
            for name in names:
                destination = Path(temporary) / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(new.read(name))
            checked = verify_saved_data(Path(temporary) / NEW_PREFIX.rstrip("/"))
        require(
            checked["status"] == "PASS", "Returned cohort did not pass verification"
        )
        paired = rows(new_read("paired_runs.csv"))
        cases = []
        changed = []
        transitions = Counter()
        for case in sorted({r["case"] for r in paired}):
            group = [r for r in paired if r["case"] == case]
            differences = [
                float(r["new_best_objective"]) - float(r["old_best_objective"])
                for r in group
            ]
            cases.append(
                dict(
                    case=case,
                    runs=len(group),
                    old_hits=sum(r["old_hit"] == "True" for r in group),
                    new_hits=sum(r["new_hit"] == "True" for r in group),
                    old_callbacks=sum(int(r["old_callbacks"]) for r in group),
                    new_callbacks=sum(int(r["new_callbacks"]) for r in group),
                    callback_delta=sum(int(r["callback_delta"]) for r in group),
                    earlier_termination_runs=sum(
                        r["early_termination"] == "True" for r in group
                    ),
                    unchanged_best_objectives=sum(v == 0 for v in differences),
                    less_improved_best_objectives=sum(v > 0 for v in differences),
                    improved_best_objectives=sum(v < 0 for v in differences),
                    maximum_objective_increase=max(differences),
                )
            )
        for row in paired:
            shortened = row["early_termination"] == "True"
            transitions[row["old_termination"], row["new_termination"], shortened] += 1
            if shortened:
                changed.append(row)
        transition_rows = [
            dict(
                old_reason=old_reason,
                new_reason=new_reason,
                fewer_callbacks=shortened,
                runs=count,
            )
            for (old_reason, new_reason, shortened), count in sorted(
                transitions.items()
            )
        ]
        differences = [
            float(r["new_best_objective"]) - float(r["old_best_objective"])
            for r in paired
        ]
        environment = data("execution_manifest.json")
        sessions = environment["sessions"]
        require(
            len(sessions) == 1
            and sessions[0]["executed"] == 1050
            and sessions[0]["reused"] == 0
            and sessions[0]["smoke_jobs"] == 3
            and sessions[0]["error"] is None,
            "Unexpected execution accounting",
        )
        smoke = data("sessions/1/smoke/smoke_summary.json")
        require(
            smoke["grid_jobs"] == 3
            and smoke["process_jobs"]
            == smoke["other_method_jobs"]
            == smoke["solver_calls"]
            == 0,
            "Smoke scope or solver calls differ",
        )
        require(
            "Ran 13 tests" in new_read("sessions/1/tests.log").decode()
            and "\nOK\n" in new_read("sessions/1/tests.log").decode(),
            "Server tests did not pass",
        )
        report = dict(
            **checked,
            archive_sha256=NEW_SHA,
            baseline_archive_sha256=OLD_SHA,
            baseline_members_compared_byte_for_byte=len(copied),
            published_execution_sources_compared=len(manifest["source_sha256"]),
            server_grid_smoke_runs=3,
            server_tests_passed=13,
            changed_callback_cases=sorted({r["case"] for r in changed}),
            unchanged_best_objectives=sum(v == 0 for v in differences),
            less_improved_best_objectives=sum(v > 0 for v in differences),
            improved_best_objectives=sum(v < 0 for v in differences),
            maximum_objective_increase=max(differences),
            changed_first_hit_indices=sum(
                r["old_first_hit"] != r["new_first_hit"] for r in paired
            ),
            shortened_runs_stopping_after_first_hit=sum(
                int(r["new_termination_callback"]) > int(r["new_first_hit"])
                for r in changed
            ),
            callback_reduction_percent=100
            * (checked["old_callbacks"] - checked["new_callbacks"])
            / checked["old_callbacks"],
            effective_cpus=sessions[0]["cpu_allocation"]["effective_cpus"],
            exclusive_reservation=False,
            server_revision=environment["repository_identity"]["head"],
            execution_source_base=environment["baseline"]["pr_head"],
            additional_nlp_calls=environment["additional_nlp_calls"],
        )
        outputs = {
            "audit.json": (
                json.dumps(report, indent=2, allow_nan=False) + "\n"
            ).encode(),
            "function_summary.csv": csv_bytes(cases),
            "earlier_termination_runs.csv": csv_bytes(changed),
            "termination_summary.csv": csv_bytes(transition_rows),
        }
        return report, outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-new", type=Path, help="Write reproducible outputs to a new directory"
    )
    args = parser.parse_args()
    report, outputs = audit()
    if args.write_new:
        args.write_new.mkdir(parents=True, exist_ok=False)
        for name, content in outputs.items():
            (args.write_new / name).write_bytes(content)
    else:
        for name, content in outputs.items():
            require(
                (HERE / name).read_bytes() == content,
                "Derived publication output differs: " + name,
            )
    print(json.dumps(report, indent=2))
