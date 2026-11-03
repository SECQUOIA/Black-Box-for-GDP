"""Audit the completed Column return and compare fixed historical cohorts."""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import statistics
import sys


def compare(run, package, replay, output):
    sys.path.insert(0, str(package))
    from common import (
        METHODS,
        THREADS,
        csvwrite,
        events,
        hit,
        read,
        require,
        sha,
        table,
        verify_package,
        write,
    )
    from analyze import selected

    require(not output.exists(), "Use a fresh comparison directory")
    output.mkdir(parents=True)
    plan, costs = verify_package(package)
    original_costs = table(package / "inputs/column_81_original.csv")
    target = plan[0]["target"]
    require(
        [
            p
            for p, r in original_costs.items()
            if r["accepted"] == "True" and hit(float(r["objective"]), target)
        ]
        == [(13, 4)],
        "Target-coordinate inventory differs",
    )
    records = read(replay / "runs.json")
    metrics = {(r["condition"], r["method"], r["seed"]): r for r in records}
    require(len(metrics) == len(records) == 100, "Cohort identity is not unique")
    returned_analysis = list(run.glob("analysis_*"))
    require(len(returned_analysis) == 1, "Ambiguous returned analysis")
    server_analysis = returned_analysis[0]
    replay_identical = []
    for name in (
        "README.md",
        "attempt_inventory.json",
        "callback_ledger.csv",
        "methods.csv",
        "methods.json",
        "profiles.csv",
        "profiles.json",
        "runs.csv",
        "runs.json",
        "verification.json",
    ):
        require(
            sha(replay / name) == sha(server_analysis / name),
            "Server/local replay differs: " + name,
        )
        replay_identical.append(name)
    details, runtime_checks, intervals, auxiliary = [], [], [], []
    coordinate_counts = Counter()
    for job in plan:
        spec = job["spec"]
        method, seed = spec["method"], spec["seed"]
        new = selected(run, spec["job_id"])
        require(new is not None, "Missing terminal run")
        attempts = list((run / "jobs" / spec["job_id"]).glob("attempt_*"))
        require(len(attempts) == 1, "Multiple attempts require separate treatment")
        runtime = read(new / "runtime.json")
        expected = job["reference_runtime"]
        for key in ("python", "executable", "host", "versions", "platform"):
            require(runtime[key] == expected[key], "Recorded runtime mismatch: " + key)
        require(
            runtime["effective_cpus"] == [2]
            and runtime["threads"] == THREADS
            and runtime["cuda_visible_devices"] == "",
            "CPU/thread/GPU policy mismatch",
        )
        if method != "uniform_without_replacement":
            require(
                read(new / "actual_settings.json") == job["expected_settings"],
                "Optimizer settings mismatch",
            )
            require(
                read(new / "settings_verification.json")["passed"],
                "Settings verification failed",
            )
        if method == "rbfopt":
            for name in ("bonmin", "ipopt"):
                require(
                    runtime[name + "_sha256"] == expected["binary_sha256"][name],
                    "Auxiliary executable differs",
                )
        if method == "fmqa_sa":
            require(
                runtime["qhd_source"] == expected["qhd_source"], "FMQA source differs"
            )
        result = read(new / "result.json")
        process = read(new / "process.json")
        new_events = events(new / "callbacks.jsonl")
        require(
            result["status"] in ("completed", "budget_completed"),
            "New algorithm failure",
        )
        require(
            result["process_nlp_calls"] == 0 and not result["callback_budget_overrun"],
            "Forbidden process solve or overrun",
        )
        require(
            result["callback_count"] == len(new_events) <= 13
            and [e["point"] for e in new_events[:3]] == spec["starts"],
            "Callback budget/initial design mismatch",
        )
        require(
            result["evaluation_table_sha256"] == sha(package / "inputs/column_64.csv"),
            "Evaluation table identity differs",
        )
        require(
            process["returncode"] == 0
            and not process["watchdog_timeout"]
            and process["command"][:3] == ["taskset", "-c", "2"],
            "Worker/controller execution failed",
        )
        intervals.append(
            (process["started_utc"], process["finished_utc"], spec["job_id"])
        )
        runtime_checks.append(
            dict(
                job_id=spec["job_id"],
                passed=True,
                runtime_sha256=sha(new / "runtime.json"),
                terminal_sha256=sha(new / "terminal.json"),
            )
        )
        aux = events(new / "auxiliary_solver_calls.jsonl")
        require(
            not aux or method == "rbfopt",
            "Unexpected externally journaled auxiliary solver",
        )
        if aux:
            require(len(aux) % 2 == 0, "Incomplete auxiliary solver journal")
            for start, end in zip(aux[::2], aux[1::2]):
                require(
                    start["event"] == "start"
                    and start["scope"] == "RBFOpt surrogate only"
                    and end["event"] == "end"
                    and start["solver"] == end["solver"]
                    and start["solver"] in ("bonmin", "ipopt"),
                    "Unexpected auxiliary call",
                )
                auxiliary.append(
                    dict(
                        job_id=spec["job_id"],
                        solver=start["solver"],
                        seconds=end["wall_s"],
                        termination=end["termination"],
                    )
                )
        for condition, path in [
            ("81_B16", package / "baseline/jobs" / job["baseline_job"]),
            ("64_B13", new),
        ]:
            ev = events(path / "callbacks.jsonl")
            m = metrics[condition, method, seed]
            wall = m["search_s"]
            require(
                wall is not None and wall >= sum(e["lookup_wall_s"] for e in ev),
                "Invalid recorded search endpoint",
            )
            expected_cost = sum(
                float(original_costs[tuple(e["point"])]["total_wall_s"]) for e in ev
            )
            require(
                abs(m["point_cost_s"] - expected_cost) < 1e-9
                and abs(
                    m["completion_s"]
                    - (expected_cost + wall - sum(e["lookup_wall_s"] for e in ev))
                )
                < 1e-9,
                "Time reconstruction differs",
            )
            accepted = [e for e in ev if e["accepted"]]
            best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
            independent_hit = bool(
                best
                and hit(best["raw_objective"], target)
                and m["status"] in ("completed", "budget_completed")
            )
            require(
                m["target_hit"] == independent_hit, "Final best target rule differs"
            )
            initial_hit = any(
                e["accepted"] and hit(e["raw_objective"], target) for e in ev[:3]
            )
            details.append(
                dict(
                    condition=condition,
                    method=method,
                    seed=seed,
                    **{
                        k: v
                        for k, v in m.items()
                        if k not in ("condition", "method", "seed")
                    },
                    initial_points=[e["point"] for e in ev[:3]],
                    initial_accepted=sum(e["accepted"] for e in ev[:3]),
                    initial_target=initial_hit,
                    accepted_callbacks=len(accepted),
                    unaccepted_callbacks=len(ev) - len(accepted),
                    repeated_callbacks=len(ev) - len({tuple(e["point"]) for e in ev}),
                    excluded_coordinate_callbacks=sum(
                        tuple(e["point"]) not in costs for e in ev
                    ),
                    first_target_after_initial=bool(
                        m["target_hit"] and m["first_hit"] > 3
                    ),
                )
            )
            for e in ev:
                coordinate_counts[condition, method, tuple(e["point"])] += 1
    intervals.sort()
    require(
        all(
            previous[1] <= current[0]
            for previous, current in zip(intervals, intervals[1:])
        ),
        "Concurrent workers observed",
    )
    paired, methods = [], []
    for method in METHODS:
        old = {
            r["seed"]: r
            for r in details
            if r["method"] == method and r["condition"] == "81_B16"
        }
        new = {
            r["seed"]: r
            for r in details
            if r["method"] == method and r["condition"] == "64_B13"
        }
        require(set(old) == set(new) == set(range(10)), "Denominator changed")
        for seed in range(10):
            a, b = old[seed], new[seed]
            outcome = (
                "both_success"
                if a["target_hit"] and b["target_hit"]
                else "new_only"
                if b["target_hit"]
                else "old_only"
                if a["target_hit"]
                else "neither"
            )
            paired.append(
                dict(
                    method=method,
                    seed=seed,
                    old_budget=16,
                    new_budget=13,
                    outcome=outcome,
                    old_target=a["target_hit"],
                    new_target=b["target_hit"],
                    old_status=a["status"],
                    new_status=b["status"],
                    old_best=a["best_objective"],
                    new_best=b["best_objective"],
                    old_starts=a["initial_points"],
                    new_starts=b["initial_points"],
                    old_initial_target=a["initial_target"],
                    new_initial_target=b["initial_target"],
                    old_first_hit=a["first_hit"],
                    new_first_hit=b["first_hit"],
                    old_callbacks=a["callbacks"],
                    new_callbacks=b["callbacks"],
                    old_completion_s=a["completion_s"],
                    new_completion_s=b["completion_s"],
                    paired_completion_delta_s=b["completion_s"] - a["completion_s"],
                    old_point_cost_s=a["point_cost_s"],
                    new_point_cost_s=b["point_cost_s"],
                    old_search_overhead_s=a["retained_search_s"],
                    new_search_overhead_s=b["retained_search_s"],
                )
            )
        paired_method = [r for r in paired if r["method"] == method]
        row = dict(
            method=method,
            denominator=10,
            **{
                k: sum(r["outcome"] == k for r in paired_method)
                for k in ("both_success", "new_only", "old_only", "neither")
            },
        )
        for label, cohort in [("old", old), ("new", new)]:
            values = list(cohort.values())
            row.update(
                {
                    label + "_hits": sum(r["target_hit"] for r in values),
                    label + "_hit_seeds": [
                        r["seed"] for r in values if r["target_hit"]
                    ],
                    label + "_failures": sum(
                        r["category"] == "execution_failed" for r in values
                    ),
                    label + "_callbacks": sum(r["callbacks"] for r in values),
                    label + "_median_completion_s": statistics.median(
                        r["completion_s"] for r in values
                    ),
                    label + "_median_point_cost_s": statistics.median(
                        r["point_cost_s"] for r in values
                    ),
                    label + "_median_search_overhead_s": statistics.median(
                        r["retained_search_s"] for r in values
                    ),
                    label + "_total_point_cost_s": sum(
                        r["point_cost_s"] for r in values
                    ),
                    label + "_accepted_callbacks": sum(
                        r["accepted_callbacks"] for r in values
                    ),
                    label + "_unaccepted_callbacks": sum(
                        r["unaccepted_callbacks"] for r in values
                    ),
                    label + "_repeated_callbacks": sum(
                        r["repeated_callbacks"] for r in values
                    ),
                    label + "_excluded_coordinate_callbacks": sum(
                        r["excluded_coordinate_callbacks"] for r in values
                    ),
                    label + "_initial_target_runs": sum(
                        r["initial_target"] for r in values
                    ),
                    label + "_first_target_after_initial_runs": sum(
                        r["first_target_after_initial"] for r in values
                    ),
                }
            )
        row["median_completion_percent_change"] = 100 * (
            row["new_median_completion_s"] / row["old_median_completion_s"] - 1
        )
        row["historical_B16_hits_observed_by_callback13"] = sum(
            r["target_hit"] and r["first_hit"] <= 13 for r in old.values()
        )
        row["median_paired_completion_delta_s"] = statistics.median(
            r["paired_completion_delta_s"] for r in paired_method
        )
        methods.append(row)
    coordinates = []
    for method in METHODS:
        for point, row in sorted(original_costs.items()):
            a = coordinate_counts["81_B16", method, point]
            b = coordinate_counts["64_B13", method, point]
            cost = float(row["total_wall_s"])
            coordinates.append(
                dict(
                    method=method,
                    point=list(point),
                    accepted=row["accepted"] == "True",
                    retained_domain=point in costs,
                    point_cost_s=cost,
                    old_visits=a,
                    new_visits=b,
                    old_charged_cost_s=a * cost,
                    new_charged_cost_s=b * cost,
                    charged_cost_change_s=(b - a) * cost,
                )
            )
        require(
            abs(
                sum(
                    r["charged_cost_change_s"]
                    for r in coordinates
                    if r["method"] == method
                )
                - (
                    next(r for r in methods if r["method"] == method)[
                        "new_total_point_cost_s"
                    ]
                    - next(r for r in methods if r["method"] == method)[
                        "old_total_point_cost_s"
                    ]
                )
            )
            < 1e-8,
            "Coordinate cost attribution differs",
        )
    initial_designs = [
        dict(
            seed=s,
            old=next(
                r for r in details if r["seed"] == s and r["condition"] == "81_B16"
            )["initial_points"],
            new=next(
                r for r in details if r["seed"] == s and r["condition"] == "64_B13"
            )["initial_points"],
        )
        for s in range(10)
    ]
    for seed in range(10):
        for condition in ("81_B16", "64_B13"):
            starts = [
                r["initial_points"]
                for r in details
                if r["seed"] == seed and r["condition"] == condition
            ]
            require(
                len(starts) == 5 and all(s == starts[0] for s in starts),
                "Shared initial design differs",
            )
    run_info = read(run / "run.json")

    def elapsed(a, b):
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()

    cpu_records = list(run.glob("cpu2_occupancy_*.json"))
    require(len(cpu_records) == 1, "Unexpected occupancy attempts")
    cpu = read(cpu_records[0])
    require(cpu["permitted_to_start"] and not cpu["blockers"], "CPU preflight failed")
    report = dict(
        complete=True,
        new_jobs=50,
        new_failures=0,
        new_pending=0,
        new_attempts=50,
        old_hits=sum(r["old_hits"] for r in methods),
        new_hits=sum(r["new_hits"] for r in methods),
        old_callbacks=sum(r["old_callbacks"] for r in methods),
        new_callbacks=sum(r["new_callbacks"] for r in methods),
        old_initial_target_runs=sum(r["old_initial_target_runs"] for r in methods),
        new_initial_target_runs=sum(r["new_initial_target_runs"] for r in methods),
        old_first_target_after_initial_runs=sum(
            r["old_first_target_after_initial_runs"] for r in methods
        ),
        new_first_target_after_initial_runs=sum(
            r["new_first_target_after_initial_runs"] for r in methods
        ),
        new_terminal_first_hits=[
            dict(method=r["method"], seed=r["seed"])
            for r in details
            if r["condition"] == "64_B13" and r["first_hit"] == 13
        ],
        reference_point=[13, 4],
        reference_objective=target,
        reference_absolute_tolerance=1e-5 * max(1, abs(target)),
        old_domain_size=len(original_costs),
        new_domain_size=len(costs),
        accepted_inventory_old=sum(
            r["accepted"] == "True" for r in original_costs.values()
        ),
        accepted_inventory_new=sum(r["accepted"] == "True" for r in costs.values()),
        old_budget=16,
        new_budget=13,
        old_budget_fraction=16 / 81,
        new_budget_fraction=13 / 64,
        controller_elapsed_before_pack_s=elapsed(
            run_info["created_utc"], run_info["finished_utc"]
        ),
        sequential_job_phase_s=elapsed(
            run_info["preflight_passed_utc"], run_info["finished_utc"]
        ),
        measured_search_wall_total_s=sum(
            r["search_s"] for r in details if r["condition"] == "64_B13"
        ),
        original_process_nlp_calls=0,
        analysis_optimizer_calls=0,
        auxiliary_calls=dict(Counter(r["solver"] for r in auxiliary)),
        auxiliary_call_wall_s=sum(r["seconds"] for r in auxiliary),
        bam_internal_surrogate_accounting="Included in search overhead; not individually journaled.",
        cpu=2,
        smt_siblings=cpu["siblings"],
        cpu_busy_percent_over_window=cpu["busy_percent_over_window"],
        runtime_and_settings_checks=len(runtime_checks),
        source_revision=read(package / "manifest.json")["source_base_revision"],
        package_manifest_sha256=sha(package / "manifest.json"),
        server_replay_byte_identical_outputs=replay_identical,
        all_five_methods_shared_ordered_initials=True,
        workers_sequential=True,
        no_new_original_nlp_reason="Exact pinned lookup-only source, process-model import guard, same-attempt input rows and separate permitted surrogate journal were verified.",
        caveat="Domain, budget and regenerated common initial designs change together; the paired ten-seed comparison is descriptive rather than a single-factor causal estimate.",
    )
    for name, data in [
        ("methods", methods),
        ("paired_runs", paired),
        ("run_details", details),
        ("coordinate_cost_attribution", coordinates),
        ("initial_designs", initial_designs),
        ("auxiliary_calls", auxiliary),
    ]:
        write(output / (name + ".json"), data)
        csvwrite(output / (name + ".csv"), data)
    write(output / "runtime_verification.json", runtime_checks)
    write(output / "summary.json", report)
    labels = dict(
        dsda="D-SDA",
        rbfopt="RBFOpt",
        bam="BAM",
        fmqa_sa="FMQA-SA",
        uniform_without_replacement="Uniform",
    )
    lines = [
        "# Column logical-domain/B13 follow-up versus historical B16",
        "",
        "All 50 new jobs completed without execution failure, with 648 charged callbacks and no original process NLP calculation.",
        f"Total target hits change from {report['old_hits']}/50 to {report['new_hits']}/50, which is a small aggregate difference rather than broad evidence of improved search.",
        "The comparison is between the historical 81-coordinate/B16 cohort and the 64-coordinate/B13 cohort, with newly generated shared initial points.",
        "The domain, budget and common initial designs changed together, so this comparison does not isolate any one factor.",
        "Every method retains ten seeds in the denominator, and the historical D-SDA execution failure remains in all primary counts and timing summaries.",
        "",
        "| Method | B16 hits / 10 | B13 hits / 10 | B16 median reconstructed completion (s) | B13 median reconstructed completion (s) | Change |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in methods:
        lines.append(
            f"| {labels[row['method']]} | {row['old_hits']} | {row['new_hits']} | {row['old_median_completion_s']:.3f} | {row['new_median_completion_s']:.3f} | {row['median_completion_percent_change']:+.1f}% |"
        )
    lines += [
        "",
        "## Earlier target observations",
        "",
        "The new evaluation profiles reach their final success levels within thirteen callbacks, whereas several historical successes occur at callbacks fourteen through sixteen.",
        "Reading the first thirteen callbacks of the archived B16 paths gives the descriptive counts below.",
        "These prefixes are not new B13 runs and do not isolate the budget effect, because the actual algorithms used B16 settings, the old domain and the old initial designs.",
        "",
        "| Method | Historical B16 paths by callback 13 | New B13 runs |",
        "| --- | ---: | ---: |",
    ]
    for row in methods:
        lines.append(
            f"| {labels[row['method']]} | {row['historical_B16_hits_observed_by_callback13']}/10 | {row['new_hits']}/10 |"
        )
    lines += [
        "",
        "## Initial-design effect",
        "",
        "The new seed-6 design is [(11,3), (9,7), (13,4)], so every method observes the reference target on its third initial callback.",
        "Neither historical initial designs nor any other new seed starts at the target.",
        "The sole new successes for BAM and uniform sampling both occur at seed 6 and therefore do not establish an improvement in their adaptive search.",
        f"Targets first reached after initialization change from {report['old_first_target_after_initial_runs']} runs to {report['new_first_target_after_initial_runs']} runs; this is an observation-stage breakdown, not a replacement success denominator.",
        "D-SDA seed 0 previously failed after three unaccepted initial points and now completes with an accepted initial observation, but it still misses the target.",
        "D-SDA seed 6 terminates naturally after eleven callbacks, while the other 49 new jobs consume thirteen callbacks.",
        "",
        "## Paired target outcomes",
        "",
        "| Method | Both succeed | New only | Old only | Neither succeeds |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in methods:
        lines.append(
            f"| {labels[row['method']]} | {row['both_success']} | {row['new_only']} | {row['old_only']} | {row['neither']} |"
        )
    rbf = next(r for r in methods if r["method"] == "rbfopt")
    rbf_cost = next(
        r for r in coordinates if r["method"] == "rbfopt" and r["point"] == [15, 8]
    )
    lines += [
        "",
        "All fifty paired seed records, including unchanged and worsened outcomes, are retained in paired_runs.csv.",
        "Ten seeds per method provide descriptive evidence and do not establish a general algorithm ranking.",
        "",
        "## Timing interpretation",
        "",
        "Reconstructed completion equals recorded search wall time minus measured table-lookup time plus historical same-attempt point costs charged on every callback.",
        "These times are not online optimizer-NLP measurements and do not measure new process solves.",
        "The reported time median includes all ten runs for each method, including the one historical D-SDA failure.",
        "Medians of individual timing components need not add to the median of reconstructed completion.",
        f"RBFOpt median measured search overhead decreases from {rbf['old_median_search_overhead_s']:.6f} s to {rbf['new_median_search_overhead_s']:.6f} s, while median charged point cost rises from {rbf['old_median_point_cost_s']:.3f} s to {rbf['new_median_point_cost_s']:.3f} s.",
        f"RBFOpt visits the unaccepted coordinate (15,8), whose historical cost is {rbf_cost['point_cost_s']:.6f} s, {rbf_cost['old_visits']} times before and {rbf_cost['new_visits']} times after, adding {rbf_cost['charged_cost_change_s']:.3f} s across its ten runs.",
        "This is a deterministic accounting explanation using unchanged point costs, not a newly measured solver slowdown.",
        "FMQA-SA likewise has lower median search overhead but a larger median charged point cost in the new coordinate paths.",
        f"The controller takes {report['controller_elapsed_before_pack_s']:.3f} s from creation to completion before final analysis and ZIP packaging, including {report['sequential_job_phase_s']:.3f} s in the sequential job phase.",
        f"The sum of measured new search wall times is {report['measured_search_wall_total_s']:.3f} s; these execution durations are distinct from reconstructed per-run completion costs.",
        f"The auxiliary journal contains {len(auxiliary)} Bonmin calls for RBFOpt surrogate models, totaling {report['auxiliary_call_wall_s']:.3f} s and already included in search overhead.",
        "BAM internal surrogate work remains inside search overhead and is not independently counted as process NLP work.",
        "",
        "## Domain, target and verification",
        "",
        "The input retains 29 accepted and 35 unaccepted coordinates, with the seventeen excluded historical coordinates all outside the logical domain.",
        "The accepted fraction of the candidate set rises from 29/81 to 29/64, while the nominal budget fraction changes from 16/81 to 13/64.",
        f"The reference remains (13,4), objective {target}, and the final-best absolute tolerance remains {report['reference_absolute_tolerance']:.12f}.",
        "No objective, acceptance record, target, archived provider revision, manuscript, Overleaf file or representative figure is changed.",
        "All 50 runtime, settings, CPU-2 affinity, single-thread and disabled-GPU records match the frozen plan, and worker intervals are sequential.",
        "All 1,202 returned member hashes pass, the 638 reproduction files match the delivered v3 package, and ten data/report outputs reproduce byte-for-byte.",
        "The local scientific figures are rendered from the verified profile coordinates and are separate follow-up artifacts.",
        "No original process NLP or optimizer is invoked by this analysis.",
        "The input archive, full callbacks, environments, paired comparison, coordinate cost attribution and replay sources are retained alongside this report.",
    ]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    write(
        output / "manifest.json",
        dict(
            source_base_revision=report["source_revision"],
            package_manifest_sha256=report["package_manifest_sha256"],
            analysis_source_sha256=sha(Path(__file__)),
            inputs=dict(
                plan_sha256=sha(package / "plan.json"),
                evaluation_table_sha256=sha(package / "inputs/column_64.csv"),
                replayed_runs_sha256=sha(replay / "runs.json"),
            ),
            original_process_nlp_calls=0,
            analysis_optimizer_calls=0,
            outputs_sha256={
                p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()
            },
        ),
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("run", "package", "replay", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(compare(args.run, args.package, args.replay, args.output), indent=2)
    )
