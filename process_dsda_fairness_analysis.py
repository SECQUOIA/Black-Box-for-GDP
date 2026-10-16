"""Verification, provenance-preserving point-cost joins and candidate selection."""

from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    k: json.dumps(v, allow_nan=False)
                    if isinstance(v, (list, dict))
                    else v
                    for k, v in r.items()
                }
            )


def outcome_summary(rows, expected_runs=10):
    groups = defaultdict(list)
    for r in rows:
        groups[r["case"], r["cstr_size"], r["budget"], r["method"]].append(r)
    summaries = []
    for (case, size, budget, method), group in sorted(groups.items()):
        hits = sum(r["lookup_target_hit"] for r in group)
        n = len(group)
        matrix_complete = n == expected_runs
        complete = matrix_complete and all(
            r.get("estimated_total_s") is not None
            and math.isfinite(r["estimated_total_s"])
            for r in group
        )
        median = (
            statistics.median(r["estimated_total_s"] for r in group)
            if complete
            else None
        )
        repeats = (
            None
            if not matrix_complete
            else math.inf
            if hits == 0
            else 1
            if hits == n
            else math.ceil(math.log(0.01) / math.log1p(-hits / n))
        )
        s = {
            "case": case,
            "cstr_size": size,
            "budget": budget,
            "method": method,
            "runs": n,
            "expected_runs": expected_runs,
            "matrix_complete": matrix_complete,
            "target_hits": hits,
            "hit_rate": hits / n if matrix_complete else None,
            "timed_runs": sum(
                r.get("estimated_total_s") is not None
                and math.isfinite(r["estimated_total_s"])
                for r in group
            ),
            "cost_complete": complete,
            "median_completion_s": median,
            "runs_99": repeats,
            "tts99_s": None if median is None else repeats * median,
        }
        fields = (
            "search_overhead_s",
            "accepted_nlp_s",
            "unaccepted_nlp_s",
            "dynamic_preparation_s",
            "estimated_total_s",
        )
        for field in fields:
            s["mean_" + field] = (
                statistics.mean(r[field] for r in group) if complete else None
            )
        for field in fields[:-1]:
            s[field.removesuffix("_s") + "_pct"] = (
                100 * s["mean_" + field] / s["mean_estimated_total_s"]
                if complete
                else None
            )
        if all("total_evals" in r for r in group):
            s["mean_callbacks"] = statistics.mean(r["total_evals"] for r in group)
            s["unsuccessful_callbacks"] = sum(
                r["unsuccessful_evaluations"] for r in group
            )
        summaries.append(s)
    return summaries


def join_costs(spec, events, costs, method_s, preparation_s):
    ledger = []
    missing = []
    accepted = []
    unsuccessful = []
    for e in events:
        key = (spec["case_name"], str(spec.get("grid_size") or ""), tuple(e["point"]))
        point = costs.get(key)
        measured_size = key[1]
        cost_policy = "exact_model_size"
        # User-directed reuse of measured logical-rejection costs at the SAME
        # integer coordinate. Prefer CSTR30; otherwise use the largest measured
        # CSTR instance. Never transfer successful NLP or solver-error costs.
        if (point is None and key[0] == "cstr"
                and e.get("lookup_successful") is False
                and len(key[2]) == 2 and key[2][0] < key[2][1]):
            candidates = [
                (int(size), value) for (case, size, coordinate), value in costs.items()
                if case == "cstr" and coordinate == key[2]
                and value["point_outcome"] == "preprocessing_infeasible"
            ]
            if candidates:
                size, point = max(candidates, key=lambda item: (item[0] == 30, item[0]))
                measured_size = str(size)
                cost_policy = "same_coordinate_logical_rejection_reuse"
        row = {
            **e,
            "job_id": spec["job_id"],
            "case": key[0],
            "cstr_size": key[1],
            "budget": spec["max_evaluations"],
            "seed": spec["seed"],
            "point_evaluation_s": None,
            "point_outcome": "measurement_missing",
            "point_source": None,
            "point_source_sha256": None,
            "point_cost_cstr_size": measured_size,
            "point_cost_policy": cost_policy,
        }
        if point is None:
            missing.append(key)
        else:
            duration = point["point_evaluation_s"]
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("Invalid measured point cost")
            row.update(point)
            (accepted if point["point_outcome"] == "accepted" else unsuccessful).append(
                duration
            )
        ledger.append(row)
    lookup = math.fsum(e["objective_wall_s"] for e in events)
    if method_s < lookup:
        raise ValueError("Method time smaller than lookup time")
    total = (
        None
        if missing
        else math.fsum([method_s - lookup, preparation_s, *accepted, *unsuccessful])
    )
    return (
        {
            "recorded_dfo_s": method_s,
            "recorded_lookup_s": lookup,
            "search_overhead_s": method_s - lookup,
            "accepted_nlp_s": None if missing else math.fsum(accepted),
            "unaccepted_nlp_s": None if missing else math.fsum(unsuccessful),
            "dynamic_preparation_s": preparation_s,
            "estimated_total_s": total,
            "missing_point_costs": len(missing),
            "cost_complete": not missing,
            "reused_cstr_rejection_callbacks": sum(
                r["point_cost_policy"] == "same_coordinate_logical_rejection_reuse"
                for r in ledger
            ),
            "known_point_cost_sum_s": math.fsum([*accepted, *unsuccessful]),
        },
        ledger,
        missing,
    )


