"""Grid-only input validation and data-only comparison against the second run."""

import csv
import hashlib
import itertools
import io
import json
import math
from pathlib import Path

from adopted_analysis import hit

BUDGETS = (10, 30, 50, 70, 100)
EXPECTED = 1050


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def events(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def key(spec):
    return spec["scope"], spec["case"], int(spec["budget"]), int(spec["seed"])


def validate_job(job):
    s = job["spec"]
    require(
        s["scope"] == "grid" and s["method"] == "dsda", "Only Grid D-SDA is permitted"
    )
    require(s["budget"] in BUDGETS and s["seed"] in range(10), "Invalid budget or seed")
    require(
        s["settings"] == dict(diagonal=True, tie_break="first", tol=1e-12),
        "Internal settings changed",
    )
    require(s["lower"] == [0, 0] and s["upper"] == [30, 30], "Candidate domain changed")
    require(
        len(s["starts"]) == 3
        and all(
            len(p) == 2 and all(0 <= v <= 30 and int(v) == v for v in p)
            for p in s["starts"]
        ),
        "Invalid initial design",
    )
    require(job["hard_seconds"] is None, "Grid watchdog policy changed")
    require(math.isfinite(job["target"]), "Missing finite target")
    require(
        Path(s["job_id"]).name == s["job_id"] and s["job_id"] not in (".", ".."),
        "Invalid job identifier",
    )


def validate_cohort(jobs):
    for job in jobs:
        validate_job(job)
    keys = [key(j["spec"]) for j in jobs]
    require(
        len(keys) == len(set(keys)) == EXPECTED,
        "Incomplete or duplicate 1050-pair Grid cohort",
    )
    require(
        len({j["spec"]["job_id"] for j in jobs}) == EXPECTED, "Duplicate job identifier"
    )
    cases = {k[1] for k in keys}
    require(len(cases) == 21, "Expected 21 functions")
    expected = {("grid", c, b, s) for c in cases for b in BUDGETS for s in range(10)}
    require(
        set(keys) == expected,
        "Every function-budget must contain exactly seeds 0 through 9",
    )
    return jobs


def verify_grid(path, spec):
    with Path(path).open() as f:
        rows = list(csv.DictReader(f))
    points = [(int(r["x"]), int(r["y"])) for r in rows]
    domain = set(
        itertools.product(
            *(range(lo, hi + 1) for lo, hi in zip(spec["lower"], spec["upper"]))
        )
    )
    require(
        len(points) == len(set(points)) and set(points) == domain,
        "Missing or duplicate lookup response: " + str(path),
    )
    require(
        all(math.isfinite(float(r["z_norm"])) for r in rows), "Invalid lookup value"
    )


def verify_inputs(root):
    root = Path(root)
    inventory = read(root / "SHA256SUMS.json")
    for name, expected in inventory.items():
        path = (root / name).resolve()
        require(
            path.is_relative_to(root.resolve()) and sha(path) == expected,
            "Input/source hash mismatch: " + name,
        )
    jobs = validate_cohort(read(root / "inputs/jobs.json"))
    seen = set()
    for job in jobs:
        s = job["spec"]
        if s["case"] not in seen:
            verify_grid(root / "inputs/grids" / (s["case"] + ".csv"), s)
            seen.add(s["case"])
        old = read(root / "baseline_runs" / s["job_id"] / "result.json")
        es = events(root / "baseline_runs" / s["job_id"] / "callbacks.jsonl")
        require(
            old["spec"] == s and old["improvement_abs_tol"] == 1e-5,
            "Wrong direct comparison baseline",
        )
        require(
            old["status"] == "completed"
            and len(es) == old["evaluations"] <= s["budget"],
            "Incomplete baseline run",
        )
        require([e["point"] for e in es[:3]] == s["starts"], "Initial design mismatch")
        require(
            all(e["accepted"] and math.isfinite(e["raw_objective"]) for e in es),
            "Invalid baseline response",
        )
        require(
            old["best_objective"] == min(e["raw_objective"] for e in es),
            "Baseline incumbent mismatch",
        )
        require(
            old["hit"] == hit(old["best_objective"], job["target"]),
            "Baseline success-rule mismatch",
        )
    return jobs


def without_times(value):
    if isinstance(value, dict):
        return {
            k: len(v) if k == "objective_wall_times" else without_times(v)
            for k, v in value.items()
            if k not in ("wall_time_s", "lookup_wall_s")
        }
    if isinstance(value, list):
        return [without_times(v) for v in value]
    return value


def first_hit(es, target):
    return next(
        (e["index"] for e in es if e["accepted"] and hit(e["raw_objective"], target)),
        None,
    )


def audit_one(root, job, directory, expected_cpu=None):
    validate_job(job)
    directory = Path(directory)
    s = job["spec"]
    old_dir = Path(root) / "baseline_runs" / s["job_id"]
    old = read(old_dir / "result.json")
    old_events = events(old_dir / "callbacks.jsonl")
    new = read(directory / "result.json")
    es = events(directory / "callbacks.jsonl")
    require(
        new["spec"] == s
        and new["improvement_abs_tol"] == 1e-5
        and new["target_stop_rule"] == "adopted_analysis.hit",
        "Execution configuration changed",
    )
    require(
        new["status"] == "completed" and new["error"] is None, "Unsuccessful worker"
    )
    require(
        new["solver_calls"] == 0
        and new["process_nlp_calls"] == 0
        and not new["blocked_solver_or_process_attempts"],
        "Solver or other-process attempt",
    )
    if expected_cpu is not None:
        require(
            new["effective_cpus"] == [expected_cpu], "Actual worker affinity mismatch"
        )
    require(
        [e["index"] for e in es] == list(range(1, len(es) + 1)),
        "Callback indices differ",
    )
    require(
        [e["point"] for e in es[:3]] == s["starts"] and len(es) <= s["budget"],
        "Initial order or budget changed",
    )
    require(
        len(es) <= len(old_events)
        and without_times(es) == without_times(old_events[: len(es)]),
        "Unexpected callback path/value change before target stopping",
    )
    require(
        all(e["accepted"] and math.isfinite(e["raw_objective"]) for e in es),
        "Invalid accepted response",
    )
    best = min(e["raw_objective"] for e in es)
    require(
        new["best_objective"] == best and new["evaluations"] == len(es),
        "Observed incumbent or callback count differs",
    )
    require(
        new["hit"] == hit(best, job["target"])
        and new["first_hit"] == first_hit(es, job["target"]),
        "Common success or first-hit mismatch",
    )
    require(
        new["category"] == ("target_reached" if new["hit"] else "target_not_reached"),
        "Outcome category differs",
    )
    require(
        new["termination_callback"] == len(es)
        and new["last_callback"] == es[-1]["point"],
        "Termination callback mismatch",
    )
    algo = new["algorithm_result"]
    old_algo = old["algorithm_result"]
    runs = algo["runs"]
    require(
        without_times(runs) == without_times(old_algo["runs"][: len(runs)]),
        "Unexpected descent movement/state change",
    )
    require(
        new["path"] == [r["path"] for r in runs],
        "Movement path differs from descent states",
    )
    for name in ("ordered_starting_points", "starting_point_values"):
        require(algo[name] == old_algo[name], "Start ranking changed")
    checks = []
    count = 3
    for index, run in enumerate(runs, 1):
        count += run["point_evaluations"]
        if run["stopped_early"]:
            require(index == len(runs), "Continuation after budget stop")
            break
        observed = min(e["raw_objective"] for e in es[:count])
        reached = hit(observed, job["target"])
        checks.append(
            dict(
                descent_index=index,
                callback=count,
                observed_incumbent=observed,
                target=job["target"],
                reached=reached,
            )
        )
        require(
            not reached or index == len(runs),
            "Continued after successful target checkpoint",
        )
    require(
        algo["target_stop_checks"] == checks,
        "Target checkpoint location or observed incumbent differs",
    )
    require(count == len(es), "Descent callbacks do not account for total budget")
    target_stopped = bool(
        checks and checks[-1]["reached"] and not runs[-1]["stopped_early"]
    )
    expected_reason = algo["stop_reason"] or "all_ranked_starts_exhausted"
    require(new["termination"] == expected_reason, "Termination reason mismatch")
    require(
        (new["termination"] == "target_common_success") == target_stopped,
        "Target stopping differs from common success checkpoint",
    )
    require(
        len(es) == len(old_events) or target_stopped,
        "Truncation not explained by target checkpoint",
    )
    return dict(
        **{k: s[k] for k in ("scope", "case", "budget", "seed")},
        old_hit=old["hit"],
        new_hit=new["hit"],
        old_category=old["category"],
        new_category=new["category"],
        old_best_objective=old["best_objective"],
        new_best_objective=best,
        old_callbacks=old["evaluations"],
        new_callbacks=len(es),
        callback_delta=len(es) - old["evaluations"],
        old_first_hit=old["first_hit"],
        new_first_hit=new["first_hit"],
        old_termination_callback=old["evaluations"],
        new_termination_callback=len(es),
        old_termination=old["termination"],
        new_termination=new["termination"],
        early_termination=len(es) < len(old_events),
        callback_prefix_verified=True,
        descent_prefix_verified=True,
        old_search_s=old["search_s"],
        new_search_s=new["search_s"],
        status="verified",
    )


def csvwrite(path, rows):
    with Path(path).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyze(root, out, save=True):
    jobs = verify_inputs(root)
    out = Path(out)
    paired = []
    issues = []
    known = {j["spec"]["job_id"] for j in jobs}
    present = (
        {p.name for p in (out / "runs").iterdir()} if (out / "runs").exists() else set()
    )
    require(
        present <= known, "Unexpected/duplicate/misnamed run directory or non-Grid job"
    )
    for job in jobs:
        s = job["spec"]
        directory = out / "runs" / s["job_id"]
        old = read(Path(root) / "baseline_runs" / s["job_id"] / "result.json")
        try:
            process = read(directory / "process.json")
            require(
                process["returncode"] == 0 and process["watchdog_seconds"] is None,
                "Worker completion policy differs",
            )
            record = audit_one(root, job, directory, process["cpu"])
        except Exception as exc:
            status = "missing" if not directory.exists() else "failed_verification"
            issues.append(dict(job=s["job_id"], status=status, error=str(exc)))
            record = dict(
                **{k: s[k] for k in ("scope", "case", "budget", "seed")},
                old_hit=old["hit"],
                new_hit=None,
                old_callbacks=old["evaluations"],
                new_callbacks=None,
                status=status,
            )
        paired.append(record)
    fields = list(dict.fromkeys(k for r in paired for k in r))
    paired_table = [{k: r.get(k) for k in fields} for r in paired]

    def aggregate(group, budget):
        valid = [r for r in group if r["status"] == "verified"]
        return dict(
            budget=budget,
            expected=len(group),
            completed=len(valid),
            failed=sum(r["status"] == "failed_verification" for r in group),
            missing=sum(r["status"] == "missing" for r in group),
            old_hits=sum(r["old_hit"] for r in group),
            new_hits=sum(r["new_hit"] for r in valid),
            old_callbacks=sum(r["old_callbacks"] for r in group),
            new_callbacks=sum(r["new_callbacks"] for r in valid),
            callback_delta=sum(r["callback_delta"] for r in valid),
            early_terminations=sum(r["early_termination"] for r in valid),
            changed_hits=sum(r["old_hit"] != r["new_hit"] for r in valid),
        )

    summaries = [aggregate([r for r in paired if r["budget"] == b], b) for b in BUDGETS]
    total = aggregate(paired, "all")
    verification = dict(
        status="PASS" if not issues else "INCOMPLETE_OR_FAILED",
        **total,
        missing_or_failed_jobs=issues,
        callback_prefixes_verified=total["completed"],
        descent_prefixes_verified=total["completed"],
        unexpected_success_changes=[
            r
            for r in paired
            if r["status"] == "verified" and r["old_hit"] != r["new_hit"]
        ],
        process_jobs=0,
        other_method_jobs=0,
        additional_solver_calls=0,
    )
    for name, rows in [
        ("paired_runs.csv", paired_table),
        ("grid_budget_summary.csv", summaries),
    ]:
        if save:
            csvwrite(out / name, rows)
        else:
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(
                stream, fieldnames=list(rows[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            require(
                (out / name).read_bytes() == stream.getvalue().encode(),
                "Derived table mismatch: " + name,
            )
    if save:
        write(out / "verification.json", verification)
        (out / "README.md").write_text(
            "\n".join(
                [
                    "# Grid D-SDA common-success target stopping",
                    "",
                    "This follows the second absolute-improvement 1e-5 D-SDA experiment and changes only the Grid target stopping predicate and its observed incumbent.",
                    "The checkpoint remains after a completed descent and after the pre-existing budget-stop check, before the next ranked start.",
                    "The target is retained from each baseline job and the predicate is the unchanged adopted_analysis.hit function.",
                    "Movement acceptance remains old_value - new_value > 1e-5, and ties and internal numerical settings retain tol=1e-12.",
                    "No immediate callback-level stopping is added and the first target callback can precede the termination callback.",
                    f"The cohort has {total['expected']} Grid jobs, {total['completed']} verified completions, {total['failed']} failed verifications, and {total['missing']} missing runs.",
                    f"Target hits change from {total['old_hits']} to {total['new_hits']}, and callbacks change from {total['old_callbacks']} to {total['new_callbacks']} among the reported records.",
                    "Incomplete rows retain the full cohort denominator and are listed in verification.json.",
                    "Only saved Grid responses are evaluated and no NLP, GAMS, SCIP, Process job, or other optimization method is run.",
                    "CPU selection observes an idle SMT pair and affinity pins one logical CPU, without exclusive reservation.",
                    "Wall times are retained without a speedup claim and historical configuration-cost estimates are not reused.",
                    "Process records and existing representative manuscript tables and figures are preserved, and these results are not automatically adopted into the manuscript or Overleaf.",
                    "The reproduction directory contains sealed inputs and source, and execution_manifest.json records environment and execution sessions.",
                    "Run python reproduction/verify.py --results . from this result directory to verify stored data without a search or solver.",
                ]
            )
            + "\n"
        )
    else:
        require(
            read(out / "verification.json") == verification,
            "Verification summary mismatch",
        )
    return verification
