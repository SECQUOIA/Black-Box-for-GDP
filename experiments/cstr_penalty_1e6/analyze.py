"""Independently audit a returned CSTR penalty archive without executing its code."""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import statistics
import zipfile

REPO = Path(__file__).resolve().parents[2]
RETURN = "results/archives/cstr_penalty_1e6_20261022_045249_vn111_rf.zip"
BUNDLE = "results/runners/cstr_penalty_1e6_dantzig_20261022.zip"
BUDGETS = dict(zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43)))


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def save_csv(path, records):
    fields = list(dict.fromkeys(k for row in records for k in row))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(
            {
                k: json.dumps(v) if isinstance(v, (list, dict)) else v
                for k, v in row.items()
            }
            for row in records
        )


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        self.digest = sha(self.path.read_bytes())
        require(
            self.digest == Path(str(path) + ".sha256").read_text().split()[0],
            "ZIP checksum mismatch",
        )
        self.z = zipfile.ZipFile(path)
        names = self.z.namelist()
        require(len(names) == len(set(names)), "Duplicate archive members")
        require(
            all(
                not PurePosixPath(n).is_absolute()
                and ".." not in PurePosixPath(n).parts
                for n in names
            ),
            "Unsafe member path",
        )
        self.prefix = names[0].split("/")[0] + "/"
        require(all(n.startswith(self.prefix) for n in names), "Multiple archive roots")
        require(self.z.testzip() is None, "ZIP CRC failure")

    def data(self, name):
        return self.z.read(self.prefix + name)

    def read(self, name):
        return json.loads(self.data(name))

    def events(self, name):
        # Unlike the execution reader, reject a truncated final JSONL line.
        return [json.loads(line) for line in self.data(name).splitlines()]


def input_maps(archive, size):
    case = f"cstr_{size}"
    lookup_rows = load_csv(archive.data(f"reproduction/inputs/{case}/evaluations.csv"))
    cost_rows = load_csv(archive.data(f"reproduction/data/cost_table_{case}.csv"))

    def mapping(rows):
        data = {}
        for r in rows:
            require(
                r["case"] == "cstr" and int(r["cstr_size"]) == size,
                "Wrong point model/size",
            )
            point = tuple(json.loads(r["point"]))
            require(point not in data, "Duplicate coordinate")
            require(
                len(point) == 2
                and all(type(v) is int and 1 <= v <= size for v in point),
                "Invalid input coordinate",
            )
            data[point] = r
        return data

    lookup, costs = mapping(lookup_rows), mapping(cost_rows)
    expected = {
        (x, y)
        for x in range(1, size + 1)
        for y in range(1, size + 1)
        if size < 30 or y <= x
    }
    require(set(lookup) == expected, "Incomplete original lookup domain")
    accepted = [float(r["objective"]) for r in lookup_rows if r["accepted"] == "True"]
    require(
        all(math.isfinite(v) and v < 1e6 for v in accepted),
        "Penalty/objective collision",
    )
    for point, row in lookup.items():
        if point in costs:
            for field in ("accepted", "objective", "status", "total_wall_s"):
                require(
                    costs[point][field] == row[field], "Cost/lookup source disagreement"
                )
    return lookup, costs, min(accepted), max(accepted)


