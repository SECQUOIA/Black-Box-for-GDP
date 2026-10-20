"""Completed records only; fixed-path scenarios and paired comparisons, no solves."""

from collections import Counter, defaultdict
import math
import random
import statistics
import time

from .common import csvrows, save, writecsv


def historical(root):
    result = []
    for row in csvrows(root / "data/historical_grid_runs.csv"):
        result.append(
            {
                "scope": "grid",
                "case": row["grid_name"],
                "budget": int(row["max_evals"]),
                "seed": int(row["seed"]),
                "method": "rbfopt_msrsm_solver"
                if row["method"] == "rbfopt"
                else row["method"],
                "category": "target_reached"
                if row["target_hit"] == "True"
                else "target_not_reached",
                "best_objective": float(row["best_value"]),
                "evaluations": int(row["total_evals"]),
                "search_s": float(row["retained_search_wall_s"]),
                "lookup_s": float(row["recorded_lookup_wall_s"])
                if row["recorded_lookup_wall_s"]
                else None,
                "point_cost_s": float(row["sum_point_wall_s"]),
                "prep_s": 0.0,
                "record_source": "historical_grid_runs.csv",
                "lookup_accounting": "unmeasured; retained recorded wall, not zero lookup"
                if not row["recorded_lookup_wall_s"]
                else "subtracted",
            }
        )
    for row in csvrows(root / "data/historical_process_runs.csv"):
        result.append(
            {
                "scope": "process",
                "case": row["case"],
                "budget": int(row["budget"]),
                "seed": int(row["seed"]),
                "method": "rbfopt_msrsm_solver"
                if row["method"] == "rbfopt"
                else row["method"],
                "category": row["category"],
                "best_objective": float(row["best_observed_objective"])
                if row["best_observed_objective"]
                else None,
                "evaluations": int(row["logged_callbacks"]),
                "search_s": float(row["dfo_wall_s"]) - float(row["lookup_wall_s"]),
                "lookup_s": float(row["lookup_wall_s"]),
                "point_cost_s": float(row["historical_nlp_known_within_budget_s"]),
                "prep_s": float(row["dynamic_preparation_s"]),
                "record_source": "historical_process_runs.csv",
                "lookup_accounting": "subtracted",
            }
        )
    return result


def paired_interval(groups, seed=20261020, replications=2000, clustered=False):
    """Resample intact problem vectors for Grid; seed pairs for a single Process condition."""
    rng = random.Random(seed)
    samples = []
    if clustered:
        for _ in range(replications):
            samples.append(
                statistics.mean(statistics.mean(rng.choice(groups)) for _ in groups)
            )
    else:
        pairs = groups[0]
        for _ in range(replications):
            samples.append(statistics.mean(rng.choices(pairs, k=len(pairs))))
    samples.sort()
    return samples[int(0.025 * replications)], samples[int(0.975 * replications)]


