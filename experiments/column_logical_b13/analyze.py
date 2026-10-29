"""Replay preserved callbacks; do not invoke any optimizer or process solver."""

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

from common import (
    METHODS,
    csvwrite,
    events,
    measure,
    read,
    require,
    sha,
    verify_package,
    write,
)

ROOT = Path(__file__).resolve().parent


def selected(directory, job_id):
    sealed = sorted((directory / "jobs" / job_id).glob("attempt_*/terminal.json"))
    if not sealed:
        return None
    require(
        len(sealed) == 1, "Multiple sealed outcomes would introduce result selection"
    )
    path = sealed[0].parent
    for name, checksum in read(sealed[0])["files_sha256"].items():
        require(sha(path / name) == checksum, "Sealed job artifact changed")
    return path


def summarize(records):
    output = []
    for condition in ("81_B16", "64_B13"):
        for method in METHODS:
            group = [
                r
                for r in records
                if r["condition"] == condition and r["method"] == method
            ]
            require(
                len(group) == 10 and {r["seed"] for r in group} == set(range(10)),
                "Denominator changed",
            )
            finished = [
                r for r in group if r["status"] not in ("not_run", "interrupted")
            ]
            times = [
                r["completion_s"] for r in finished if r.get("completion_s") is not None
            ]
            overhead = [
                r["retained_search_s"]
                for r in finished
                if r.get("retained_search_s") is not None
            ]
            output.append(
                dict(
                    condition=condition,
                    method=method,
                    planned=10,
                    completed=len(finished),
                    failed=sum(r["category"] == "execution_failed" for r in finished),
                    pending=10 - len(finished),
                    target_hits=sum(r["target_hit"] for r in finished)
                    if finished
                    else None,
                    denominator=10,
                    target_rate=sum(r["target_hit"] for r in finished) / 10
                    if finished
                    else None,
                    total_callbacks=sum(r.get("callbacks", 0) for r in finished),
                    median_callbacks=statistics.median(r["callbacks"] for r in finished)
                    if finished
                    else None,
                    completion_time_records=len(times),
                    median_reconstructed_completion_s=statistics.median(times)
                    if times
                    else None,
                    median_search_overhead_s=statistics.median(overhead)
                    if overhead
                    else None,
                )
            )
    return output