def audit_events(spec, events, lookup, finite):
    n, budget = spec["cstr_size"], spec["budget"]
    require(3 <= len(events) <= budget, "Charged budget or initial callbacks missing")
    require([e["point"] for e in events[:3]] == spec["starts"], "Initial order changed")
    previous = 0.0
    for i, e in enumerate(events, 1):
        require(
            e["index"] == i and e["cstr_size"] == n and not e["budget_overrun"],
            "Callback index/size/overrun",
        )
        point = tuple(e["point"])
        require(
            len(point) == 2 and all(type(v) is int and 1 <= v <= n for v in point),
            "Out-of-domain callback",
        )
        require(
            [round(x) for x in e["callback_coordinates"]] == list(point),
            "Requested/evaluated coordinates disagree",
        )
        require(
            e["phase"] == ("initial" if i <= 3 else "adaptive"), "Wrong callback phase"
        )
        row = lookup.get(point)
        accepted = row is not None and row["accepted"] == "True"
        require(e["accepted"] is accepted, "Acceptance changed")
        require(
            e["raw_objective"] == (float(row["objective"]) if accepted else None),
            "Raw objective changed",
        )
        candidate = (
            float(row["candidate_objective"])
            if row and row.get("candidate_objective")
            else None
        )
        require(e["raw_candidate_objective"] == candidate, "Raw candidate changed")
        if row:
            require(
                all(e["source_row"].get(k) == v for k, v in row.items()),
                "Original NLP row/status changed",
            )
        else:
            require(
                n == 30 and point[1] > point[0] and e["source_row"] is None,
                "Unexplained missing lookup",
            )
        state = (
            "accepted"
            if accepted
            else "evaluated_unaccepted"
            if row
            else "logical_exclusion_unmeasured"
        )
        require(e["evaluation_state"] == state, "Evaluation state changed")
        require(
            e["method_value"]
            == (e["raw_objective"] if accepted else 1e6 if finite else None),
            "Wrong optimizer response",
        )
        require(
            e["method_value_kind"] == ("finite" if accepted or finite else "+inf"),
            "Wrong response kind",
        )
        if finite:
            require(
                e["penalty_applied"] is (not accepted)
                and e["unaccepted_response"] == 1e6,
                "Penalty flag/setting mismatch",
            )
        require(
            e["value_returned_to_optimizer"] is (i != budget),
            "Terminal delivery differs from primary",
        )
        require(
            e["callback_exit"] == ("budget_stop" if i == budget else "return"),
            "Wrong callback exit",
        )
        require(
            math.isfinite(e["lookup_wall_s"]) and e["lookup_wall_s"] >= 0,
            "Invalid lookup time",
        )
        require(
            math.isfinite(e["elapsed_s"]) and e["elapsed_s"] >= previous,
            "Nonmonotonic callback time",
        )
        previous = e["elapsed_s"]


def measure(spec, events, result, costs, target):
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    hit_indices = [
        e["index"]
        for e in accepted
        if abs(e["raw_objective"] - target) <= 1e-5 * max(1, abs(target))
    ]
    failed = result["status"] not in ("completed", "budget_completed") or best is None
    category = (
        "execution_failed"
        if failed
        else "target_reached"
        if hit_indices
        else "target_not_reached"
    )
    wall = result.get("recorded_search_wall_s", result.get("dfo_wall_s"))
    require(math.isfinite(wall) and wall >= 0, "Invalid measured search time")
    lookup = sum(e["lookup_wall_s"] for e in events)
    require(wall >= lookup, "Lookup exceeds total search time")
    ledger, seen = [], set()
    for e in events:
        point = tuple(e["point"])
        row = costs.get(point)
        cost = float(row["total_wall_s"]) if row and row.get("total_wall_s") else None
        require(cost is None or math.isfinite(cost) and cost >= 0, "Invalid point cost")
        ledger.append(
            {
                **e,
                "repeated_point": point in seen,
                "historical_point_cost_s": cost,
                "cost_key": ["cstr", spec["cstr_size"], list(point)],
                "cost_source": row.get("cost_source", "original") if row else "missing",
            }
        )
        seen.add(point)
    missing = [e["cost_key"] for e in ledger if e["historical_point_cost_s"] is None]
    total = None if missing else sum(e["historical_point_cost_s"] for e in ledger)
    return {
        "category": category,
        "status": result["status"],
        "target_hit": category == "target_reached",
        "target_observed_even_if_failed": bool(hit_indices),
        "first_target_evaluation": hit_indices[0] if hit_indices else None,
        "best_accepted_objective": best["raw_objective"] if best else None,
        "best_point": best["point"] if best else None,
        "target": target,
        "charged_evaluations": len(events),
        "accepted_evaluations": len(accepted),
        "unaccepted_evaluations": len(events) - len(accepted),
        "repeated_evaluations": len(events) - len(seen),
        "measured_search_s": wall,
        "lookup_s": lookup,
        "retained_search_s": wall - lookup,
        "point_cost_sum_s": total,
        "missing_cost_keys": missing,
        "estimated_completion_s": wall - lookup + total if total is not None else None,
    }, ledger