def render_candidate(rows, output):
    """Render separate process figures only with all ten costs in every group."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summaries = outcome_summary(rows)
    if any(s["runs"] != 10 or not s["cost_complete"] for s in summaries):
        raise ValueError("Candidate figures require complete ten-seed groups")
    methods = ("dsda", "rbfopt", "bam", "fmqa_sa")
    labels = ("DSDA", "RBFOpt", "BAM", "FMQA-SA")
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd")
    keys = sorted({(r["case"], r["cstr_size"], r["budget"]) for r in rows})

    def title(key):
        case, size, budget = key
        return f"{case.replace('_', ' ').title()} {size} / B={budget}"

    generated = []

    def save_fig(fig, name):
        for suffix in ("png", "svg"):
            p = output / (name + "." + suffix)
            fig.savefig(p, dpi=180, bbox_inches="tight")
            generated.append(p.name)
        plt.close(fig)

    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9}):
        fig, ax = plt.subplots(figsize=(6.5, 7.5))
        matrix = [
            [
                next(
                    s["target_hits"]
                    for s in summaries
                    if (s["case"], s["cstr_size"], s["budget"], s["method"])
                    == (*key, m)
                )
                for m in methods
            ]
            for key in keys
        ]
        ax.imshow(matrix, vmin=0, vmax=10, cmap="Blues", aspect="auto")
        ax.set(
            xticks=range(4),
            xticklabels=labels,
            yticks=range(len(keys)),
            yticklabels=[title(k) for k in keys],
            title="Candidate process target attainment",
        )
        for i, line in enumerate(matrix):
            for j, n in enumerate(line):
                ax.text(
                    j,
                    i,
                    f"{n}/10",
                    ha="center",
                    va="center",
                    color="white" if n >= 7 else "black",
                )
        save_fig(fig, "candidate_target_attainment")
        fig, axes = plt.subplots(4, 4, figsize=(13, 11))
        for ax, key in zip(axes.flat, keys):
            group = [r for r in rows if (r["case"], r["cstr_size"], r["budget"]) == key]
            maximum = max(r["estimated_total_s"] for r in group) * 1.1
            for method, label, color in zip(methods, labels, colors):
                subset = [r for r in group if r["method"] == method]
                times = sorted(
                    r["estimated_total_s"] for r in subset if r["lookup_target_hit"]
                )
                ax.step(
                    [0.0, *times, maximum],
                    [0.0, *[i / 10 for i in range(1, len(times) + 1)], len(times) / 10],
                    where="post",
                    label=label,
                    color=color,
                )
            ax.set(title=title(key), xlabel="Completion estimate (s)", ylim=(0, 1.03))
            ax.grid(alpha=0.2)
        for ax in list(axes.flat)[len(keys) :]:
            ax.set_visible(False)
        axes.flat[0].legend(fontsize=7)
        fig.suptitle("Candidate completed-run profiles — all ten seeds in denominator")
        fig.tight_layout()
        save_fig(fig, "candidate_completion_profiles")
        panels = [
            ("column", "", 16),
            ("cstr", "30", 43),
            ("small_batch", "", 10),
            ("dynamic", "", 50),
        ]
        fig, axes = plt.subplots(2, 2, figsize=(9, 6), sharey=True)
        for ax, key in zip(axes.flat, panels):
            group = [
                next(
                    s
                    for s in summaries
                    if (s["case"], s["cstr_size"], s["budget"], s["method"])
                    == (*key, m)
                )
                for m in methods
            ]
            base = [0.0] * 4
            components = [
                ("search_overhead_pct", "Search overhead", "#295779"),
                ("point_evaluations", "Point evaluations", "#B3CEDC"),
                ("dynamic_preparation_pct", "Preparation", "#D9AC56"),
            ]
            for field, label, color in components:
                values = [
                    s["accepted_nlp_pct"] + s["unaccepted_nlp_pct"]
                    if field == "point_evaluations"
                    else s[field]
                    for s in group
                ]
                ax.bar(range(4), values, bottom=base, label=label, color=color)
                base = [a + b for a, b in zip(base, values)]
            ax.set(
                title=title(key),
                xticks=range(4),
                xticklabels=labels,
                ylim=(0, 100),
                ylabel="Share of mean total (%)",
            )
        axes.flat[0].legend(fontsize=7)
        fig.tight_layout()
        save_fig(fig, "candidate_cost_breakdown")
    return generated


def analyze(directory, output_directory=None):
    from process_dsda_fairness import (
        read,
        sha,
        save,
        valid_job,
        check_events,
        raw_problem,
        verify_plan,
        REFERENCE,
    )

    directory = Path(directory)
    run = read(directory / "run.json")
    if "recovery" in run:
        from process_dsda_fairness_recovery import verify_recovery

        verify_recovery(directory)
    reference_path = directory / "source" / REFERENCE
    if sha(reference_path) != run["reference_sha256"]:
        raise ValueError("Frozen reference changed")
    for name, digest in run["source_files_sha256"].items():
        if sha(directory / "source" / name) != digest:
            raise ValueError("Source snapshot changed")
    ref = read(reference_path)
    full_plan = verify_plan(ref)
    if any(spec not in full_plan for spec in run["plan"]):
        raise ValueError("Unexpected selected run")
    costs = {
        (p["case"], p["cstr_size"], tuple(p["point"])): {
            k: v for k, v in p.items() if k not in ("case", "cstr_size", "point")
        }
        for p in ref["point_costs"]
    }
    if len(costs) != len(ref["point_costs"]):
        raise ValueError("Duplicate point cost keys")
    out = Path(output_directory) if output_directory is not None else directory / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    callbacks = []
    comparisons = []
    missing_groups = defaultdict(list)
    errors = []
    old_selected = {
        r["job_id"]: r for r in ref["selected_runs"] if r["method"] == "dsda"
    }
    for spec in run["plan"]:
        ident = spec["job_id"]
        job = directory / "jobs" / ident
        if not (job / "terminal.json").exists():
            errors.append({"job_id": ident, "status": "missing_or_unsealed"})
            continue
        result = valid_job(job)
        if result["spec"] != spec:
            raise ValueError("Job spec mismatch")
        if result["status"] != "completed":
            errors.append(
                {
                    "job_id": ident,
                    "status": result["status"],
                    "exception": result.get("exception"),
                }
            )
            continue
        events = read(job / "callbacks.json")
        record = result["result_record"]
        raw = [
            json.loads(line)
            for line in (job / result["trace"]["path"]).read_text().splitlines()
        ]
        raw_events = [e for e in raw if e.get("event") == "evaluation"]
        if (raw[0].get("run_key") != spec
                or raw[-1].get("event") != "run_complete"
                or raw[-1].get("result_record") != record
                or result["trace"]["evaluations"] != len(events)):
            raise ValueError("Original trace identity/return mismatch")
        if len(raw_events) != len(events) or any(
            any(e[k] != v for k, v in original.items())
            for e, original in zip(events, raw_events)
        ):
            raise ValueError("Enriched callbacks differ from measured original trace")
        if sha(job / result["trace"]["path"]) != result["trace"]["sha256"]:
            raise ValueError("Trace hash mismatch")
        checks = check_events(spec, events, record)
        if any(result[k] != v for k, v in checks.items()):
            raise ValueError("Target accounting mismatch")
        diag = read(job / "diagnostic_candidates.json")
        if not diag["replay_matches_measured_callbacks"]:
            raise ValueError("Diagnostic replay failed")
        prep = (
            ref["dynamic_preparation"]["total_preparation_wall_s"]
            if spec["case_name"] == "dynamic"
            else 0.0
        )
        timing, ledger, missing = join_costs(
            spec, events, costs, record["wall_time_s"], prep
        )
        for key in missing:
            missing_groups[key].append(ident)
        item = {
            "case": spec["case_name"],
            "cstr_size": str(spec.get("grid_size") or ""),
            "budget": spec["max_evaluations"],
            "seed": spec["seed"],
            "method": "dsda",
            "job_id": ident,
            "lookup_target_hit": checks["target_hit"],
            "target_value": spec["target_value"],
            "recorded_best_value": record["best_value"],
            "recorded_best_point": record["best_point"],
            "total_evals": len(events),
            "unsuccessful_evaluations": checks["unsuccessful_evaluations"],
            "first_target_callback": checks["first_target_callback"],
            "repeated_callbacks": sum(e["repeated_point"] for e in events),
            "stop_reason": result["stop_reason"],
            "source": str(job / "result.json"),
            **timing,
        }
        rows.append(item)
        callbacks.extend(ledger)
        old = ref["old_dsda"][ident]
        oldrow = old_selected[ident]
        oracle = raw_problem(spec)["objective"]
        old_signature = [
            (e["point"], e["value"], e["value_kind"]) for e in old["events"]
        ]
        new_signature = [(e["point"], e["value"], e["value_kind"]) for e in events]
        divergence = next(
            (
                i
                for i, (a, b) in enumerate(zip(old_signature, new_signature), 1)
                if a != b
            ),
            None,
        )
        if divergence is None and len(old_signature) != len(new_signature):
            divergence = min(len(old_signature), len(new_signature)) + 1
        comparison = {
            "case": item["case"],
            "cstr_size": item["cstr_size"],
            "budget": item["budget"],
            "seed": item["seed"],
            "old_target_hit": oldrow["lookup_target_hit"],
            "new_target_hit": item["lookup_target_hit"],
            "old_callbacks": len(old["events"]),
            "new_callbacks": len(events),
            "old_unsuccessful_callbacks": sum(
                not math.isfinite(oracle(e["point"])) for e in old["events"]
            ),
            "new_unsuccessful_callbacks": item["unsuccessful_evaluations"],
            "first_trajectory_divergence": divergence,
            "old_stop_reason": old["stop_reason"],
            "new_stop_reason": item["stop_reason"],
            "old_estimated_total_s": oldrow["estimated_total_s"],
            "new_estimated_total_s": item["estimated_total_s"],
            "cost_change_s": None
            if item["estimated_total_s"] is None
            else item["estimated_total_s"] - oldrow["estimated_total_s"],
            "new_path_candidates_old_filter_would_skip": sum(
                bool(r.get("would_be_excluded_by_old_finite_map"))
                for r in diag["records"]
            ),
            "skip_count_scope": "Membership tests on corrected diagnostic path; not hypothetical repair of historical path",
        }
        comparisons.append(comparison)
        if spec["case_name"] == "small_batch" and (
            divergence is not None
            or item["lookup_target_hit"] != oldrow["lookup_target_hit"]
        ):
            raise ValueError(
                "Unchanged full-domain Small Batch failed archived regression"
            )
    missing = [
        {
            "case": key[0],
            "cstr_size": key[1],
            "point": list(key[2]),
            "callback_visits": len(ids),
            "affected_runs": sorted(set(ids)),
            "required_profile": "existing GAMS/IPOPT, auto initialization, 60 seconds; original model/size; successful retry policy",
        }
        for key, ids in sorted(missing_groups.items())
    ]
    write_csv(out / "runs.csv", rows)
    write_csv(out / "callbacks_and_costs.csv", callbacks)
    write_csv(out / "old_vs_new.csv", comparisons)
    write_csv(
        out / "missing_point_requests.csv",
        missing,
        fields=[
            "case",
            "cstr_size",
            "point",
            "callback_visits",
            "affected_runs",
            "required_profile",
        ],
    )
    write_csv(out / "dsda_summary.csv", outcome_summary(rows))
    grouped = defaultdict(list)
    for r in comparisons:
        grouped[r["case"], r["cstr_size"], r["budget"]].append(r)
    compact = []
    for (case, size, budget), group in sorted(grouped.items()):
        compact.append(
            {
                "case": case,
                "cstr_size": size,
                "budget": budget,
                "runs": len(group),
                "old_target_hits": sum(r["old_target_hit"] for r in group),
                "new_target_hits": sum(r["new_target_hit"] for r in group),
                "old_callbacks": sum(r["old_callbacks"] for r in group),
                "new_callbacks": sum(r["new_callbacks"] for r in group),
                "old_unsuccessful_callbacks": sum(
                    r["old_unsuccessful_callbacks"] for r in group
                ),
                "new_unsuccessful_callbacks": sum(
                    r["new_unsuccessful_callbacks"] for r in group
                ),
                "changed_paths": sum(
                    r["first_trajectory_divergence"] is not None for r in group
                ),
                "new_cost_complete": len(group) == 10 and all(
                    r["new_estimated_total_s"] is not None for r in group
                ),
            }
        )
    write_csv(out / "old_vs_new_summary.csv", compact)
    complete = (
        len(rows) == 140
        and not errors
        and not run["development_only"]
        and not run["smoke_only"]
    )
    figures = []
    figure_error = None
    if complete:
        preserved = [r for r in ref["selected_runs"] if r["method"] != "dsda"]
        digest = hashlib.sha256(
            json.dumps(preserved, sort_keys=True).encode()
        ).hexdigest()
        if digest != ref["non_dsda_sha256"]:
            raise ValueError("Changed non-DSDA rows")
        candidate = preserved + rows
        if (
            len(candidate) != 560
            or len(
                {
                    (r["case"], r["cstr_size"], r["budget"], r["seed"], r["method"])
                    for r in candidate
                }
            )
            != 560
        ):
            raise ValueError("Invalid candidate publication selection")
        save(out / "candidate_selection.json", candidate)
        write_csv(out / "candidate_selection.csv", candidate)
        write_csv(out / "candidate_summary.csv", outcome_summary(candidate))
        profile = [
            {
                **r,
                "profile_completion_s": None
                if r["estimated_total_s"] is None
                else r["estimated_total_s"]
                if r["lookup_target_hit"]
                else math.inf,
            }
            for r in candidate
        ]
        write_csv(out / "candidate_profile_runs.csv", profile)
        if not missing:
            try:
                figures = render_candidate(candidate, out)
            except ImportError as error:
                figure_error = str(error)
    summary = {
        "kind": "process_dsda_fairness_verified_results",
        "planned_runs": len(run["plan"]),
        "completed_runs": len(rows),
        "preserved_parent_jobs": len(run.get("recovery", {}).get("preserved_job_ids", [])),
        "remeasured_job_ids": run.get("recovery", {}).get("remeasured_job_ids", []),
        "errors": errors,
        "dantzig_matrix_complete": complete,
        "development_only": run["development_only"],
        "callbacks": len(callbacks),
        "missing_unique_points": len(missing),
        "missing_callback_costs": sum(len(v) for v in missing_groups.values()),
        "reused_cstr_rejection_callbacks": sum(
            r["point_cost_policy"] == "same_coordinate_logical_rejection_reuse"
            for r in callbacks
        ),
        "cstr_rejection_cost_policy": (
            "Keep existing costs; fill missing logical-rejection costs from the same coordinate, "
            "preferring CSTR30 then the largest measured CSTR size; retain measured size and source"
        ),
        "timing_reconstruction_complete": complete and not missing,
        "candidate_selection_created": complete,
        "preserved_non_dsda_rows": 420 if complete else None,
        "preserved_non_dsda_sha256": ref["non_dsda_sha256"],
        "official_results_modified": False,
        "new_nlp_solves": 0,
        "figures_status": "Pending complete Dantzig matrix and all required costs"
        if not complete or missing
        else "Generated; visual review pending"
        if figures
        else "Plotting dependency unavailable",
        "figure_files": figures,
        "figure_error": figure_error,
        "timing_definition": "method time minus lookup callback time plus measured cost for every callback plus one reference Dynamic preparation",
        "missing_cost_policy": "Keep search outcome; no subset median or aggregate TTS99 for incomplete groups",
        "initialization_only_exception_policy": "No reseeding/restoration; failed initialization retained as job error with partial trace",
    }
    save(out / "summary.json", summary)
    (
        out / "affected_artifacts.txt"
    ).write_text("""Candidate replacement only; original publications remain untouched.
results/dfo_trace_nlp_20261002/figures/cost_breakdown.{pdf,png,csv}: DSDA components.
results/dfo_trace_nlp_20261002/figures/performance_profiles.{pdf,png}: DSDA completion profile.
results/dfo_trace_nlp_20261002/figures/completion_time_scatter.{pdf,png} and tts99 aliases: DSDA runs.
results/dfo_trace_nlp_20261002/figures/tts99_summary.csv: affected DSDA probabilities and costs.
results/dfo_trace_nlp_20261002/figures/all_method_completion_times.*: DSDA rows only; GDP/MINLP unchanged.
Process attainment/evaluation-convergence claims using these selected DSDA paths.
Historical October 2 analysis remains evidence and must not be overwritten.
Manuscript labels were not available; do not infer figure numbers or edit prose.
""")
    return summary
