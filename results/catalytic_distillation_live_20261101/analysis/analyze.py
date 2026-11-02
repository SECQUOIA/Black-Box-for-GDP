"""Independently audit returned data; never import or run an optimizer or NLP solver."""

import argparse
import ast
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import io
import itertools
import json
import math
from pathlib import Path, PurePosixPath
import re
import sqlite3
import statistics
import subprocess
import tempfile
import zipfile
from zoneinfo import ZoneInfo

import numpy as np

PIN = "5580a7eacdc8b4098ba5c239822de2300e667a1c"
METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa", "uniform", "nomad", "miso")
BUDGETS = (25, 50, 100)
PREFIX = "catalytic_distillation_live/"
OUTER_SHA = "9518bf6ab26faed2d2b2b5e9834280c40a98c0c760679170d480e48112e78dab"
INNER_SHA = "1ff96f101b3e30cbb0c47663af13d5d8fc680eb1466c425868e1e25825718e26"
REFERENCE = (
    "results/catalytic_distillation_pilot_20261030/final_pilot_200_conopt/solves.csv"
)


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same(a, b):
    return (
        a == b
        if a is None or b is None
        else math.isclose(float(a), float(b), rel_tol=1e-11, abs_tol=1e-8)
    )


def positions(g):
    a = 2 + g[0]
    b = a + g[1]
    c = b + g[2] + 1
    d = c + g[3] + 1
    e = d + g[4]
    return [a, b, c, d, e, e + g[5]]


def gaps(p):
    a, b, c, d, e, f = p
    return (a - 2, b - a, c - b - 1, d - c - 1, e - d, f - e)