def compare_export(actual, expected):
    for key, value in expected.items():
        require(key in actual, f"Export missing {key}")
        raw = actual[key]
        if value is None:
            require(raw == "", f"Export null differs: {key}")
        elif isinstance(value, bool):
            require(raw == str(value), f"Export bool differs: {key}")
        elif isinstance(value, (float, int)):
            require(
                math.isclose(float(raw), value, rel_tol=1e-12, abs_tol=1e-12),
                f"Export number differs: {key}",
            )
        elif isinstance(value, (list, dict)):
            require(json.loads(raw) == value, f"Export collection differs: {key}")
        else:
            require(raw == value, f"Export value differs: {key}")


def analyze(path, bundle_path, output):
    require(
        not output.exists(), "Output directory already exists; preserve prior analysis"
    )
    a, bundle = Archive(path), Archive(bundle_path)
    manifest = bundle.data("SHA256SUMS")
    require(
        manifest == a.data("reproduction/SHA256SUMS"),
        "Returned bundle differs from submitted bundle",
    )
    for line in manifest.decode().splitlines():
        digest, name = line.split("  ", 1)
        require(sha(bundle.data(name)) == digest, f"Submitted file mismatch: {name}")
        require(
            a.data("reproduction/" + name) == bundle.data(name),
            f"Returned source/input changed: {name}",
        )
    require(
        a.read("run.json")["inventory_sha256"] == sha(manifest),
        "Run inventory mismatch",
    )
    plan = a.read("reproduction/plan.json")
    expected = {
        (n, b, s, m)
        for n, b in BUDGETS.items()
        for s in range(10)
        for m in ("dsda", "rbfopt")
    }
    require(
        len(plan) == 120
        and {
            (
                j["spec"]["cstr_size"],
                j["spec"]["budget"],
                j["spec"]["seed"],
                j["spec"]["method"],
            )
            for j in plan
        }
        == expected,
        "Wrong plan",
    )
    maps = {n: input_maps(a, n) for n in BUDGETS}
    exported = {r["job_id"]: r for r in load_csv(a.data("paired_comparison.csv"))}
    require(len(exported) == 120, "Missing returned pairs")
    originals, paired, coordinates, trajectory_pairs = {}, [], [], []
    runtime_rows, trajectories = [], {}
    for job in plan:
        spec, jobid = job["spec"], job["spec"]["job_id"]
        require(spec["unaccepted_response"] == 1e6, "Wrong penalty")
        new_path, base_path = (
            "jobs/" + jobid + "/",
            "reproduction/baseline/" + jobid + "/",
        )
        require(
            a.read(new_path + "job.json") == job,
            "Executed spec differs from frozen plan",
        )
        current, old = (
            a.events(new_path + "callbacks.jsonl"),
            a.events(base_path + "callbacks.jsonl"),
        )
        archive_name = job["baseline_archive"]["path"]
        if archive_name not in originals:
            originals[archive_name] = Archive(REPO / archive_name)
            require(
                originals[archive_name].digest == job["baseline_archive"]["sha256"],
                "Baseline archive mismatch",
            )
        original = originals[archive_name]
        for name in (
            "callbacks.jsonl",
            "result.json",
            "runtime.json",
            "actual_settings.json",
        ):
            require(
                a.data(base_path + name)
                == original.z.read(job["baseline_member"] + name),
                "Baseline bytes changed",
            )
        lookup, costs, target, _ = maps[spec["cstr_size"]]
        audit_events(spec, old, lookup, False)
        audit_events(spec, current, lookup, True)
        new_result, old_result = (
            a.read(new_path + "result.json"),
            a.read(base_path + "result.json"),
        )
        require(new_result.get("returncode") == 0, "Worker failed")
        require(
            new_result["status"]
            == ("budget_completed" if len(current) == spec["budget"] else "completed"),
            "Unexpected stopping status",
        )
        process = a.read(new_path + "process.json")
        require(
            process["hard_seconds"] == job["hard_seconds"] == 2100
            and "_worker" in process["command"],
            "Worker command/watchdog mismatch",
        )
        before, old_ledger = measure(spec, old, old_result, costs, target)
        after, new_ledger = measure(spec, current, new_result, costs, target)
        compare_export(
            exported[jobid],
            {
                k: v
                for k, v in after.items()
                if k not in ("repeated_evaluations", "target_observed_even_if_failed")
            },
        )
        compare_export(
            exported[jobid],
            {
                "baseline_" + k: v
                for k, v in before.items()
                if k not in ("repeated_evaluations", "target_observed_even_if_failed")
            },
        )
        settings = a.read(new_path + "actual_settings.json")
        require(
            settings
            == job["reference_settings"]
            == a.read(base_path + "actual_settings.json"),
            "Actual optimizer settings changed",
        )
        if spec["method"] == "rbfopt":
            require(
                (
                    settings["algorithm"],
                    settings["rbf"],
                    settings["global_search_method"],
                )
                == ("MSRSM", "auto", "genetic"),
                "Wrong primary variant",
            )
            require(
                a.read(new_path + "settings_comparison.json")["identical_to_primary"],
                "Settings audit failed",
            )
        rt, old_rt = (
            a.read(new_path + "runtime.json"),
            a.read(base_path + "runtime.json"),
        )
        for field in ("versions", "python", "host", "platform", "executable"):
            require(rt[field] == old_rt[field], "Runtime differs: " + field)
        require(
            len(rt["effective_cpus"]) == 1
            and all(
                v == "1"
                for k, v in rt["threads"].items()
                if k not in ("OMP_DYNAMIC", "MKL_DYNAMIC")
            ),
            "Thread/affinity mismatch",
        )
        require(
            rt["threads"]["OMP_DYNAMIC"] == rt["threads"]["MKL_DYNAMIC"] == "FALSE",
            "Dynamic threading enabled",
        )
        if spec["method"] == "rbfopt":
            require(
                all(
                    rt[k + "_sha256"] == old_rt["binary_sha256"][k]
                    for k in ("bonmin", "ipopt")
                ),
                "Auxiliary binary changed",
            )
        runtime_rows.append(
            {
                "job_id": jobid,
                "host": rt["host"],
                "python": rt["python"],
                "versions": rt["versions"],
                "cpu": rt["effective_cpus"],
                "baseline_cpu": old_rt.get("affinity", {}).get("effective_cpus"),
                "command": process["command"],
            }
        )
        points_old, points_new = (
            [e["point"] for e in old],
            [e["point"] for e in current],
        )
        common = 0
        for left, right in zip(points_old, points_new):
            if left != right:
                break
            common += 1
        same = points_old == points_new
        delta = after["best_accepted_objective"] - before["best_accepted_objective"]
        row = {
            k: spec[k]
            for k in ("job_id", "case", "cstr_size", "method", "seed", "budget")
        }
        row.update({"baseline_" + k: v for k, v in before.items()})
        row.update(after)
        row.update(
            path_identical=same,
            common_prefix_evaluations=common,
            first_path_divergence=None if same else common + 1,
            baseline_first_different_point=None
            if same or common == len(old)
            else old[common]["point"],
            first_different_point=None
            if same or common == len(current)
            else current[common]["point"],
            initial_unaccepted_evaluations=sum(not e["accepted"] for e in current[:3]),
            objective_change=delta,
            objective_comparison="worse"
            if delta > 1e-12
            else "better"
            if delta < -1e-12
            else "equal",
            target_hit_change=int(after["target_hit"]) - int(before["target_hit"]),
        )
        paired.append(row)
        trajectories[jobid] = (points_old, points_new)
        for policy, ledger in [("+inf", old_ledger), ("1e6", new_ledger)]:
            for e in ledger:
                trajectory_pairs.append(
                    {
                        "job_id": jobid,
                        "case": spec["case"],
                        "method": spec["method"],
                        "seed": spec["seed"],
                        "policy": policy,
                        **{
                            k: e.get(k)
                            for k in (
                                "index",
                                "phase",
                                "point",
                                "callback_coordinates",
                                "accepted",
                                "raw_objective",
                                "raw_candidate_objective",
                                "evaluation_state",
                                "method_value",
                                "method_value_kind",
                                "penalty_applied",
                                "value_returned_to_optimizer",
                                "repeated_point",
                                "cost_key",
                                "cost_source",
                                "historical_point_cost_s",
                            )
                        },
                    }
                )
                if policy == "1e6" and spec["method"] == "rbfopt":
                    coordinates.append(trajectory_pairs[-1])
    returned_coordinates = load_csv(a.data("rbfopt_coordinates.csv"))
    require(
        len(returned_coordinates) == len(coordinates),
        "Coordinate export count mismatch",
    )
    for actual, expected_row in zip(returned_coordinates, coordinates):
        compare_export(actual, {k: v for k, v in expected_row.items() if k in actual})
    groups = []
    for n in BUDGETS:
        for method in ("dsda", "rbfopt"):
            rs = [r for r in paired if r["cstr_size"] == n and r["method"] == method]
            groups.append(
                group_summary(
                    rs, {"case": f"cstr_{n}", "method": method, "budget": BUDGETS[n]}
                )
            )
    methods = [
        group_summary([r for r in paired if r["method"] == m], {"method": m})
        for m in ("dsda", "rbfopt")
    ]
    returned_summary = a.read("summary.json")
    require(
        returned_summary["planned"] == 120
        and returned_summary["counts"] == dict(Counter(r["category"] for r in paired)),
        "Returned summary counts differ",
    )
    for g in groups:
        old_group = next(
            r
            for r in returned_summary["groups"]
            if (r["case"], r["method"]) == (g["case"], g["method"])
        )
        require(
            (
                old_group["target_hits"],
                old_group["baseline_target_hits"],
                old_group["execution_failed"],
                old_group["not_run"],
            )
            == (g["penalty_hits"], g["baseline_hits"], g["execution_failed"], 0),
            "Returned group summary differs",
        )
    output.mkdir(parents=True)
    save_csv(output / "paired_runs.csv", paired)
    save_csv(output / "condition_summary.csv", groups)
    save_csv(output / "method_summary.csv", methods)
    save_csv(output / "callback_paths.csv", trajectory_pairs)
    save_csv(output / "rbfopt_coordinates.csv", coordinates)
    save_csv(output / "runtime_audit.csv", runtime_rows)
    save_json(
        output / "audit.json",
        {
            "archive": RETURN,
            "archive_sha256": a.digest,
            "submitted_bundle": BUNDLE,
            "submitted_bundle_sha256": bundle.digest,
            "planned": 120,
            "completed": len(paired),
            "execution_failed": sum(
                r["category"] == "execution_failed" for r in paired
            ),
            "not_run": 0,
            "new_callbacks": sum(r["charged_evaluations"] for r in paired),
            "rbfopt_coordinates": len(coordinates),
            "penalized_callbacks": sum(
                not e["accepted"] for e in trajectory_pairs if e["policy"] == "1e6"
            ),
            "missing_cost_callbacks": sum(len(r["missing_cost_keys"]) for r in paired),
            "source_input_inventory_verified": True,
            "baseline_original_bytes_verified": True,
            "all_initial_orders_preserved": True,
            "all_actual_settings_preserved": True,
            "raw_objective_acceptance_status_verified": True,
            "returned_summaries_and_coordinates_verified": True,
            "same_host_python_packages_platform_executable": True,
            "baseline_rbfopt_cpu": sorted(
                {
                    cpu
                    for r in runtime_rows
                    if r["baseline_cpu"]
                    for cpu in r["baseline_cpu"]
                }
            ),
            "new_cpu": sorted({cpu for r in runtime_rows for cpu in r["cpu"]}),
            "server_protocol_tests_passed": "Ran 13 tests"
            in a.data("checks/tests/optimizer.log").decode()
            and a.data("checks/tests/optimizer.log").decode().rstrip().endswith("OK"),
            "accepted_objective_maxima": {str(n): maps[n][3] for n in BUDGETS},
            "analysis_only_no_optimization": True,
            "methods": methods,
        },
    )
    write_report(output, groups, methods, paired)
    for obj in [a, bundle, *originals.values()]:
        obj.z.close()
    return groups, methods, trajectories