def summarize(root, directory, jobs):
    from .runner import selected_result, snapshot, unsealed_state

    output = directory / f"analysis_{time.time_ns()}"
    output.mkdir(parents=True)
    rows = historical(root)
    slots = []
    for job in jobs:
        selection = selected_result(directory, job)
        slots.append(
            {k: job[k] for k in ("job_id", "scope", "case", "budget", "seed", "method")}
        )
        if not selection:
            slots[-1]["state"] = unsealed_state(directory, job)
            continue
        attempt, r = selection
        slots[-1]["state"] = r["category"]
        rows.append(
            {k: job[k] for k in ("scope", "case", "budget", "seed", "method")}
            | {
                "category": r["category"],
                "best_objective": r["best_objective"],
                "evaluations": r["evaluations"],
                "search_s": r["retained_search_wall_s"],
                "lookup_s": r["lookup_wall_s"],
                "point_cost_s": r["sum_point_cost_s"],
                "prep_s": r["one_time_preparation_s"],
                "record_source": str(attempt.relative_to(directory)),
                "lookup_accounting": "subtracted",
            }
        )
    writecsv(output / "new_slots.csv", slots)
    writecsv(output / "completed_runs.csv", rows)
    groups = defaultdict(list)
    for r in rows:
        groups[r["scope"], r["case"], r["budget"], r["method"]].append(r)
    summary = []
    for key, rr in sorted(groups.items()):
        n = len(rr)
        if n != len({r["seed"] for r in rr}):
            raise ValueError("Duplicate selected seed")
        counts = Counter(r["category"] for r in rr)
        complete = n == 10 and {r["seed"] for r in rr} == set(range(10))
        costs = [
            r["search_s"] + r["point_cost_s"] + r["prep_s"]
            for r in rr
            if r["point_cost_s"] is not None
        ]
        hits = counts["target_reached"]
        p = hits / 10 if complete else None
        median = statistics.median(costs) if complete and len(costs) == 10 else None
        tts = (
            median * (1 if p == 1 else math.ceil(math.log(0.01) / math.log1p(-p)))
            if p and median is not None
            else None
        )
        summary.append(
            dict(zip(("scope", "case", "budget", "method"), key))
            | {
                "completed_slots": n,
                "target_reached": hits,
                "target_not_reached": counts["target_not_reached"],
                "execution_failed": counts["execution_failed"],
                "not_completed": 10 - n,
                "ten_seed_condition_complete": complete,
                "success_rate": p,
                "median_completion_s": median,
                "empirical_tts99_s": tts,
                "tts99_status": "infinite_zero_hits"
                if p == 0
                else "finite"
                if tts is not None
                else "incomplete",
                "tts99_interpretation": "median cost times geometric independent-restart estimate; not a measured 99th percentile or guarantee",
            }
        )
    writecsv(output / "condition_summary.csv", summary)
    sensitivity = []
    exclusion = []
    for selection, excluded in [
        ("all", set()),
        ("without_yang3", {"xin_she_yang3"}),
        ("without_yang3_bohachevsky2", {"xin_she_yang3", "bohachevsky2"}),
    ]:
        for r in rows:
            if r["scope"] == "grid" and r["case"] in excluded:
                continue
            for alpha in (0.01, 0.1, 1.0, 10.0, 100.0):
                sensitivity.append(
                    {
                        k: r[k]
                        for k in (
                            "scope",
                            "case",
                            "budget",
                            "seed",
                            "method",
                            "category",
                        )
                    }
                    | {
                        "subset": selection,
                        "alpha": alpha,
                        "fixed_path_cost_s": r["search_s"]
                        + alpha * r["point_cost_s"]
                        + r["prep_s"]
                        if r["point_cost_s"] is not None
                        else None,
                    }
                )
        pooled = defaultdict(list)
        for s in summary:
            if (
                s["scope"] == "grid"
                and s["case"] not in excluded
                and s["ten_seed_condition_complete"]
            ):
                pooled[s["budget"], s["method"]].append(s)
        for (budget, method), ss in sorted(pooled.items()):
            exclusion.append(
                {
                    "subset": selection,
                    "budget": budget,
                    "method": method,
                    "complete_problem_groups": len(ss),
                    "expected_problem_groups": 21 - len(excluded),
                    "mean_problem_success_rate": statistics.mean(
                        s["success_rate"] for s in ss
                    ),
                    "mean_problem_median_cost_s": statistics.mean(
                        s["median_completion_s"] for s in ss
                    )
                    if all(s["median_completion_s"] is not None for s in ss)
                    else None,
                    "scope_complete": len(ss) == 21 - len(excluded),
                }
            )
    writecsv(output / "fixed_path_sensitivity.csv", sensitivity)
    writecsv(output / "grid_exclusions.csv", exclusion)
    pairs = []
    contrasts = [
        ("dsda", "rbfopt_msrsm_solver"),
        ("dsda", "bam"),
        ("dsda", "fmqa_sa"),
        ("rbfopt_msrsm_solver", "rbfopt_msrsm_genetic"),
        ("rbfopt_msrsm_solver", "uniform_without_replacement"),
        ("bam", "bam_predetermined_uniform"),
        ("bam", "uniform_without_replacement"),
    ]
    for old, new in contrasts:
        for scope in ("grid", "process"):
            buckets = defaultdict(list)
            for (sc, case, budget, method), base in groups.items():
                if sc != scope or method != old:
                    continue
                added = groups.get((sc, case, budget, new), [])
                if len(base) != 10 or len(added) != 10:
                    continue
                a = {r["seed"]: r["category"] == "target_reached" for r in base}
                b = {r["seed"]: r["category"] == "target_reached" for r in added}
                diffs = [int(b[s]) - int(a[s]) for s in range(10)]
                buckets[
                    (budget, "all_grid_problems" if scope == "grid" else case)
                ].append((case, diffs))
            for (budget, case), vectors in buckets.items():
                low, high = paired_interval(
                    [v for _, v in vectors], clustered=scope == "grid"
                )
                pairs.append(
                    {
                        "scope": scope,
                        "case": case,
                        "budget": budget,
                        "reference": old,
                        "new": new,
                        "problem_groups": len(vectors),
                        "expected_problem_groups": 21 if scope == "grid" else 1,
                        "scope_complete": len(vectors)
                        == (21 if scope == "grid" else 1),
                        "group_names": [c for c, _ in vectors],
                        "mean_paired_success_difference": statistics.mean(
                            statistics.mean(v) for _, v in vectors
                        ),
                        "bootstrap_95_low": low,
                        "bootstrap_95_high": high,
                        "bootstrap_replications": 2000,
                        "unit": "intact function with ten paired seeds"
                        if scope == "grid"
                        else "paired seed within condition",
                        "warning": "Percentile bootstrap descriptive uncertainty; ten seeds, boundary degeneracy possible; incomplete condition pairs excluded and counted explicitly",
                    }
                )
    writecsv(output / "paired_success.csv", pairs)
    save(output / "progress.json", snapshot(directory, jobs))
    save(
        output / "interpretation.json",
        {
            "new_data_complete": all(
                s["state"]
                in ("target_reached", "target_not_reached", "execution_failed")
                for s in slots
            ),
            "scope": "Completed first sealed attempts only; no best-of-retries; all unexecuted slots retained in new_slots.csv",
            "scenario": "T_search + alpha * sum(point costs) + T_prep conditional on recorded paths; not predicted adaptive trajectories under new time limits",
            "endpoints": "Recorded search-stage endpoint is primary. Incumbent extraction/export clocks of new runs are additional and not added to historical endpoint.",
            "legacy_DSDA": "Grid lookup subtraction unavailable; retained wall includes lookup. No zero timing assumed.",
            "inference": "Unequal elapsed times across hosts are not comparable; new formal runs require Dantzig. BAM prefix control does not isolate all BAM components.",
        },
    )
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(11, 5))
        for method in sorted({s["method"] for s in summary}):
            points = [
                s
                for s in summary
                if s["method"] == method
                and s["scope"] == "process"
                and s["ten_seed_condition_complete"]
            ]
            if points:
                labels = sorted(
                    {
                        (s["case"], s["budget"])
                        for s in summary
                        if s["scope"] == "process"
                    }
                )
                ax.plot(
                    [labels.index((s["case"], s["budget"])) for s in points],
                    [s["success_rate"] for s in points],
                    marker="o",
                    label=method,
                )
        if ax.lines:
            ax.set_xticks(
                range(len(labels)), [f"{c}\nB{b}" for c, b in labels], rotation=60
            )
            ax.set_ylim(-0.05, 1.05)
            ax.set_ylabel("Target attainment / ten seeds")
            ax.legend(fontsize=7)
            fig.tight_layout()
            fig.savefig(output / "process_success_draft.pdf")
        plt.close(fig)
        save(
            output / "plot_status.json",
            {"rendered": bool(ax.lines), "new_comparison_may_be_pending": True},
        )
    except ImportError as exc:
        save(
            output / "plot_status.json",
            {"rendered": False, "reason": str(exc), "tables_complete": True},
        )
    return output