def rows(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def write_csv(path, values):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(values[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)


def validate_zip(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()
    check(len(names) == len(set(names)), "Duplicate archive members")
    check(
        all(
            not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts
            for n in names
        ),
        "Unsafe archive member",
    )
    check(archive.testzip() is None, "Archive CRC failure")
    return archive


def source(repo, name):
    return subprocess.check_output(["git", "-C", str(repo), "show", PIN + ":" + name])


def audit(result_dir, repo, output, outer_return):
    output.mkdir(parents=True, exist_ok=True)
    outer_bytes = outer_return.read_bytes()
    check(sha(outer_bytes) == OUTER_SHA, "Outer return SHA mismatch")
    outer = validate_zip(outer_bytes)
    check(
        outer_return.with_suffix(".zip.sha256").read_text().split()[0] == OUTER_SHA,
        "Outer checksum file differs",
    )
    returned = json.loads((result_dir / "wrapper_execution.json").read_text())
    original = next(
        (result_dir / "evidence").glob("catalytic_distillation_live_dantzig_*.zip")
    )
    raw_bytes = original.read_bytes()
    check(
        outer.read("catalytic_distillation_live_20261101/evidence/" + original.name)
        == raw_bytes,
        "Nested original archive differs",
    )
    check(sha(raw_bytes) == INNER_SHA, "Original returned archive SHA mismatch")
    check(
        original.stat().st_size <= 90_000_000,
        "Original archive exceeds publication limit",
    )
    check(
        original.with_suffix(".zip.sha256").read_text().split()[0] == INNER_SHA,
        "Inner checksum file differs",
    )
    z = validate_zip(raw_bytes)
    files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}

    def load(name):
        return json.loads(files[PREFIX + name])

    check(
        returned["revision"] == returned["expected_revision"] == PIN,
        "Execution revision differs",
    )
    check(
        returned["controller_exit_code"] == 0 and returned["error"] is None,
        "Controller failure",
    )
    preflight = returned["preflight"]
    check(
        preflight["passed"] and preflight["execution"]["exit_code"] == 0,
        "Preflight failed",
    )
    check(
        set(preflight["required_tests"]) <= set(preflight["passed_tests"])
        and len(preflight["required_tests"]) == 10,
        "Required preflight test absent",
    )
    check(
        preflight["preflight_cpu_binding"]["returncode"] == 0, "Real GAMS test failure"
    )
    check(
        preflight["versions"]["gams_version"] == "54.3.1"
        and preflight["versions"]["conopt_version"] == "4.39.1",
        "Recorded versions differ",
    )
    check(all(returned["startup_checks"].values()), "Startup verification missing")
    cpus = returned["cpus"]
    check(
        len({(c["socket"], c["core"]) for c in cpus}) == len(cpus) == 3,
        "Physical CPU overlap",
    )
    allowed = {c["cpu"] for c in cpus}
    check(
        allowed == {17, 38, 43} and all(17 <= c <= 48 for c in allowed),
        "Unexpected CPU set",
    )

    reference_paths = [
        "experiments/catalytic_distillation_live/run.py",
        "experiments/catalytic_distillation_live/case.py",
        "experiments/catalytic_distillation_live/run_dantzig.sh",
        "experiments/mixed_integer_dfo/run.py",
        "tests/test_catalytic_distillation_live.py",
        "gdp_models/catalytic_distillation/distillation_model_corrected.gms",
        "gdp_models/catalytic_distillation/solve_configuration.gms",
        "gdp_models/catalytic_distillation/init.gdx",
        REFERENCE,
    ]
    sources = {p: source(repo, p) for p in reference_paths}
    source_hashes = {p: sha(data) for p, data in sources.items()}
    check(
        source_hashes["tests/test_catalytic_distillation_live.py"]
        == preflight["preflight_cpu_binding"]["test_source_sha256"],
        "Preflight test source differs",
    )
    tree = ast.parse(sources["experiments/catalytic_distillation_live/run.py"])
    settings = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SETTINGS" for t in n.targets)
    )

    plan = load("plan.json")
    expected_ids = {
        f"{m}_B{b}_seed{s}" for m in METHODS for b in BUDGETS for s in range(10)
    }
    jobs = {j["job_id"]: j for j in plan["jobs"]}
    check(
        len(plan["jobs"]) == len(jobs) == 210 and set(jobs) == expected_ids,
        "Plan coverage mismatch",
    )
    check(
        plan["methods"] == list(METHODS)
        and plan["budgets"] == list(BUDGETS)
        and plan["seeds"] == list(range(10)),
        "Plan order differs",
    )
    pool = [p for p in itertools.product(range(7), repeat=6) if sum(p) <= 17]
    check(len(pool) == 54159, "Admissible space count differs")
    # Initial-design generation only: this performs no objective evaluation.
    for seed in range(10):
        rng = np.random.default_rng([20261031, seed])
        while True:
            chosen = [pool[i] for i in rng.choice(len(pool), size=7, replace=False)]
            if (
                np.linalg.matrix_rank(np.c_[np.ones(7), np.array(chosen, dtype=float)])
                == 7
            ):
                break
        check(
            plan["starts"][str(seed)] == [list(p) for p in chosen],
            f"Initial seed design changed: {seed}",
        )

    with tempfile.TemporaryDirectory(prefix="pr57-data-audit-") as temp:
        cache_path = Path(temp) / "cache.sqlite"
        cache_path.write_bytes(files[PREFIX + "cache.sqlite"])
        db = sqlite3.connect(cache_path.as_uri() + "?mode=ro&immutable=1", uri=True)
        check(
            db.execute("pragma integrity_check").fetchone()[0] == "ok",
            "SQLite integrity check failed",
        )
        cache = {
            tuple(json.loads(p)): json.loads(r)
            for p, r in db.execute("select gaps, record from responses")
        }
        provenance = json.loads(
            db.execute("select value from meta where key='provenance'").fetchone()[0]
        )
        db.close()
    for key, path in [
        ("model_sha256", "distillation_model_corrected.gms"),
        ("init_sha256", "init.gdx"),
        ("solve_configuration_sha256", "solve_configuration.gms"),
    ]:
        check(
            provenance[key]
            == source_hashes["gdp_models/catalytic_distillation/" + path],
            "Cache source hash mismatch: " + key,
        )
    check(
        provenance["solver"] == "conopt"
        and provenance["threads"] == 1
        and provenance["timeout_s"] == 300,
        "Cache solver protocol differs",
    )
    for p, r in cache.items():
        check(
            len(p) == 6
            and all(type(v) is int and 0 <= v <= 6 for v in p)
            and sum(p) <= 17,
            "Invalid cached coordinates",
        )
        check(r["positions"] == positions(p), "Cache coordinate mapping differs")
        row = r["solver_row"]
        check(
            r["accepted"] == (row["solvestat"] == 1 and row["modelstat"] in (1, 2)),
            "Cache acceptance differs",
        )
        check(
            same(r["objective"], row["zobj"] if r["accepted"] else None),
            "Cache objective differs",
        )

    pilot = rows(sources[REFERENCE])
    pilot_accepted = {
        gaps([int(r[k]) for k in ("f1", "c1", "c2", "c3", "f2", "b")]): float(r["zobj"])
        for r in pilot
        if r["solvestat"] == "1" and r["modelstat"] in ("1", "2")
    }
    accepted_union = {p: r["objective"] for p, r in cache.items() if r["accepted"]}
    for p, value in pilot_accepted.items():
        if all(0 <= v <= 6 for v in p) and sum(p) <= 17:
            accepted_union[p] = min(accepted_union.get(p, math.inf), value)
    best_point = min(accepted_union, key=accepted_union.get)
    best = accepted_union[best_point]
    original_best = load("best_known.json")
    check(
        original_best["objective"] == best
        and original_best["gaps"] == list(best_point)
        and original_best["positions"] == positions(best_point),
        "Best-known reconstruction differs",
    )
    check(
        original_best["distinct_solved"] == len(cache)
        and original_best["distinct_accepted"] == len(accepted_union),
        "Best-known cache/reference counts differ",
    )
    check(
        all(
            (result_dir / name).read_bytes() == files[PREFIX + name]
            for name in ("runs.csv", "conditions.csv", "best_known.json")
        ),
        "Returned summary copies differ",
    )
    summaries = {r["job_id"]: r for r in rows(files[PREFIX + "runs.csv"])}
    check(
        len(summaries) == 210 and set(summaries) == expected_ids,
        "runs.csv coverage differs",
    )
    result_names = [
        n for n in files if re.fullmatch(PREFIX + r"runs/[^/]+/result.json", n)
    ]
    check(
        len(result_names) == 210
        and {n.split("/")[-2] for n in result_names} == expected_ids,
        "Result coverage differs",
    )
    check(
        not any(n.endswith("/worker_failure.json") for n in files),
        "Worker failure record present",
    )
    records, all_points, accepted_points, unaccepted_callbacks = (
        [],
        set(),
        set(),
        Counter(),
    )
    attempts, cap_rejections = [], []
    method_events = defaultdict(Counter)
    for jid in sorted(expected_ids):
        job = jobs[jid]
        method, budget, seed = job["method"], job["budget"], job["seed"]
        check(
            jid == f"{method}_B{budget}_seed{seed}"
            and job["settings"] == settings[method],
            "Job settings differ: " + jid,
        )
        check(
            job["lower"] == [0] * 6
            and job["upper"] == [6] * 6
            and job["starts"] == plan["starts"][str(seed)],
            "Job input differs: " + jid,
        )
        directory = "runs/" + jid + "/"
        r = load(directory + "result.json")
        check(
            r["spec"] == load(directory + "spec.json") == job,
            "Result spec differs: " + jid,
        )
        check(
            r["status"] == "completed" and r["error"] is None,
            "Non-completed run: " + jid,
        )
        check(
            len(r["cpu"]) == 1
            and r["cpu"][0] in allowed
            and r["host"] == "dantzig.ecn.purdue.edu",
            "Result affinity/host differs",
        )
        e = [
            json.loads(line)
            for line in files[PREFIX + directory + "callbacks.jsonl"].splitlines()
            if line
        ]
        points = [tuple(x["point"]) for x in e]
        check(
            7 <= len(e) == r["evaluations"] <= budget,
            "Evaluation budget exceeded: " + jid,
        )
        check(
            [x["index"] for x in e] == list(range(1, len(e) + 1)),
            "Callback indices differ",
        )
        check(
            [list(p) for p in points[:7]] == job["starts"], "Shared-start order changed"
        )
        check(len(set(points)) == r["distinct_points"], "Distinct count differs")
        check(len(set(points)) == len(points), "Repeated evaluated point: " + jid)
        accepted = [x for x in e if x["accepted"]]
        for x, p in zip(e, points):
            check(
                len(p) == 6 and all(type(v) is int and 0 <= v <= 6 for v in p),
                "Out-of-box coordinate",
            )
            all_points.add(p)
            if sum(p) > 17:
                check(
                    not x["accepted"]
                    and x["raw_objective"] is None
                    and x["status"] == "logical_infeasible"
                    and x["point_cost_s"] == 0,
                    "Logical rejection mismatch",
                )
            else:
                check(p in cache, "Admissible callback absent from cache")
                c = cache[p]
                check(
                    x["accepted"] == c["accepted"]
                    and same(x["raw_objective"], c["objective"])
                    and same(x["point_cost_s"], c["solve_wall_s"]),
                    "Callback/cache mismatch: " + jid,
                )
                if not c["accepted"]:
                    unaccepted_callbacks[c["status"]] += 1
            if x["accepted"]:
                accepted_points.add(p)
            method_events[method][x["status"]] += 1
        first_best = min(accepted, key=lambda x: x["raw_objective"], default=None)
        obj = first_best["raw_objective"] if first_best else None
        check(
            same(obj, r["best_objective"])
            and r["best_index"] == (first_best["index"] if first_best else None),
            "Best objective/index differs",
        )
        check(
            r["best_point"] == (first_best["point"] if first_best else None),
            "Best point differs",
        )
        check(
            r["best_positions"]
            == (positions(first_best["point"]) if first_best else None),
            "Best positions differ",
        )
        check(
            r["accepted_evaluations"] == len(accepted)
            and r["logical_rejections"]
            == sum(x["status"] == "logical_infeasible" for x in e),
            "Response counts differ",
        )
        point_s = sum(x["point_cost_s"] for x in e)
        callback_s = sum(x["lookup_wall_s"] for x in e)
        overhead_s = r["worker_wall_s"] - callback_s
        completion_s = overhead_s + point_s
        for k, value in [
            ("point_cost_s", point_s),
            ("callback_wall_s", callback_s),
            ("search_overhead_s", overhead_s),
            ("completion_s", completion_s),
        ]:
            check(
                math.isfinite(value) and value >= 0 and same(value, r[k]),
                "Timing mismatch: " + jid + ":" + k,
            )
        if method in ("nomad", "miso"):
            a = r["details"]["attempts"]
            check(a == [{"attempt": 1, "exitcode": 0}], "Native retry/crash present")
            original_events = [
                json.loads(line)
                for line in files[PREFIX + directory + "attempt1.jsonl"].splitlines()
                if line
            ]
            check(
                len(original_events) == len(e)
                and all(
                    all(x[k] == y[k] for k in x) for x, y in zip(original_events, e)
                ),
                "Native attempt events differ",
            )
            check(not r["details"]["invalid"], "Invalid native requests")
            attempts.append(dict(job_id=jid, attempts=len(a), exit_code=0))
            cap_rejections.append(
                dict(
                    job_id=jid,
                    method=method,
                    rejected_after_cap=r["details"]["overruns"],
                )
            )
        hit = obj is not None and abs(obj - best) <= 1e-5 * max(1, abs(best))
        gap = obj - best if obj is not None else None
        row = dict(
            job_id=jid,
            method=method,
            budget=budget,
            seed=seed,
            status=r["status"],
            evaluations=len(e),
            accepted=len(accepted),
            logical_rejections=r["logical_rejections"],
            unaccepted_nlp_callbacks=len(e) - len(accepted) - r["logical_rejections"],
            distinct_points=len(set(points)),
            best_objective=obj,
            gap_to_best_known=gap,
            hit=hit,
            best_index=r["best_index"],
            worker_wall_s=r["worker_wall_s"],
            callback_wall_s=callback_s,
            completion_s=completion_s,
            point_cost_s=point_s,
            search_overhead_s=overhead_s,
            recorded_solved_now=r["solved_now"],
            cpu=r["cpu"][0],
            finished_utc=r["finished_utc"],
        )
        for k, value in summaries[jid].items():
            check(k in row, "Unverified summary field: " + k)
            expected = row[k]
            check(
                value == str(expected)
                if isinstance(expected, (str, bool, int))
                else value == ""
                if expected is None
                else same(value, expected),
                "runs.csv mismatch: " + jid + ":" + k,
            )
        records.append(row)

    groups, conditions = defaultdict(list), []
    for r in records:
        groups[r["method"], r["budget"]].append(r)
    original_conditions = {
        (r["method"], int(r["budget"])): r
        for r in rows(files[PREFIX + "conditions.csv"])
    }
    check(
        set(original_conditions) == set(groups) and len(original_conditions) == 21,
        "Condition coverage differs",
    )
    for (method, budget), group in sorted(groups.items()):
        gap_values = [r["gap_to_best_known"] for r in group]
        time_values = [r["completion_s"] for r in group]
        q1, _, q3 = np.quantile(gap_values, [0.25, 0.5, 0.75], method="linear")
        c = dict(
            method=method,
            budget=budget,
            runs=len(group),
            hits=sum(r["hit"] for r in group),
            completed=len(group),
            mean_gap=statistics.mean(gap_values),
            median_gap=statistics.median(gap_values),
            q1_gap=float(q1),
            q3_gap=float(q3),
            minimum_gap=min(gap_values),
            maximum_gap=max(gap_values),
            median_completion_s=statistics.median(time_values),
            median_worker_wall_s=statistics.median(r["worker_wall_s"] for r in group),
            evaluations=sum(r["evaluations"] for r in group),
            accepted_callbacks=sum(r["accepted"] for r in group),
            logical_rejections=sum(r["logical_rejections"] for r in group),
            unaccepted_nlp_callbacks=sum(r["unaccepted_nlp_callbacks"] for r in group),
            original_upper_middle_gap=sorted(gap_values)[len(group) // 2],
            original_upper_middle_completion_s=sorted(time_values)[len(group) // 2],
        )
        old = original_conditions[method, budget]
        for k in ("runs", "hits", "completed"):
            check(int(old[k]) == c[k], "Condition count differs")
        check(
            same(old["median_gap"], c["original_upper_middle_gap"])
            and same(
                old["median_completion_s"], c["original_upper_middle_completion_s"]
            ),
            "Original upper-middle statistic differs",
        )
        conditions.append(c)

    controller = files[PREFIX + "controller.log"].decode()
    terminal = re.findall(
        r"^(\S+)\s+cpu\s+(\d+)\s+rc\s+(-?\d+)\s+(\S+)\s*$", controller, re.M
    )
    check(
        len(terminal) == 210
        and {r[0] for r in terminal} == expected_ids
        and all(r[2:] == ("0", "completed") for r in terminal),
        "Controller terminal coverage/exit failure",
    )
    start = datetime.fromisoformat(returned["started_utc"])
    finish = datetime.fromisoformat(returned["finished_utc"])
    wall = (finish - start).total_seconds()
    cache_counts = dict(Counter(r["status"] for r in cache.values()))
    totals = {
        k: sum(r[k] for r in records)
        for k in [
            "evaluations",
            "accepted",
            "logical_rejections",
            "unaccepted_nlp_callbacks",
            "worker_wall_s",
            "completion_s",
            "point_cost_s",
            "callback_wall_s",
            "search_overhead_s",
            "recorded_solved_now",
        ]
    }
    totals.update(
        unique_cached_configurations=len(cache),
        unique_accepted_cache=sum(r["accepted"] for r in cache.values()),
        unique_cache_solve_wall_s=sum(r["solve_wall_s"] for r in cache.values()),
        unique_all_callback_points=len(all_points),
        unique_accepted_callback_points=len(accepted_points),
        target_hits=sum(r["hit"] for r in records),
        target_misses=sum(not r["hit"] for r in records),
        repeated_admissible_requests_across_runs=totals["evaluations"]
        - totals["logical_rejections"]
        - len(cache),
    )
    check(
        set(cache) == {p for p in all_points if sum(p) <= 17},
        "Cache contains unreferenced or missing configurations",
    )
    summary = dict(
        passed=True,
        execution_revision=PIN,
        expected_runs=210,
        completed_runs=210,
        missing=0,
        duplicates=0,
        worker_failures=0,
        worker_timeouts=0,
        native_crashes=0,
        native_reruns=0,
        native_attempts=len(attempts),
        admitted_budget_excess=0,
        repeated_evaluations_within_run=0,
        invalid_admitted_coordinates=0,
        rejected_after_budget_cap=sum(r["rejected_after_cap"] for r in cap_rejections),
        rejected_cap_jobs=sum(r["rejected_after_cap"] > 0 for r in cap_rejections),
        under_budget_runs=[
            dict(job_id=r["job_id"], evaluations=r["evaluations"], budget=r["budget"])
            for r in records
            if r["evaluations"] < r["budget"]
        ],
        best_known=original_best,
        pilot_best=min(pilot_accepted.values()),
        best_improvement=min(pilot_accepted.values()) - best,
        hit_absolute_tolerance=1e-5 * max(1, abs(best)),
        totals=totals,
        cache_statuses=cache_counts,
        unaccepted_callback_statuses=dict(unaccepted_callbacks),
        cache_returncodes=dict(
            Counter(str(r["solver_row"]["returncode"]) for r in cache.values())
        ),
        nonzero_nlp_returncodes=[
            dict(
                gaps=list(p),
                positions=r["positions"],
                accepted=r["accepted"],
                objective=r["objective"],
                status=r["status"],
                returncode=r["solver_row"]["returncode"],
                modelstat=r["solver_row"]["modelstat"],
                solvestat=r["solver_row"]["solvestat"],
            )
            for p, r in cache.items()
            if r["solver_row"]["returncode"] != 0
        ],
        nlp_returncode_note="The original acceptance predicate uses solvestat == 1 and modelstat in (1, 2), without checking process returncode; both returncode-7 records are retained, including the accepted record with objective 25273.891950.",
        nlp_total_exact=False,
        nlp_accounting_note="3,499 cache rows and 3,500 recorded solve counters do not establish an exact total of actual NLP calls: simultaneous cache misses may execute duplicate solves, and non-forked callback counters can omit the losing solve.",
        preflight_required_passed=10,
        preflight_raw_log_returned=False,
        preflight_evidence_note="The returned wrapper records all ten required tests passed across the designated environments; skips from the first environment are followed by passes in the method-specific environments. The raw test log and private GAMS logs remain on Dantzig.",
        gams_version=preflight["versions"]["gams_version"],
        conopt_version=preflight["versions"]["conopt_version"],
        cpu_topology=cpus,
        started_utc=start.isoformat(),
        finished_utc=finish.isoformat(),
        started_indiana=start.astimezone(
            ZoneInfo("America/Indiana/Indianapolis")
        ).isoformat(),
        finished_indiana=finish.astimezone(
            ZoneInfo("America/Indiana/Indianapolis")
        ).isoformat(),
        campaign_wall_s=wall,
        worker_occupied_fraction=totals["worker_wall_s"] / (3 * wall),
        original_archive=dict(
            name=original.name,
            bytes=len(raw_bytes),
            sha256=sha(raw_bytes),
            crc_passed=True,
        ),
        outer_archive_expected_sha256=OUTER_SHA,
        uploaded_return=dict(
            name=outer_return.name,
            bytes=len(outer_bytes),
            sha256=sha(outer_bytes),
            crc_passed=True,
        ),
        source_sha256=source_hashes,
        cache_provenance=provenance,
        original_median_convention="Original conditions.csv uses sorted(values)[n//2], the sixth observation for ten seeds. Independent medians average the fifth and sixth, and quartiles use linear interpolation.",
        analysis_numpy_version=np.__version__,
        optimizer_or_nlp_runs_locally=0,
    )
    write_json(output / "validation.json", summary)
    write_csv(output / "runs_recomputed.csv", records)
    write_csv(output / "conditions_recomputed.csv", conditions)
    write_csv(output / "target_hits.csv", [r for r in records if r["hit"]])
    write_csv(output / "native_attempts.csv", attempts)
    write_csv(output / "rejected_budget_requests.csv", cap_rejections)
    write_json(
        output / "ARCHIVE_MEMBER_SHA256.json",
        {n: sha(data) for n, data in sorted(files.items())},
    )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in [
                    "passed",
                    "completed_runs",
                    "campaign_wall_s",
                    "best_known",
                    "totals",
                    "cache_statuses",
                    "admitted_budget_excess",
                    "rejected_after_budget_cap",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--outer-return", type=Path)
    args = parser.parse_args()
    audit(
        args.result_dir.resolve(),
        args.repository.resolve(),
        args.output.resolve(),
        (args.outer_return or args.result_dir / "evidence/RETURN_B.zip").resolve(),
    )