def group_summary(rs, identity):
    data = {
        **identity,
        "runs": len(rs),
        "baseline_hits": sum(r["baseline_target_hit"] for r in rs),
        "penalty_hits": sum(r["target_hit"] for r in rs),
        "lost_hits": sum(r["target_hit_change"] == -1 for r in rs),
        "gained_hits": sum(r["target_hit_change"] == 1 for r in rs),
        "identical_paths": sum(r["path_identical"] for r in rs),
        **{
            "objective_" + k: sum(r["objective_comparison"] == k for r in rs)
            for k in ("better", "equal", "worse")
        },
        "execution_failed": sum(r["category"] == "execution_failed" for r in rs),
        "baseline_evaluations": sum(r["baseline_charged_evaluations"] for r in rs),
        "penalty_evaluations": sum(r["charged_evaluations"] for r in rs),
    }
    for prefix in ("baseline_", ""):
        for metric in (
            "accepted_evaluations",
            "unaccepted_evaluations",
            "repeated_evaluations",
        ):
            data[prefix + "total_" + metric] = sum(r[prefix + metric] for r in rs)
    data["early_stopped_runs"] = sum(r["charged_evaluations"] < r["budget"] for r in rs)
    for metric in (
        "measured_search_s",
        "point_cost_sum_s",
        "estimated_completion_s",
        "accepted_evaluations",
        "unaccepted_evaluations",
    ):
        for prefix in ("baseline_", ""):
            values = [r[prefix + metric] for r in rs]
            data[prefix + "median_" + metric] = (
                statistics.median(values)
                if all(v is not None for v in values)
                else None
            )
    return data