def generate(directory, output, root=ROOT, plots=True):
    require(not output.exists(), "Analysis output must be a fresh directory")
    plan, costs = verify_package(root)
    point_hashes = {
        tuple(record["point"]): record["sha256"]
        for record in read(root / "provenance/point_attempts.json")
    }
    output.mkdir(parents=True)
    baseline = (
        read(root / "baseline/runs.json")
        if (root / "baseline/runs.json").exists()
        else None
    )
    require(baseline is not None, "Typed historical metrics are required")
    records = [{**r, "condition": "81_B16"} for r in baseline]
    callbacks, attempts, verified = [], [], []
    for job in plan:
        spec = job["spec"]
        path = selected(directory, spec["job_id"])
        common = dict(
            method=spec["method"],
            seed=spec["seed"],
            budget=13,
            domain_size=64,
            condition="64_B13",
            job_id=spec["job_id"],
        )
        all_attempts = sorted((directory / "jobs" / spec["job_id"]).glob("attempt_*"))
        attempts.extend(
            dict(
                job_id=spec["job_id"],
                path=str(p.relative_to(directory)),
                sealed=(p / "terminal.json").exists(),
                recorded_callbacks=len(events(p / "callbacks.jsonl")),
                rejected_over_budget_requests=len(
                    events(p / "callback_overrun_audit.jsonl")
                ),
            )
            for p in all_attempts
        )
        if path is None:
            records.append(
                {
                    **common,
                    "status": "interrupted" if all_attempts else "not_run",
                    "category": "not_run",
                    "target_hit": False,
                    "callbacks": 0,
                    "completion_s": None,
                    "retained_search_s": None,
                    "first_hit": None,
                }
            )
            continue
        require(read(path / "job.json") == job, "Executed job differs from frozen plan")
        result = read(path / "result.json")
        require(result["process_nlp_calls"] == 0, "Unexpected process NLP computation")
        ev = events(path / "callbacks.jsonl")
        for event in ev:
            point = tuple(event["point"])
            require(point in costs, "Callback outside new domain")
            if not event.get("budget_overrun"):
                require(
                    event["source_row"] == costs[point],
                    "Callback response/cost not from frozen input row",
                )
                require(
                    event["selected_attempt_nlp_s"]
                    == float(costs[point]["total_wall_s"]),
                    "Point cost changed",
                )
                if not event["accepted"]:
                    expected_kind = (
                        "nan"
                        if spec["method"] == "bam"
                        else "+inf"
                        if spec["method"] == "fmqa_sa"
                        else "finite"
                    )
                    require(
                        event["method_value_kind"] == expected_kind,
                        "Failure response policy changed",
                    )
                    if expected_kind == "finite":
                        require(
                            event["method_value"] == 1e6,
                            "Finite rejection response changed",
                        )
        metric, ledger = measure(spec, ev, result, costs, job["target"])
        if spec["method"] == "uniform_without_replacement":
            require(
                len({tuple(e["point"]) for e in ev}) == len(ev),
                "Uniform sampling repeated a point",
            )
        records.append({**common, **metric})
        callbacks.extend(
            {
                **common,
                **e,
                "evaluation_record_sha256": point_hashes.get(tuple(e["point"])),
            }
            for e in ledger
        )
        verified.append(
            dict(
                job_id=spec["job_id"],
                callbacks=len(ev),
                terminal_sha256=sha(path / "terminal.json"),
                status=result["status"],
                protocol_valid=not metric["protocol_error"],
                terminal_callback_target=bool(
                    ev and ev[-1]["index"] == 13 and metric["first_hit"] == 13
                ),
            )
        )
    require(
        len(records) == 100
        and sum(r["callbacks"] for r in records if r["condition"] == "64_B13") <= 650,
        "Plan/budget cap changed",
    )
    summaries = summarize(records)
    csvwrite(output / "runs.csv", records)
    write(output / "runs.json", records)
    csvwrite(output / "methods.csv", summaries)
    write(output / "methods.json", summaries)
    csvwrite(
        output / "callback_ledger.csv",
        callbacks,
        fields=None
        if callbacks
        else ["job_id", "index", "point", "accepted", "raw_objective", "point_cost_s"],
    )
    write(output / "attempt_inventory.json", attempts)
    profiles = []
    for condition, budget in [("81_B16", 16), ("64_B13", 13)]:
        for method in METHODS:
            group = [
                r
                for r in records
                if r["condition"] == condition and r["method"] == method
            ]
            completed = [
                r for r in group if r["status"] not in ("not_run", "interrupted")
            ]
            hits = [r for r in completed if r["target_hit"]]
            for axis in ("evaluations", "reconstructed_completion_s"):
                values = [
                    r["first_hit"] if axis == "evaluations" else r["completion_s"]
                    for r in hits
                ]
                times = [
                    r["completion_s"]
                    for r in completed
                    if r["completion_s"] is not None
                ]
                xs = (
                    list(range(budget + 1))
                    if axis == "evaluations"
                    else sorted({0.0, *values, max(times, default=0.0) * 1.1})
                )
                for x in xs:
                    profiles.append(
                        dict(
                            condition=condition,
                            method=method,
                            axis=axis,
                            x=x,
                            success_fraction=sum(v <= x for v in values) / 10
                            if completed
                            else None,
                            denominator=10,
                            completed=len(completed),
                            pending=10 - len(completed),
                        )
                    )
    csvwrite(output / "profiles.csv", profiles)
    write(output / "profiles.json", profiles)
    current = [r for r in records if r["condition"] == "64_B13"]
    counts = Counter(r["status"] for r in current)
    report = dict(
        planned_jobs=50,
        sealed_jobs=len(verified),
        pending_jobs=50 - len(verified),
        failed_jobs=sum(r["category"] == "execution_failed" for r in current),
        status_counts=dict(counts),
        actual_callbacks=sum(a["recorded_callbacks"] for a in attempts),
        sealed_run_callbacks=sum(r["callbacks"] for r in current),
        interrupted_attempt_callbacks=sum(
            a["recorded_callbacks"] for a in attempts if not a["sealed"]
        ),
        rejected_over_budget_requests=sum(
            a["rejected_over_budget_requests"] for a in attempts
        ),
        maximum_callbacks=650,
        original_process_nlp_calls=0,
        jobs=verified,
        frozen_package_sha256=sha(root / "manifest.json"),
        target_rule="abs(final_best_accepted-reference)<=1e-5*max(1,abs(reference)); failures remain in denominator 10",
        profile_semantics="Evaluation axis uses first observed target for successful runs; time axis uses reconstructed full-run completion, matching the publication.",
        timing="Search wall minus measured lookup time plus recorded point costs charged on every callback; not online optimizer-NLP time.",
        comparison="Domain and budget change together; no single-factor causal attribution.",
    )
    write(output / "verification.json", report)
    if plots:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            write(
                output / "plot_status.json",
                dict(
                    created=False,
                    reason="Matplotlib is unavailable; profiles.csv is complete and replayable.",
                ),
            )
        else:
            for axis, label in [
                ("evaluations", "Objective callbacks"),
                (
                    "reconstructed_completion_s",
                    "Reconstructed full-run completion time (s)",
                ),
            ]:
                fig, ax = plt.subplots(figsize=(8, 5))
                for index, method in enumerate(METHODS):
                    for condition, style in [("81_B16", "--"), ("64_B13", "-")]:
                        points = [
                            p
                            for p in profiles
                            if p["axis"] == axis
                            and p["method"] == method
                            and p["condition"] == condition
                            and p["success_fraction"] is not None
                        ]
                        if points:
                            ax.step(
                                [p["x"] for p in points],
                                [p["success_fraction"] for p in points],
                                where="post",
                                color=f"C{index}",
                                linestyle=style,
                                label=f"{method} {condition}",
                            )
                ax.set(
                    xlabel=label,
                    ylabel="Target-reaching fraction (denominator 10)",
                    ylim=(-0.02, 1.02),
                    title=f"Column: historical 81/B16 vs logical 64/B13 ({len(verified)}/50 new jobs sealed)",
                )
                ax.grid(alpha=0.2)
                ax.legend(fontsize=7, ncol=2)
                fig.tight_layout()
                for suffix in ("png", "pdf"):
                    fig.savefig(output / f"profile_{axis}.{suffix}", dpi=180)
                plt.close(fig)
            write(
                output / "plot_status.json",
                dict(created=True, unrun_new_curves_omitted=True),
            )
    lines = [
        "# Column logical-domain follow-up",
        "",
        f"{len(verified)} of 50 new jobs are sealed, {report['failed_jobs']} are execution failures, and {50 - len(verified)} remain uncompleted.",
        "No new original GDP NLP calculation is performed; the oracle reuses the 64 original IPOPT records, including all 35 unaccepted coordinates.",
        "The original 81-coordinate/B16 cohort and the new 64-coordinate/B13 cohort are distinct experiments.",
        "The new domain and budget change together, so their difference is not a causal estimate of either factor alone.",
        "The target, acceptance criteria, failure policies, archived algorithms and native stopping rules are preserved.",
        "Every method retains all ten seeds in its denominator, including algorithm failures.",
        "A target first observed at callback 13 is retained even when the callback raises the budget-stop exception.",
        "Reported completion times combine measured new search overhead with old same-attempt point costs and are not online optimizer-NLP measurements.",
        "The time profile uses the full-run reconstructed completion time for successful runs, matching the publication.",
        "",
        "| Condition | Method | Sealed | Failed | Hits / 10 | Median estimated completion (s) | Median search overhead (s) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    def number(value):
        return "not run" if value is None else f"{value:.6g}"

    for r in summaries:
        lines.append(
            f"| {r['condition']} | {r['method']} | {r['completed']} | {r['failed']} | {number(r['target_hits'])} | {number(r['median_reconstructed_completion_s'])} | {number(r['median_search_overhead_s'])} |"
        )
    lines += [
        "",
        "Pending runs are not reported as measured failures or zero-duration results.",
        "Partial-run rates and available-time medians are provisional until all ten jobs for that method are sealed.",
        "All baseline and new per-seed records are in runs.csv, with callback details in callback_ledger.csv.",
        "profiles.csv preserves the plotted coordinates, and verification.json records the checks and job counts.",
    ]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    write(
        output / "manifest.json",
        dict(
            package_sha256=sha(root / "manifest.json"),
            source_base_revision=read(root / "manifest.json")["source_base_revision"],
            analysis_source_sha256=sha(Path(__file__)),
            input_plan_sha256=sha(root / "plan.json"),
            input_table_sha256=sha(root / "inputs/column_64.csv"),
            original_process_nlp_calls=0,
            new_optimizer_calls_during_analysis=0,
            outputs_sha256={
                p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()
            },
        ),
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.run_dir, args.output), indent=2))
