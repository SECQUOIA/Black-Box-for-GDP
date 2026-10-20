"""Recompute all 8 main and 15 supplementary table data from frozen records."""

from collections import Counter, defaultdict
import math
import statistics

from common import DATA, GRID, PROCESS, ROOT, METHODS, read_json, rows, write_table


def interval(hits, n=10):
    from scipy.stats import beta

    return (
        0.0 if hits == 0 else float(beta.ppf(0.025, hits, n - hits + 1)),
        1.0 if hits == n else float(beta.ppf(0.975, hits + 1, n - hits)),
    )


def restart_cost(hits, values):
    repetitions = (
        math.ceil(math.log(0.01) / math.log1p(-hits / len(values)))
        if 0 < hits < len(values)
        else 1
        if hits
        else math.inf
    )
    return statistics.median(values) * repetitions


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    grid, process = rows(GRID / "runs.csv"), rows(PROCESS / "run_results.csv")
    gg, pg = defaultdict(list), defaultdict(list)
    for r in grid:
        gg[r["grid_name"], int(r["max_evals"]), r["method"]].append(r)
    for r in process:
        pg[r["case"], int(r["budget"]), r["method"]].append(r)
    support = DATA / "supporting_data"
    inventory = read_json(support / "grid_inventory.json")
    counts = read_json(support / "process_model_counts.json")
    coverage = rows(PROCESS / "timing_coverage.csv")
    tables = {}
    tables["main_01"] = []
    for r in coverage:
        case = r["case"]
        selected = [v for v in process if v["case"] == case]
        costs = rows(PROCESS / f"cost_table_{case}.csv")
        accepted = [c for c in costs if c["accepted"] == "True"]
        tables["main_01"].append(
            dict(
                case=case,
                finite_lookup=len(accepted),
                measured_coordinates=len(costs),
                budgets=sorted({int(v["budget"]) for v in selected}),
                reference=min(float(c["objective"]) for c in accepted),
                full_gdp_box_size=225 if case == "column" else len(costs),
                dfo_box_size=len(costs),
            )
        )
    tables["main_02"] = []
    for method in METHODS:
        protocol = read_json(support / f"protocol_{method}.json")
        # Every actual dictionary is exported, rather than silently selecting one budget.
        for job in protocol["jobs"]:
            tables["main_02"].append(
                dict(
                    scope="process",
                    method=method,
                    job_id=job["job_id"],
                    settings=job["actual_settings"],
                    spec=job["spec"],
                    source=job["source"],
                )
            )
    for record in read_json(support / "grid_execution_records.json"):
        tables["main_02"].append(
            dict(
                scope="grid",
                method=record["method"],
                source=record["archive"],
                archive_sha256=record["sha256"],
                protocol=record["protocol"],
                runtime=record["runtime"],
                settings=record["config"],
            )
        )
    tables["main_03"] = []
    tables["main_04"] = []
    for budget in (10, 30, 50, 70, 100):
        for method in METHODS:
            rr = [
                r
                for r in grid
                if int(r["max_evals"]) == budget and r["method"] == method
            ]
            hits = sum(r["target_hit"] == "True" for r in rr)
            tables["main_03"].append(
                dict(
                    budget=budget,
                    method=method,
                    hits=hits,
                    n=len(rr),
                    percent=100 * hits / len(rr),
                    display_percent=f"{100 * hits / len(rr):.1f}",
                )
            )
            if budget == 100:
                tables["main_04"].append(
                    dict(
                        method=method,
                        hits=hits,
                        n=len(rr),
                        median_completion_s=statistics.median(
                            float(r["estimated_total_s"]) for r in rr
                        ),
                        median_point_s=statistics.median(
                            float(r["sum_point_wall_s"]) for r in rr
                        ),
                        median_search_s=statistics.median(
                            float(r["retained_search_wall_s"]) for r in rr
                        ),
                    )
                )
    tables["main_05"] = []
    for r in rows(GRID / "gdp_runs.csv"):
        flag = (
            "U"
            if r["status"] == "unsupported_expression"
            else "M"
            if r["target_hit"] != "True"
            else f"{float(r['measured_worker_wall_s']):.2f}"
        )
        tables["main_05"].append(
            dict(
                r,
                display=flag,
                time_limit=r["termination"] == "maxTimeLimit"
                or r["status"] == "hard_time_limit",
                corrected_profile=r["profile"] == "pyomo610-grid-v1",
            )
        )
    tables["main_06"], tables["main_07"] = [], []
    intervals = []
    for scope, groups in [("grid", gg), ("process", pg)]:
        for (case, budget, method), rr in sorted(groups.items()):
            hits = sum(
                r["target_hit"] == "True"
                if scope == "grid"
                else r["category"] == "target_reached"
                for r in rr
            )
            lo, hi = interval(hits, len(rr))
            intervals.append(
                dict(
                    scope=scope,
                    case=case,
                    budget=budget,
                    method=method,
                    n=len(rr),
                    hits=hits,
                    p_hat=hits / len(rr),
                    ci95_lower=lo,
                    ci95_upper=hi,
                )
            )
            if scope == "process":
                failures = sum(r["category"] == "execution_failed" for r in rr)
                tables["main_06"].append(
                    dict(
                        case=case,
                        budget=budget,
                        method=method,
                        hits=hits,
                        n=len(rr),
                        execution_failures=failures,
                    )
                )
                values = [float(r["reconstructed_total_s"]) for r in rr]
                tables["main_07"].append(
                    dict(
                        case=case,
                        budget=budget,
                        method=method,
                        median_completion_s=statistics.median(values),
                        tts99_s=restart_cost(hits, values),
                    )
                )
    audit = rows(DATA / "algebraic_audit/table8_bound_audit.csv")
    comparison = rows(ROOT / "results/gdp_comparison_current/analysis/comparison.csv")
    by_key = {(r["instance_id"], r["method"]): r for r in comparison}
    tables["main_08"] = []
    for r in audit:
        c = by_key[r["instance_id"], r["method"]]
        tables["main_08"].append(
            dict(
                instance_id=r["instance_id"],
                method=r["method"],
                objective=r["reported_objective"],
                completion_s=c["measured_total_with_preparation_s"],
                termination=r["raw_termination"],
                target_attained=r["target_attained"],
                bound_conflict=r["uniform_bound_conflict"],
                optimal_target_miss=r["raw_termination"] == "optimal"
                and r["target_attained"] != "True",
            )
        )
    tables["supp_01"] = [
        dict(
            function=r["name"],
            bounds=r["bounds"],
            configurations=r["n_grid"],
            boolean_indicators=62,
        )
        for r in inventory
    ]
    proposals = rows(support / "fmqa_proposal_counts.csv")
    families = defaultdict(list)
    for r in proposals:
        family = (
            "Grid"
            if r["scope"] == "grid"
            else "CSTR"
            if r["job_id"].startswith("cstr")
            else "Column"
            if r["job_id"].startswith("column")
            else "Dynamic"
            if r["job_id"].startswith("dynamic")
            else "Small Batch"
        )
        families[family].append(r)
        if family != "Grid":
            families["Process total"].append(r)
    tables["supp_02"] = [
        dict(
            family=f,
            runs=len(rr),
            proposals=sum(int(r["proposals"]) for r in rr),
            uniform_fallbacks=sum(int(r["uniform_fallbacks"]) for r in rr),
            fallback_percent=100
            * sum(int(r["uniform_fallbacks"]) for r in rr)
            / sum(int(r["proposals"]) for r in rr),
        )
        for f, rr in families.items()
    ]
    tables["supp_03"] = read_json(support / "terminal_callback_recovery.json")["runs"]
    stopping = read_json(support / "stopping_diagnostics.json")
    pooled = defaultdict(list)
    for r in stopping["runs"]:
        pooled[r["family"] + "/" + r["method"]].append(r)
    tables["supp_04"] = []
    for key, rr in pooled.items():
        post = [r["callbacks_after_first_target"] for r in rr if r["target_hit"]]
        tables["supp_04"].append(
            dict(
                key=key,
                runs=len(rr),
                stop_counts=dict(Counter(r["stop_reason"] for r in rr)),
                callbacks_total=sum(r["callbacks"] for r in rr),
                target_hits=sum(r["target_hit"] for r in rr),
                post_target_median_successful=statistics.median(post),
            )
        )
    tables["supp_05"] = counts
    tables["supp_06"] = [
        {k: r[k] for k in ["name", "L", "U", "n_min", "n_target"]} for r in inventory
    ]
    tables["supp_07"] = [
        dict(name=r["name"], minimizing_indices=r["floating_minimizers"])
        for r in inventory
    ]
    tables["supp_08"] = [r for r in intervals if r["scope"] == "process"]
    for i, budget in enumerate((10, 30, 50, 70, 100), 9):
        tables[f"supp_{i:02}"] = [
            r for r in intervals if r["scope"] == "grid" and r["budget"] == budget
        ]
    tables["supp_14"] = []
    for r in audit:
        result = dict(r)
        lower, witness = (
            r["reported_lower_bound"],
            float(r["witness_recorded_objective"]),
        )
        tolerance = 1e-5 * max(1, abs(witness))
        result.update(
            tolerance=tolerance,
            bound_minus_witness=float(lower) - witness if lower else "",
            bound_gap_over_tolerance=(float(lower) - witness) / tolerance
            if lower
            else "",
            uniform_bound_conflict=bool(lower and float(lower) - witness > tolerance),
        )
        tables["supp_14"].append(result)
    tables["supp_15"] = rows(DATA / "algebraic_audit/feasible_witnesses.csv")
    for name, records in tables.items():
        write_table(output / f"{name}.csv", records)
    write_table(output / "success_intervals.csv", intervals)
    return tables