def write_report(output, groups, methods, paired):
    dsda, rbf = methods
    lines = [
        "CSTR penalty 1e6: returned Dantzig data analysis",
        "",
        f"{len(paired)}/120 runs completed; {sum(g['execution_failed'] for g in methods)} execution failures; {sum(len(r['missing_cost_keys']) for r in paired)} missing point costs.",
        f"D-SDA: {dsda['baseline_hits']}/60 -> {dsda['penalty_hits']}/60 target hits; {dsda['identical_paths']}/60 coordinate paths and {dsda['objective_equal']}/60 best objectives identical.",
        f"RBFOpt primary (MSRSM/auto/genetic): {rbf['baseline_hits']}/60 -> {rbf['penalty_hits']}/60 hits; {rbf['lost_hits']} lost hits, {rbf['gained_hits']} gained.",
        f"{60 - rbf['identical_paths']}/60 RBFOpt coordinate paths changed. Best accepted objective worsened in {rbf['objective_worse']} runs,",
        f"was unchanged in {rbf['objective_equal']}, and improved in {rbf['objective_better']}.",
        "",
        "Hits per 10 seeds (+inf -> 1e6):",
        "Size   Budget   D-SDA      RBFOpt",
    ]
    for n in BUDGETS:
        d, r = [g for g in groups if g["case"] == f"cstr_{n}"]
        lines.append(
            f"{n:<6} {BUDGETS[n]:<8} {d['baseline_hits']}->{d['penalty_hits']:<7} {r['baseline_hits']}->{r['penalty_hits']}"
        )
    lines += [
        "",
        "Interpretation",
        "Within these fixed budgets/seeds, using 1e6 did not improve either method.",
        "D-SDA begins from the best accepted initial point and accepts only improving moves;",
        "every accepted lookup objective is below 10, so replacing +inf by 1e6 still rejects",
        "the same unaccepted moves. Identical observed paths support this explanation.",
        "RBFOpt models the responses; finite failures can affect its model/scaling and subsequent",
        "candidate choices. Its auto scaling and median dynamism clipping were NOT changed.",
        "The coordinate logs establish path changes; they do not isolate which internal scaling",
        "or interpolation decision caused each divergence. No claim of universal optimal penalty.",
        "",
        "Accounting and timing",
        f"{sum(g['penalty_evaluations'] for g in methods)} actual callbacks: {dsda['penalty_evaluations']} D-SDA and {rbf['penalty_evaluations']} RBFOpt.",
        f"D-SDA stopped naturally before B in {dsda['early_stopped_runs']}/60 runs; RBFOpt in {rbf['early_stopped_runs']}/60.",
        f"RBFOpt rejected callbacks: {rbf['baseline_total_unaccepted_evaluations']} -> {rbf['total_unaccepted_evaluations']}; fewer rejections did not yield more target hits.",
        "Three archived initial points, their order, full integer domain, budgets, settings,",
        "repeated visits and terminal BudgetStop policy are preserved. Callback B is included",
        "in best accepted/target summaries even though it is not returned to the optimizer.",
        "A finite rejection never becomes accepted. Raw candidate objective/status remain intact.",
        "Estimated completion = measured search - measured lookup + historical per-callback NLP cost.",
        "Point keys include CSTR size and coordinates; repeated and rejected visits are charged.",
        "CSTR30 uses the existing same-size structural rejection cost supplement. No NLP reruns.",
        f"RBFOpt median measured search: {rbf['baseline_median_measured_search_s']:.6f} -> {rbf['median_measured_search_s']:.6f} s.",
        f"RBFOpt median estimated completion: {rbf['baseline_median_estimated_completion_s']:.6f} -> {rbf['median_estimated_completion_s']:.6f} s.",
        "These are descriptive medians across six sizes (10 seeds each), not paired speedup estimates.",
        "Host, Python, package versions, platform and auxiliary solver binaries match the baselines.",
        "CPU affinity is retained in runtime_audit.csv as execution metadata, not treated as",
        "an explanation for the changed target hits or evaluation coordinates.",
        "Installed RBFOpt module hashes are recorded for the new runs; the historical runtime",
        "did not record these hashes, so installed source byte identity cannot be established.",
        "No additional +inf control experiment was performed or included.",
        "",
        "Reproduce from the repository root (standard library only; no archive code execution):",
        "python experiments/cstr_penalty_1e6/analyze.py --output /tmp/cstr_penalty_analysis_replay",
        "Optional static figures: add --plots using the existing matplotlib environment.",
        "",
        "Files: audit.json; paired_runs.csv; condition_summary.csv; method_summary.csv;",
        "callback_paths.csv (both policies); rbfopt_coordinates.csv (new RBFOpt); runtime_audit.csv.",
        "Raw return ZIP and submitted runner ZIP are retained under results/archives and results/runners.",
        "Original commands, paths, source/lookup hashes and raw JSONL callbacks remain in the ZIP.",
        "Historical validation logs in the submitted bundle describe preparation, not returned run status.",
        "No paper/Overleaf/source figure/table was replaced; this is a separate experiment report.",
        "",
        "RBFOpt lost-hit seeds:",
    ]
    lines += [
        f"  {r['case']}, seed {r['seed']}: first path divergence at callback {r['first_path_divergence']}; objective {r['baseline_best_accepted_objective']:.12g} -> {r['best_accepted_objective']:.12g}"
        for r in paired
        if r["target_hit_change"] == -1
    ]
    (output / "README.txt").write_text("\n".join(lines) + "\n")


