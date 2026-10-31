"""Independently audit saved D-SDA results; never import or run an optimizer."""

from collections import Counter, defaultdict
from datetime import datetime
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import zipfile
from zoneinfo import ZoneInfo

from reference_inputs import reference_bytes

ROOT = Path(__file__).resolve().parents[1]
PIN = "c186408728c6f95ac33a5465edd53035d85c5620"
RETURN_SHA = "aac54f826a19ebd81b5dfd376e792badcb79586161ce3c622fdd24e4b61ad88f"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def close(a, b):
    return (
        a is None
        and b is None
        or a is not None
        and b is not None
        and math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-10)
    )


def csv_rows(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def events(data):
    return [json.loads(line) for line in data.decode().splitlines() if line]


def checked_zip(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    require(len(names) == len(set(names)), "Duplicate ZIP member")
    require(
        all(not n.startswith("/") and ".." not in Path(n).parts for n in names),
        "Unsafe ZIP member",
    )
    require(z.testzip() is None, "ZIP CRC failure")
    return z


def zroot(z):
    roots = {n.split("/")[0] for n in z.namelist()}
    require(len(roots) == 1, "Unexpected ZIP roots")
    return next(iter(roots)) + "/"


def write_json(name, data):
    (ROOT / name).write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def write_csv(name, rows):
    require(rows, "Empty output table: " + name)
    with (ROOT / "analysis" / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def quantile(values, q):
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def output_hashes(z, prefix):
    name = prefix + "OUTPUT_SHA256SUMS.json"
    if name not in z.namelist():
        return 0
    hashes = json.loads(z.read(name))
    for name, value in hashes.items():
        require(sha(z.read(prefix + name)) == value, "Reference member hash: " + name)
    return len(hashes)


def summarize_pair(rows, cohort):
    return dict(
        cohort=cohort,
        runs=len(rows),
        previous_hits=sum(r["previous_hit"] for r in rows),
        new_hits=sum(r["new_hit"] for r in rows),
        gained_hits=sum(r["new_hit"] and not r["previous_hit"] for r in rows),
        lost_hits=sum(r["previous_hit"] and not r["new_hit"] for r in rows),
        objective_improvements=sum(r["objective_improved"] for r in rows),
        objective_regressions=sum(r["objective_worsened"] for r in rows),
        previous_callbacks=sum(r["previous_evaluations"] for r in rows),
        previous_repeated_callbacks=sum(r["previous_repeats"] for r in rows),
        new_callbacks=sum(r["new_evaluations"] for r in rows),
        previous_point_cost_s=math.fsum(r["previous_point_cost_s"] for r in rows),
        new_point_cost_s=math.fsum(r["new_point_cost_s"] for r in rows),
        median_previous_completion_s=statistics.median(
            r["previous_completion_s"] for r in rows
        ),
        median_new_completion_s=statistics.median(r["new_completion_s"] for r in rows),
    )


def main():
    provenance = json.loads((ROOT / "PROVENANCE.json").read_text())
    for name, info in provenance.items():
        require(
            sha(reference_bytes(name)) == info["sha256"],
            "Reference/source hash: " + name,
        )
    raw = (ROOT / "evidence/RETURN_A.zip").read_bytes()
    require(sha(raw) == RETURN_SHA, "Return SHA256 differs")
    require(
        (ROOT / "evidence/RETURN_A.zip.sha256").read_text().split()[0] == RETURN_SHA,
        "Return sidecar differs",
    )
    outer = checked_zip(raw)
    op = zroot(outer)
    inner_name = next(n for n in outer.namelist() if n.endswith(".zip"))
    inner_data = outer.read(inner_name)
    require(
        outer.read(inner_name + ".sha256").decode().split()[0] == sha(inner_data),
        "Inner ZIP hash",
    )
    current = checked_zip(inner_data)
    cp = zroot(current)
    for name in (
        "manifest.json",
        "runs.csv",
        "checks.csv",
        "checks.json",
        "condition_summary.csv",
    ):
        require(
            outer.read(op + name) == current.read(cp + name),
            "Packaged summary differs: " + name,
        )
    manifest = json.loads(current.read(cp + "manifest.json"))
    execution = json.loads(outer.read(op + "wrapper_execution.json"))
    require(
        manifest["git_head"] == execution["revision"] == PIN
        and manifest["git_status"] == "",
        "Execution revision/source changed",
    )
    require(
        execution["exit_code"] == 0 and manifest["process_nlp_calls"] == 0,
        "Execution status or NLP calls",
    )
    expected_hashes = {
        "archive_sha256": "reference/process_reference.zip",
        "grid_archive_sha256": "reference/grid_reference.zip",
        "grid_costs_sha256": "reference/grid_point_timings.csv",
        "script_sha256": "source/run_no_revisit.py",
        "grid_dsda_sha256": "source/grid_dsda.py",
    }
    for field, filename in expected_hashes.items():
        require(
            manifest[field] == provenance[filename]["sha256"],
            "Execution provenance: " + field,
        )
    process = checked_zip(reference_bytes("reference/process_reference.zip"))
    grid = checked_zip(reference_bytes("reference/grid_reference.zip"))
    previous_restart = checked_zip(
        reference_bytes("reference/previous_process_restarts.zip")
    )
    pp, gp, rp = zroot(process), zroot(grid), zroot(previous_restart)
    member_hashes = output_hashes(process, pp) + output_hashes(grid, gp)
    sealed = json.loads(process.read(pp + "reproduction/SHA256SUMS.json"))
    for name, digest in sealed.items():
        require(
            sha(process.read(pp + "reproduction/" + name)) == digest,
            "Sealed input member: " + name,
        )
    jobs_list = json.loads(process.read(pp + "reproduction/inputs/jobs.json"))
    jobs = {j["spec"]["job_id"]: j for j in jobs_list}
    require(len(jobs) == len(jobs_list) == 1190, "Sealed plan coverage")
    expected = {
        (jid, v)
        for jid, j in jobs.items()
        for v in (
            ["grid"]
            if j["spec"]["scope"] == "grid"
            else ["single", "ranked", "ranked_random"]
        )
    }
    records = {}
    traces = {}
    for name in current.namelist():
        if name.startswith(cp + "runs/") and name.endswith("/result.json"):
            r = json.loads(current.read(name))
            key = r["spec"]["job_id"], r["variant"]
            require(key not in records, "Duplicate result")
            records[key] = r
            traces[key] = events(
                current.read(name.replace("result.json", "callbacks.jsonl"))
            )
    require(set(records) == expected and len(records) == 1470, "Missing/extra result")
    check_data = json.loads(current.read(cp + "checks.json"))
    check_rows = csv_rows(current.read(cp + "checks.csv"))
    checks = {(r["job_id"], r["variant"]): r for r in check_rows}
    require(
        check_data == dict(passed=True, jobs=1470, failures=[]),
        "Original checks failed",
    )
    require(
        len(check_rows) == len(checks) == 1470 and set(checks) == expected,
        "Check coverage",
    )
    rows = csv_rows(current.read(cp + "runs.csv"))
    summary_keys = [
        (r["scope"], r["case"], int(r["budget"]), int(r["seed"]), r["variant"])
        for r in rows
    ]
    require(
        len(summary_keys) == len(set(summary_keys)) == 1470,
        "Summary coverage/duplicates",
    )
    tables = {}
    costs = {
        (r["grid_name"], tuple(json.loads(r["point"]))): float(r["point_wall_s"])
        for r in csv_rows(reference_bytes("reference/grid_point_timings.csv"))
    }
    pairs, incremental, summary_groups = [], [], defaultdict(list)
    total_callbacks, baseline_prefix_checks = 0, 0
    for key, record in sorted(records.items()):
        jid, variant = key
        spec = record["spec"]
        job = jobs[jid]
        trace = traces[key]
        points = [tuple(e["point"]) for e in trace]
        require(
            spec == job["spec"] and record["target"] == job["target"],
            "Job inputs changed: " + jid,
        )
        require(
            record["status"] in ("completed", "budget_completed")
            and record["error"] is None,
            "Execution failed",
        )
        require(
            record["process_nlp_calls"] == 0 and record["reevaluate_explored"] is False,
            "Wrong execution mode",
        )
        require(
            record["effective_cpus"] == [47] and record["improvement_abs_tol"] == 1e-5,
            "CPU or improvement tolerance changed",
        )
        require(
            len(trace)
            == len(set(points))
            == record["evaluations"]
            == record["distinct_evaluations"]
            <= spec["budget"],
            "Repeat/budget error: " + jid,
        )
        require(
            record["unused_budget"] == spec["budget"] - len(trace),
            "Unused budget mismatch",
        )
        require(
            [list(p) for p in points[: len(spec["starts"])]] == spec["starts"],
            "Initial point order changed",
        )
        require(
            [e["index"] for e in trace] == list(range(1, len(trace) + 1)),
            "Callback indices changed",
        )
        require(
            all(
                len(p) == len(spec["lower"])
                and all(
                    isinstance(v, int) and lo <= v <= hi
                    for v, lo, hi in zip(p, spec["lower"], spec["upper"])
                )
                for p in points
            ),
            "Invalid coordinates",
        )
        case, scope = spec["case"], spec["scope"]
        if (scope, case) not in tables:
            path = (
                f"inputs/grids/{case}.csv"
                if scope == "grid"
                else f"inputs/process/{case}_full.csv"
            )
            rows_for_case = csv_rows(process.read(pp + "reproduction/" + path))
            tables[scope, case] = {
                tuple(json.loads(r["Point" if scope == "grid" else "point"])): r
                for r in rows_for_case
            }
        table = tables[scope, case]
        point_costs = []
        for e, point in zip(trace, points):
            row = table[point]
            accepted = scope == "grid" or row["accepted"] == "True"
            value = (
                float(row["z_norm" if scope == "grid" else "objective"])
                if accepted
                else None
            )
            require(
                e["accepted"] == accepted and close(e["raw_objective"], value),
                "Stored-response mismatch: " + jid,
            )
            point_costs.append(
                costs[case, point] if scope == "grid" else float(row["total_wall_s"])
            )
        accepted = [e for e in trace if e["accepted"]]
        best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
        hit = bool(
            best
            and abs(best["raw_objective"] - job["target"])
            <= 1e-5 * max(1, abs(job["target"]))
        )
        first_hit = next(
            (
                e["index"]
                for e in accepted
                if abs(e["raw_objective"] - job["target"])
                <= 1e-5 * max(1, abs(job["target"]))
            ),
            None,
        )
        require(
            record["best_objective"] == (best["raw_objective"] if best else None)
            and record["best_point"] == (best["point"] if best else None),
            "Best result differs",
        )
        require(
            record["hit"] == hit and record["first_hit"] == first_hit,
            "Target scoring differs",
        )
        require(
            record["category"] == ("target_reached" if hit else "target_not_reached"),
            "Category differs",
        )
        lookup = math.fsum(e["lookup_wall_s"] for e in trace)
        require(
            close(record["lookup_s"], lookup)
            and close(record["point_cost_s"], math.fsum(point_costs)),
            "Lookup/cost accounting differs",
        )
        prep = 0 if scope == "grid" else float(job["baseline"]["prep_s"])
        require(
            close(record["prep_s"], prep)
            and close(record["retained_search_s"], record["search_s"] - lookup),
            "Search/preparation accounting",
        )
        require(
            close(
                record["completion_s"],
                record["search_s"] - lookup + math.fsum(point_costs) + prep,
            ),
            "Completion reconstruction differs",
        )
        check = checks[key]
        for label in ("passed", "ok", "no_repeats"):
            require(check[label] == "True", "Original check failed")
        if variant in ("grid", "single"):
            baseline_zip, prefix = (grid, gp) if scope == "grid" else (process, pp)
            baseline = json.loads(
                baseline_zip.read(prefix + "runs/" + jid + "/result.json")
            )
            old_events = events(
                baseline_zip.read(prefix + "runs/" + jid + "/callbacks.jsonl")
            )
            old_points = [tuple(e["point"]) for e in old_events]
            distinct = list(dict.fromkeys(old_points))
            require(
                points[: len(distinct)] == distinct,
                "Distinct historical prefix differs: " + jid,
            )
            require(
                baseline["best_objective"] is None
                or record["best_objective"] <= baseline["best_objective"],
                "Objective worsened",
            )
            require(not baseline["hit"] or hit, "Historical success lost")
            for label in (
                "legacy_reproduces_published",
                "published_distinct_prefix",
                "not_worse",
                "hit_kept",
            ):
                require(check[label] == "True", "Original replay check failed")
            require(
                int(check["published_evaluations"]) == len(old_points)
                and int(check["published_repeats"]) == len(old_points) - len(distinct),
                "Reported published counts differ",
            )
            require(
                (check["published_hit"] == "True") == baseline["hit"],
                "Reported old hit differs",
            )
            baseline_prefix_checks += 1
        else:
            single_points = [tuple(e["point"]) for e in traces[jid, "single"]]
            require(
                points[: len(single_points)] == single_points
                and check["first_descent_matches_single"] == "True",
                "Restart single prefix differs",
            )
        if scope == "process":
            baseline = json.loads(
                previous_restart.read(rp + f"runs/{jid}__{variant}/result.json")
            )
            old_events = events(
                previous_restart.read(rp + f"runs/{jid}__{variant}/callbacks.jsonl")
            )
            old_points = [tuple(e["point"]) for e in old_events]
            require(baseline["spec"] == spec, "Previous restart protocol differs")
        # Published Grid target-stop reference and previous Dantzig Process variant are separate comparators.
        old_cost = math.fsum(
            costs[case, tuple(e["point"])]
            if scope == "grid"
            else float(table[tuple(e["point"])]["total_wall_s"])
            for e in old_events
        )
        if scope == "grid":
            # Reconstruct from observed search time minus measured lookup time.
            old_completion = baseline.get("completion_s", baseline.get("total_s"))
            if old_completion is None:
                old_completion = (
                    baseline.get(
                        "retained_search_s", baseline["search_s"] - baseline["lookup_s"]
                    )
                    + old_cost
                )
        else:
            require(
                close(old_cost, baseline["point_cost_s"]), "Old restart cost differs"
            )
            old_completion = baseline["completion_s"]
        new_best, old_best = record["best_objective"], baseline["best_objective"]
        pair = dict(
            job_id=jid,
            variant=variant,
            scope=scope,
            case=case,
            budget=spec["budget"],
            seed=spec["seed"],
            previous_hit=baseline["hit"],
            new_hit=hit,
            previous_best=old_best,
            new_best=new_best,
            objective_improved=old_best is not None
            and new_best is not None
            and new_best < old_best - 1e-5,
            objective_worsened=old_best is not None
            and (new_best is None or new_best > old_best + 1e-5),
            previous_evaluations=len(old_events),
            previous_repeats=len(old_points) - len(set(old_points)),
            new_evaluations=len(trace),
            previous_point_cost_s=old_cost,
            new_point_cost_s=record["point_cost_s"],
            previous_completion_s=old_completion,
            new_completion_s=record["completion_s"],
            first_hit=first_hit,
            status=record["status"],
        )
        pairs.append(pair)
        group = (variant, "all" if scope == "grid" else case, spec["budget"])
        summary_groups[group].append(record)
        total_callbacks += len(trace)
        if variant in ("ranked", "ranked_random"):
            s = records[jid, "single"]
            incremental.append(
                dict(
                    job_id=jid,
                    variant=variant,
                    case=case,
                    budget=spec["budget"],
                    seed=spec["seed"],
                    single_hit=s["hit"],
                    restart_hit=hit,
                    gained_hit=hit and not s["hit"],
                    lost_hit=s["hit"] and not hit,
                    single_best=s["best_objective"],
                    restart_best=new_best,
                    improved_objective=new_best < s["best_objective"] - 1e-5,
                    extra_callbacks=len(trace) - s["evaluations"],
                    extra_point_cost_s=record["point_cost_s"] - s["point_cost_s"],
                )
            )
    # Verify all returned run-summary fields from their individual results.
    by_summary_key = {
        (
            r["spec"]["scope"],
            r["spec"]["case"],
            r["spec"]["budget"],
            r["spec"]["seed"],
            r["variant"],
        ): r
        for r in records.values()
    }
    for row, key in zip(rows, summary_keys):
        r = by_summary_key[key]
        for field in (
            "status",
            "hit",
            "best_objective",
            "evaluations",
            "distinct_evaluations",
            "unused_budget",
            "first_hit",
            "retained_search_s",
            "lookup_s",
            "point_cost_s",
            "prep_s",
            "completion_s",
        ):
            wanted = r[field]
            require(
                row[field] == ("" if wanted is None else str(wanted)),
                "Run summary field differs: " + field,
            )
        require(
            int(row["descents"]) == r["descent_count"], "Descent count summary differs"
        )
    summaries = csv_rows(current.read(cp + "condition_summary.csv"))
    require(len(summaries) == len(summary_groups) == 47, "Condition summary coverage")
    for row in summaries:
        group = summary_groups[row["variant"], row["case"], int(row["budget"])]
        expected_stats = dict(
            runs=len(group),
            hits=sum(r["hit"] for r in group),
            median_evaluations=quantile([r["evaluations"] for r in group], 0.5),
            runs_using_full_budget=sum(r["unused_budget"] == 0 for r in group),
            median_search_s=quantile([r["retained_search_s"] for r in group], 0.5),
            median_completion_s=quantile([r["completion_s"] for r in group], 0.5),
            q25_completion_s=quantile([r["completion_s"] for r in group], 0.25),
            q75_completion_s=quantile([r["completion_s"] for r in group], 0.75),
        )
        require(
            all(close(row[k], value) for k, value in expected_stats.items()),
            "Condition statistics differ",
        )
    cohorts = []
    for budget in (10, 30, 50, 70, 100):
        cohorts.append(
            summarize_pair(
                [r for r in pairs if r["scope"] == "grid" and r["budget"] == budget],
                f"Grid B={budget}",
            )
        )
    cohorts.append(
        summarize_pair([r for r in pairs if r["scope"] == "grid"], "Grid total")
    )
    for variant in ("single", "ranked", "ranked_random"):
        cohorts.append(
            summarize_pair(
                [r for r in pairs if r["variant"] == variant], "Process " + variant
            )
        )
    expected_hits = [13, 78, 91, 101, 101, 384, 79, 80, 80]
    require(
        [r["new_hits"] for r in cohorts] == expected_hits,
        "Professor cross-check differs",
    )
    conditions = []
    for key in sorted(
        {(r["scope"], r["variant"], r["case"], r["budget"]) for r in pairs}
    ):
        selected = [
            r
            for r in pairs
            if (r["scope"], r["variant"], r["case"], r["budget"]) == key
        ]
        conditions.append(
            dict(
                scope=key[0],
                variant=key[1],
                case=key[2],
                budget=key[3],
                **summarize_pair(selected, ":".join(map(str, key))),
            )
        )
    start, finish = (
        datetime.fromisoformat(manifest[k]) for k in ("started_utc", "finished_utc")
    )
    audit = dict(
        passed=True,
        revision=PIN,
        return_sha256=RETURN_SHA,
        original_inner_zip=Path(inner_name).name,
        original_inner_sha256=sha(inner_data),
        original_inner_bytes=len(inner_data),
        results=1470,
        missing=0,
        duplicates=0,
        statuses=dict(Counter(r["status"] for r in records.values())),
        callbacks=total_callbacks,
        stored_response_checks=total_callbacks,
        historical_prefix_checks=baseline_prefix_checks,
        restart_prefix_checks=280,
        server_reported_historical_replay_checks=1190,
        historical_replay_trace_retained=False,
        historical_algorithms_rerun_locally=False,
        reference_output_member_hashes=member_hashes,
        sealed_member_hashes=len(sealed),
        condition_summaries_recomputed=47,
        new_nlp_calls=0,
        exit_code=execution["exit_code"],
        python=manifest["python"],
        packages=manifest["versions"],
        cpu=execution["cpus"],
        host=manifest["host"],
        started_utc=manifest["started_utc"],
        finished_utc=manifest["finished_utc"],
        started_local=start.astimezone(
            ZoneInfo("America/Indiana/Indianapolis")
        ).isoformat(),
        finished_local=finish.astimezone(
            ZoneInfo("America/Indiana/Indianapolis")
        ).isoformat(),
        experiment_wall_s=(finish - start).total_seconds(),
        launcher_wall_s=(
            datetime.fromisoformat(execution["finished_utc"])
            - datetime.fromisoformat(execution["started_utc"])
        ).total_seconds(),
        cohorts=cohorts,
        restart_incremental={
            v: dict(
                gained_hits=sum(
                    r["gained_hit"] for r in incremental if r["variant"] == v
                ),
                lost_hits=sum(r["lost_hit"] for r in incremental if r["variant"] == v),
                improved_objectives=sum(
                    r["improved_objective"] for r in incremental if r["variant"] == v
                ),
                extra_callbacks=sum(
                    r["extra_callbacks"] for r in incremental if r["variant"] == v
                ),
            )
            for v in ("ranked", "ranked_random")
        },
    )
    write_json("analysis/validation.json", audit)
    write_csv("cohorts.csv", cohorts)
    write_csv("paired_runs.csv", pairs)
    write_csv("conditions.csv", conditions)
    write_csv(
        "new_target_hits.csv",
        [r for r in pairs if r["new_hit"] and not r["previous_hit"]],
    )
    write_csv("restart_incremental.csv", incremental)
    strict_regressions = sum(
        r["previous_best"] is not None
        and (r["new_best"] is None or r["new_best"] > r["previous_best"])
        for r in pairs
    )
    audit["strict_objective_regressions_vs_same_variant"] = strict_regressions
    write_json("analysis/validation.json", audit)
    report(audit, pairs, incremental)
    print(
        json.dumps(
            dict(
                passed=True,
                results=1470,
                callbacks=total_callbacks,
                cohorts=[
                    {
                        k: r[k]
                        for k in (
                            "cohort",
                            "previous_hits",
                            "new_hits",
                            "gained_hits",
                            "lost_hits",
                        )
                    }
                    for r in cohorts
                ],
                restart_incremental=audit["restart_incremental"],
            ),
            indent=2,
        )
    )


def report(audit, pairs, incremental):
    lines = [
        "# Dantzig D-SDA no-revisit result analysis",
        "",
        "All 1,470 returned results pass the independent data audit, with no missing jobs, duplicate jobs, repeated configurations within a run, budget violations, or target-scoring discrepancies.",
        "This report independently audits the Dantzig return using saved data only; no optimizer or NLP solver is rerun.",
        "",
        "## Target attainment and comparison",
        "",
        "The Grid comparator is the archived target-stop D-SDA run, and each Process comparator is the corresponding variant from the previous Dantzig restart return.",
        "All initial points, seeds, targets, budgets, and method settings match the sealed plan.",
        "",
        "| Cohort | Runs | Previous hits | New hits | Gained | Lost |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in audit["cohorts"]:
        lines.append(
            f"| {r['cohort']} | {r['runs']} | {r['previous_hits']} | {r['new_hits']} | {r['gained_hits']} | {r['lost_hits']} |"
        )
    lines += [
        "",
        "All supplied local cross-check counts match the Dantzig output.",
        "No previous target hit is lost, and no best objective becomes worse in any same-variant comparison.",
        "Objective-improvement counts in the CSV tables use a change greater than 1e-5; target attainment retains the original relative tolerance of 1e-5 times max(1, absolute target).",
        "Grid gains ten target hits across the budget-seed conditions, while Process single gains five.",
        "The five Process single gains are CSTR10/B15/seed8, CSTR30/B43/seed3, Dynamic/B15/seed9, and Dynamic/B20/seeds7 and 8.",
        "These are outcomes over the tested conditions, with reused functions and seeds across budgets; no new independence or statistical-significance claim is made.",
        "",
        "## Incremental effect of restarts",
        "",
        "Under the new no-revisit rule, ranked and ranked_random each add one target hit relative to the new single-descent result.",
        "The added hit is CSTR30/B43/seed4, whose best objective changes from 3.1301981330254702 to 2.7695697198995095.",
        "Both restart variants improve the best objective in 14 of the 140 Process jobs relative to new single descent.",
        "Ranked uses 1,055 additional callbacks and ranked_random uses 1,249 additional callbacks relative to new single descent.",
        "Random restarts therefore use 194 more callbacks than ranked restarts without additional target hits in this sample.",
        "The earlier statement that Process restarts add no target hits needs qualification: it describes the previous repeated-evaluation implementation, not this no-revisit result.",
        "",
        "## Evaluation cost and runtime",
        "",
        "| Cohort | Previous callbacks | Previous repeat callbacks | New callbacks | Previous point cost (s) | New point cost (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in audit["cohorts"]:
        if r["cohort"] == "Grid total" or r["cohort"].startswith("Process"):
            lines.append(
                f"| {r['cohort']} | {r['previous_callbacks']} | {r['previous_repeated_callbacks']} | {r['new_callbacks']} | {r['previous_point_cost_s']:.6f} | {r['new_point_cost_s']:.6f} |"
            )
    lines += [
        "",
        "Removing repeated evaluations can both free budget for new configurations and end searches earlier; the change in total callbacks is not necessarily equal to the number of historical repeats.",
        "Point costs are reconstructed from stored per-configuration timings, and completion time adds the measured search overhead and the original preparation cost.",
        "These are not newly measured online NLP runtimes.",
        f"The recorded experiment elapsed time is {audit['experiment_wall_s']:.6f} s, and the launcher including packaging took {audit['launcher_wall_s']:.6f} s.",
        "The short runtime is consistent with searching stored responses without new GDP/NLP solves.",
        "The 1,470 published result records are accompanied by 1,190 historical-mode validation searches inside the original runner, for 2,660 search invocations in total.",
        "Historical-mode searches are validation controls rather than extra primary benchmark results.",
        "",
        "## Provenance and verification",
        "",
        f"Execution revision: `{PIN}`.",
        f"Host: `{audit['host']}`; logical CPU 47; socket 0; physical core 61; SMT sibling 95.",
        "Numerical libraries used one thread, and every returned run reports effective affinity [47].",
        f"Started: `{audit['started_utc']}`; finished: `{audit['finished_utc']}` (UTC).",
        f"Local Indiana time: `{audit['started_local']}` to `{audit['finished_local']}`.",
        f"Python: `{audit['python']}`; packages: `{json.dumps(audit['packages'], sort_keys=True)}`.",
        "The original launcher exited zero; 1,158 records have completed status and 312 have budget_completed status.",
        "Budget completion is an execution termination status and does not itself indicate target attainment.",
        f"Outer return SHA256: `{RETURN_SHA}`.",
        f"Original inner ZIP: `{audit['original_inner_zip']}`; {audit['original_inner_bytes']} bytes; SHA256 `{audit['original_inner_sha256']}`.",
        f"ZIP CRCs, {audit['reference_output_member_hashes']:,} reference output member hashes, 263 sealed input hashes, and the execution source/input provenance checks pass.",
        "The audit reconstructs all 40,562 callback responses and point costs from the stored tables, all 1,470 run summaries, and all 47 condition summaries directly from the individual records.",
        "All 1,190 new primary paths preserve the distinct historical prefix, and all 280 restarted paths preserve their new single-descent prefix.",
        "The server records 1,190 successful historical-mode replay checks.",
        "The runner deletes temporary historical-mode traces, so those replay paths cannot be independently reconstructed from this return without executing the algorithm again.",
        "This analysis verifies the reported replay-check flags and independently verifies the retained historical prefix, objectives, and target outcomes; it does not rerun any optimizer or solver locally.",
        "",
        "## Files and reproduction",
        "",
        "The original RETURN_A.zip and its checksum are preserved byte-for-byte in evidence/.",
        "The audit reads historical reference archives and the Grid cost table from pinned Git objects already present in this repository.",
        "PROVENANCE.json identifies their source revisions, archive members, and hashes.",
        "The pinned source files are read as bytes for provenance checks and are never imported or executed.",
        "analysis/cohorts.csv contains the overall comparisons, analysis/conditions.csv contains every function/model-budget comparison, and analysis/paired_runs.csv retains the paired individual records.",
        "analysis/new_target_hits.csv identifies each new target hit, and analysis/restart_incremental.csv compares each restart with new single descent.",
        "analysis/validation.json records the audit results and evidence limitations.",
        "Reproduce the data-only audit and tables from this directory:",
        "",
        "```bash",
        "python3 analysis/analyze.py",
        "```",
    ]
    require(
        audit["strict_objective_regressions_vs_same_variant"] == 0,
        "Report regression statement is unsupported",
    )
    (ROOT / "analysis/REPORT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