def plot(output, groups, trajectories):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, method in zip(axes, ("dsda", "rbfopt")):
        rs = [g for g in groups if g["method"] == method]
        x = list(range(6))
        ax.bar(
            [v - 0.18 for v in x],
            [r["baseline_hits"] for r in rs],
            width=0.36,
            label="+infinity",
            color="#2465a8",
        )
        ax.bar(
            [v + 0.18 for v in x],
            [r["penalty_hits"] for r in rs],
            width=0.36,
            label="1e6",
            color="#df791c",
        )
        ax.set(
            xticks=x,
            xticklabels=list(BUDGETS),
            ylim=(0, 11),
            xlabel="CSTR size",
            title="D-SDA" if method == "dsda" else "RBFOpt (MSRSM / genetic)",
        )
        ax.set_yticks(range(0, 11, 2))
        ax.legend(frameon=False)
    axes[0].set_ylabel("Target hits / 10 seeds")
    fig.tight_layout()
    fig.savefig(output / "target_hits.png", dpi=180)
    plt.close(fig)
    pairs = load_csv((output / "paired_runs.csv").read_bytes())
    fig, axes = plt.subplots(2, 3, figsize=(12, 8))
    for ax, n in zip(axes.flat, BUDGETS):
        r = next(
            r
            for r in pairs
            if r["case"] == f"cstr_{n}" and r["target_hit_change"] == "-1"
        )
        old, new = trajectories[r["job_id"]]
        for points, color, label, style in [
            (old, "#2465a8", "+infinity", "--"),
            (new, "#df791c", "1e6", "-"),
        ]:
            ax.plot(
                [p[0] for p in points],
                [p[1] for p in points],
                linestyle=style,
                marker="o",
                markersize=3,
                color=color,
                alpha=0.75,
                label=label,
            )
        ax.scatter(
            [p[0] for p in old[:3]],
            [p[1] for p in old[:3]],
            s=65,
            marker="s",
            facecolors="none",
            edgecolors="black",
            label="Shared starts",
        )
        ax.scatter([n], [n], marker="*", color="black", s=100, label="Target")
        ax.set(
            title=f"CSTR{n}, seed {r['seed']}, first divergence #{r['first_path_divergence']}",
            xlim=(0.5, n + 0.5),
            ylim=(0.5, n + 0.5),
            xlabel="x1",
            ylabel="x2",
        )
        ax.set_aspect("equal")
        ax.grid(alpha=0.15)
    axes.flat[0].legend(fontsize=7)
    fig.suptitle(
        "RBFOpt lost-hit examples: lowest lost-hit seed per size; lines follow callback order"
    )
    fig.tight_layout()
    fig.savefig(output / "rbfopt_path_examples.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, default=REPO / RETURN)
    p.add_argument("--bundle", type=Path, default=REPO / BUNDLE)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--plots", action="store_true")
    args = p.parse_args()
    groups, methods, trajectories = analyze(args.archive, args.bundle, args.output)
    if args.plots:
        plot(args.output, groups, trajectories)
    save_json(
        args.output / "manifest.json",
        {
            "analysis_source_sha256": sha(Path(__file__).read_bytes()),
            "outputs_sha256": {
                f.name: sha(f.read_bytes())
                for f in sorted(args.output.iterdir())
                if f.is_file()
            },
        },
    )
    print(json.dumps(methods, indent=2))
