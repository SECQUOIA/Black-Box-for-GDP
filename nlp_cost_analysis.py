"""Reconstruct traced black-box costs using measured fixed-integer NLP costs.

No optimization is run. Exact-model cost joins and a separately labelled
CSTR30 cost-transfer scenario are retained. The user specifies zero evaluation
cost for lookup-infeasible points and selected successful NLP evaluations only.
Earlier failed attempts are excluded. Unmeasured feasible costs remain missing.
"""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

from fmqa_benchmark.protocol import grid_size, problem
from gdp_models.domains import enumeration_plan


ROOT = Path(__file__).resolve().parent
METHODS = ("DSDA", "RBFOpt", "BAM 5.0.0", "FMQA-SA")
METHOD_NAMES = {"dsda": "DSDA", "rbfopt": "RBFOpt", "bam": "BAM 5.0.0", "fmqa_sa": "FMQA-SA"}
TOLERANCE = 1e-5


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No records for {path}")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def load_costs(directory, solver):
    directory = Path(directory)
    inventory = directory / "SHA256SUMS"
    for line in inventory.read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha(path) != digest:
            raise ValueError(f"Point-cost checksum mismatch: {name}")
    selected = [r for r in jsonl(directory / "points.jsonl") if r["solver"] == solver]
    costs = {(r["case"], r["cstr_size"], tuple(r["point"])): r for r in selected}
    if not selected or len(costs) != len(selected):
        raise ValueError("Missing or duplicate point costs")
    attempts = {a["attempt_id"]: a for a in jsonl(directory / "attempts.jsonl")}
    for row in selected:
        total = sum(attempts[a]["record"]["total_wall_s"] for a in row["attempt_ids"])
        if not math.isclose(total, row["all_attempts_total_wall_s"], rel_tol=1e-12):
            raise ValueError("Attempt-cost sum mismatch")
        if not 0 <= row["total_wall_s"] <= total or not math.isfinite(total):
            raise ValueError("Invalid point cost")
        selected_id = row["selected_attempt_id"]
        if selected_id not in row["attempt_ids"]:
            raise ValueError("Selected attempt missing from point history")
        selected_record = attempts[selected_id]["record"]
        if (selected_record["accepted"] != row["accepted"] or
                not math.isclose(selected_record["total_wall_s"], row["total_wall_s"], rel_tol=1e-12)):
            raise ValueError("Selected point cost differs from its source attempt")
    prep = read_json(directory / "dynamic_preparation.json")
    by_id = {p["record"]["preparation_id"]: p["record"] for p in prep}
    if len(by_id) != 1 or next(iter(by_id.values()))["included_in_point_total_wall_s"]:
        raise ValueError("Expected one separately measured Dynamic preparation")
    return costs, next(iter(by_id.values()))["total_preparation_wall_s"]


def normalize_run(spec, events, completion, source, host):
    spec = {**spec, "grid_size": grid_size(spec["csv_name"])}
    oracle = problem(spec)
    if not events or not math.isfinite(completion) or completion < events[-1]["completed_elapsed_s"]:
        raise ValueError("Invalid run clock")
    previous = 0.0
    for i, event in enumerate(events, 1):
        elapsed, duration = event["completed_elapsed_s"], event["objective_wall_s"]
        if event["evaluation_index"] != i or duration < 0 or elapsed < previous or duration > elapsed - previous + 1e-9:
            raise ValueError("Invalid evaluation order/clock")
        value = oracle["objective"](event["point"])
        recorded = event.get("raw_value", event.get("value"))
        if math.isfinite(value) and (recorded is None or not math.isclose(value, recorded, rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError("Trace objective differs from the original lookup")
        previous = elapsed
    return {"spec": spec, "events": events, "completion": completion,
            "source": str(source), "overhead_host": host, "target": oracle["target"]}


def load_traces(summary_path, fmqa_path):
    from trace_analysis import read_completed_runs
    from fmqa_compare import audit_fmqa, result_directory
    runs, sources = [], []
    inventory = read_json(summary_path)
    for item in inventory["inputs"]:
        path = Path(item["path"])
        # Permit moving the repository while retaining exact recorded files.
        if not path.exists() and "results" in path.parts:
            path = ROOT.joinpath(*path.parts[path.parts.index("results"):])
        if sha(path) != item["sha256"] or sha(path.with_suffix(".manifest.json")) != item["manifest_sha256"]:
            raise ValueError("Trace inventory checksum mismatch")
        manifest = read_json(path.with_suffix(".manifest.json"))
        for (key, record, events), artifact in zip(read_completed_runs(path), manifest["evaluation_traces"]):
            entries = jsonl(path.parent / artifact["path"])
            runs.append(normalize_run(key, events, entries[-1]["runner_elapsed_s"], path, "macOS trace rerun"))
        sources.append({"path": str(path), "sha256": sha(path)})
    with result_directory(fmqa_path) as directory:
        manifest = audit_fmqa(directory)
        for spec in manifest["plan"]:
            job = directory / "jobs" / spec["job_id"]
            outcome = read_json(job / "result.json")
            runs.append(normalize_run(spec, jsonl(job / "evaluations.jsonl"), outcome["wall_time_s"],
                                      str(fmqa_path) + ":" + spec["job_id"], manifest["runtime"]["host"]))
    sources.append({"path": str(fmqa_path), "sha256": sha(fmqa_path), "method": "FMQA-SA",
                    "created_utc": manifest.get("created_utc"), "cpu": manifest.get("cpu"),
                    "cpu_affinity": manifest["runtime"].get("cpu_affinity"),
                    "host": manifest["runtime"]["host"]})
    keys = [(r["spec"]["csv_name"], r["spec"]["seed"], r["spec"]["max_evaluations"], r["spec"]["method"]) for r in runs]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate trace run")
    paired = Counter(k[:3] for k in keys)
    if any(n != len(METHODS) for n in paired.values()):
        raise ValueError("Incomplete method pairing")
    return runs, sources


def target_hit(value, target):
    return value is not None and math.isfinite(value) and abs(value - target) <= TOLERANCE * max(1, abs(target))


def reconstruct(run, costs, preparation, *, cstr_policy="exact", cache=False):
    """Charge each actual callback by default; repeated callbacks are not cache hits.

    Lookup-infeasible evaluations are free by explicit user assumption.
    Only the selected successful evaluation is charged at feasible points;
    earlier failed attempts are excluded. Missing successful measurements stay
    missing, rather than being treated as zero. strict_* require the exact size.
    Neither path replaces objectives or changes the original search path.
    """
    spec, events = run["spec"], run["events"]
    case, size = spec["case_name"], spec["grid_size"]
    measured_size = 30 if case == "cstr" and cstr_policy == "cstr30_transfer" else size
    plan = enumeration_plan(case, cstr_size=size or 30)
    logical = set(map(tuple, plan["points"]))
    box = set(map(tuple, enumeration_plan(case, cstr_size=size or 30, domain="box")["points"]))
    oracle = problem(spec)["objective"]
    identity = {"case_name": case, "grid_size": size, "csv_name": spec["csv_name"],
                "method": METHOD_NAMES[spec["method"]], "seed": spec["seed"],
                "n_starts": spec["n_starts"], "max_evals": spec["max_evaluations"],
                "cstr_cost_policy": cstr_policy, "cache_policy": "unique_point_cache" if cache else "each_callback",
                "point_cost_policy": "selected_successful_evaluation_only",
                "overhead_host": run["overhead_host"]}
    setup = preparation if case == "dynamic" else 0.0
    counters = Counter()
    cumulative_lookup = measured_total = screen_total = waived = 0.0
    first_hit = first_measured_hit = None
    lookup_best = measured_best = None
    seen, ledger = set(), []
    for event in events:
        point = tuple(event["point"])
        row = costs.get((case, measured_size, point))
        value = oracle(point)
        feasible = math.isfinite(value)
        repeated = point in seen
        cache_hit = cache and repeated
        seen.add(point)
        counters["repeated_calls"] += repeated
        cumulative_lookup += event["objective_wall_s"]
        search = event["completed_elapsed_s"] - cumulative_lookup
        if search < -1e-9:
            raise ValueError("Objective time exceeds run clock")
        search = max(search, 0.0)
        known = row is not None
        logic_reject = point in box and point not in logical
        if logic_reject and feasible:
            raise ValueError("GDP logic contradicts a finite lookup value")
        if not feasible:
            status, cost, chosen = "infeasible_zero_assumption", 0.0, 0.0
            counters["infeasible_zero_calls"] += 1
            if known:
                waived += row["all_attempts_total_wall_s"]
        elif cache_hit:
            status, cost, chosen = "cache_lookup_proxy", event["objective_wall_s"], 0.0
            screen_total += cost
            counters["cache_hit_calls"] += 1
        elif known and row["accepted"]:
            status = "cstr30_transferred_measurement" if case == "cstr" and size != measured_size else "exact_model_measurement"
            cost = chosen = row["total_wall_s"]
            measured_total += cost
            counters["measured_calls"] += 1
            counters["cstr30_transferred_calls"] += status == "cstr30_transferred_measurement"
        else:
            status = "missing_successful_point_measurement" if known else "unmeasured_logical_point"
            cost = chosen = None
            counters["unmeasured_calls"] += 1
            counters["unsuccessful_point_calls"] += known
        if feasible:
            lookup_best = value if lookup_best is None else min(lookup_best, value)
        accepted_value = row["objective"] if known and row["accepted"] else None
        if accepted_value is not None:
            measured_best = accepted_value if measured_best is None else min(measured_best, accepted_value)
        agrees = (target_hit(accepted_value, value) if feasible else not row["accepted"]) if known else None
        counters["objective_disagreement_calls"] += agrees is False
        subtotal = setup + search + measured_total + screen_total
        scenario_time = subtotal if not counters["unmeasured_calls"] else None
        strict_time = scenario_time if not counters["cstr30_transferred_calls"] else None
        item = {**identity, "evaluation_index": event["evaluation_index"], "phase": event["phase"],
                "point": list(point), "repeated_point": repeated, "cost_status": status,
                "cost_model_cstr_size": measured_size, "recorded_lookup_wall_s": event["objective_wall_s"],
                "measured_point_all_attempts_s": row["all_attempts_total_wall_s"] if known else None,
                "charged_cost_s": cost, "selected_attempt_cost_s": chosen,
                "charged_successful_attempt_id": row["selected_attempt_id"] if feasible and known and row["accepted"] and not cache_hit else None,
                "attempt_ids": row["attempt_ids"] if known else [],
                "lookup_objective": value if feasible else None,
                "measured_nlp_objective": accepted_value, "objective_agrees": agrees,
                "lookup_incumbent": lookup_best, "measured_path_incumbent": measured_best,
                "search_prefix_s": search, "nlp_prefix_s": measured_total,
                "screen_cache_proxy_prefix_s": screen_total, "preparation_s": setup,
                "known_cost_subtotal_s": subtotal, "scenario_elapsed_s": scenario_time,
                "strict_elapsed_s": strict_time, "lookup_elapsed_s": event["completed_elapsed_s"]}
        ledger.append(item)
        if first_hit is None and target_hit(lookup_best, run["target"]):
            first_hit = {"event": item}
        if first_measured_hit is None and target_hit(measured_best, run["target"]):
            first_measured_hit = item
    search = run["completion"] - cumulative_lookup
    if search < ledger[-1]["search_prefix_s"] - 1e-9:
        raise ValueError("Completion before final objective callback")
    total = setup + search + measured_total + screen_total
    scenario_total = total if not counters["unmeasured_calls"] else None
    strict_total = scenario_total if not counters["cstr30_transferred_calls"] else None
    fh = first_hit["event"] if first_hit else {}
    summary = {**identity, "target_value": run["target"], "total_evals": len(events), "unique_points": len(seen),
               "lookup_best_value": lookup_best, "lookup_solved": target_hit(lookup_best, run["target"]),
               "measured_path_best_value": measured_best, "measured_path_target_hit": target_hit(measured_best, run["target"]),
               "lookup_completion_s": run["completion"], "search_overhead_s": search,
               "nlp_selected_attempts_s": measured_total, "screen_cache_proxy_s": screen_total,
               "preparation_s": setup, "known_cost_subtotal_s": total,
               "scenario_total_s": scenario_total, "strict_total_s": strict_total,
               "first_hit_evaluation": fh.get("evaluation_index"),
               "lookup_first_hit_s": fh.get("lookup_elapsed_s"),
               "scenario_first_hit_s": fh.get("scenario_elapsed_s"),
               "strict_first_hit_s": fh.get("strict_elapsed_s"),
               "waived_measured_infeasible_cost_s": waived,
               "measured_path_first_hit_s": first_measured_hit.get("scenario_elapsed_s") if first_measured_hit else None,
               "source": run["source"],
               **{name: counters[name] for name in ("measured_calls", "repeated_calls", "cache_hit_calls",
                   "cstr30_transferred_calls", "unsuccessful_point_calls",
                   "infeasible_zero_calls", "unmeasured_calls", "objective_disagreement_calls")}}
    return summary, ledger


def performance_ratios(rows, time_field):
    """Keep all-failed instances in the denominator and reject unpaired data."""
    groups = {}
    for row in rows:
        key = (row["csv_name"], row["seed"], row["n_starts"], row["max_evals"])
        groups.setdefault(key, []).append(row)
    output = []
    for key, group in groups.items():
        if Counter(r["method"] for r in group) != Counter(METHODS):
            raise ValueError(f"Unpaired performance profile: {key}")
        if any(r["scenario_total_s"] is None for r in group):
            raise ValueError("Unmeasured costs cannot enter a complete time profile")
        values = [r[time_field] if r["lookup_solved"] and r[time_field] is not None else math.inf for r in group]
        best = min(values)
        for row, value in zip(group, values):
            output.append({**row, "profile_time_field": time_field,
                           "time_ratio": value / best if math.isfinite(value) else None})
    return output


def panel_label(row):
    case = row["case_name"]
    name = {"column": "Column", "small_batch": "Small Batch", "dynamic": "Dynamic", "cstr": "CSTR"}[case]
    if case == "cstr":
        name += f" {int(row['grid_size'])}"
        if row["grid_size"] != 30:
            name += " (NT=30 cost proxy)"
    return f"{name}, B={row['max_evals']}"


def figures(output, native, transferred):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    import numpy as np
    import pandas as pd
    colors = dict(zip(METHODS, ("#1682cf", "#ee761c", "#209c49", "#9254b5")))
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.dpi": 180, "pdf.fonttype": 42})
    caveat = ("Reconstructed: Mac search clocks for DSDA/RBFOpt/BAM; Dantzig clocks for FMQA and NLPs.\n"
              "Infeasible evaluations: 0 s (assumption). Successful NLP evaluation costs only; original lookup targets retained.")

    def panels(rows, filename, field, absolute=False, proxy=False):
        data = performance_ratios(rows, field)
        groups = {}
        for row in data:
            groups.setdefault((row["case_name"], row["grid_size"] or 0, row["max_evals"]), []).append(row)
        groups = sorted(groups.items(), key=lambda item: (("column", "cstr", "small_batch", "dynamic").index(item[0][0]), item[0][1:]))
        cols = 3
        fig, axes = plt.subplots(math.ceil(len(groups) / cols), cols,
                                 figsize=(14, 3.25 * math.ceil(len(groups) / cols)), squeeze=False)
        for ax, (_, group) in zip(axes.flat, groups):
            finite = [r[field] if absolute else r["time_ratio"] for r in group if r["lookup_solved"] and r[field] is not None]
            hi = max(finite, default=1.0) * 1.15
            lo = min(finite, default=1.0) / 1.2 if absolute else 1.0
            hi = max(hi, lo * 1.1)
            for method in METHODS:
                selected = [r for r in group if r["method"] == method]
                values = sorted((r[field] if absolute else r["time_ratio"]) for r in selected
                                if r["lookup_solved"] and r[field] is not None)
                x = [lo, *values, hi]
                y = [0, *[i / len(selected) for i in range(1, len(values) + 1)], len(values) / len(selected)]
                ax.step(x, y, where="post", color=colors[method], label=method, linewidth=1.8)
            ax.set(xscale="log", xlim=(lo, hi), ylim=(0, 1.04),
                   title=panel_label(group[0]) + f"\n{len(group) // 4} paired starts",
                   xlabel="Reconstructed first-hit time (s)" if absolute else "Time / fastest successful method",
                   ylabel="Fraction of all runs reaching target")
            ticks = np.geomspace(lo, hi / 1.05, 4) if absolute else [v for v in (1, 1.5, 2, 3, 5, 10, 20, 50, 100, 1000) if lo <= v <= hi]
            if not absolute and len(ticks) > 5:
                ticks = [v for v in (1, 2, 5, 10, 50, 100, 1000) if lo <= v <= hi]
            ax.xaxis.set_major_locator(FixedLocator(ticks))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.3g}"))
            ax.xaxis.set_minor_locator(NullLocator())
            ax.grid(alpha=.22)
        for ax in list(axes.flat)[len(groups):]:
            ax.set_visible(False)
        title = "Success versus reconstructed time" if absolute else ("NLP-inclusive first-hit performance profiles" if "first_hit" in field else "NLP-inclusive completion-time performance profiles")
        if proxy:
            title += " — CSTR30 cost-transfer scenario"
        fig.suptitle(title, fontsize=17, y=.993)
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .97), ncol=4, frameon=False)
        fig.text(.5, .013, caveat, ha="center", fontsize=9)
        fig.tight_layout(rect=(0, .065, 1, .93))
        for extension in ("png", "pdf"):
            fig.savefig(output / f"{filename}.{extension}")
        plt.close(fig)
        return data

    ratios = panels(native, "time_performance_profiles", "scenario_first_hit_s")
    write_csv(output / "time_profile_runs.csv", ratios)
    panels(native, "completion_time_profiles", "scenario_total_s")
    panels(native, "success_vs_time", "scenario_first_hit_s", absolute=True)
    panels(transferred, "cstr30_transfer_time_profiles", "scenario_first_hit_s", proxy=True)
    # Exact-model cases; select the largest recorded Dynamic budget.
    chosen = [r for r in native if r["case_name"] != "dynamic" or r["max_evals"] == 50]
    frame = pd.DataFrame(chosen)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, case in zip(axes.flat, ("column", "cstr", "small_batch", "dynamic")):
        group = frame[frame.case_name == case]
        means = group.groupby("method").mean(numeric_only=True).reindex(METHODS)
        bottom = np.zeros(4)
        for field, label, color in (("search_overhead_s", "Search overhead", "#537896"),
                                    ("nlp_selected_attempts_s", "Successful NLP evaluations", "#80b1d3"),
                                    ("preparation_s", "One-time Dynamic preparation", "#4c9f8a")):
            vals = means[field].to_numpy()
            ax.bar(range(4), vals, bottom=bottom, label=label, color=color)
            bottom += vals
        for i, total in enumerate(bottom):
            ax.text(i, total, f"{total:.2f}s", ha="center", va="bottom", fontsize=9)
        ax.set(xticks=range(4), xticklabels=METHODS, ylabel="Mean reconstructed completion time (s)",
               title=panel_label(group.iloc[0].to_dict()), ylim=(0, max(bottom) * 1.18))
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Where the time goes — all runs, including target failures", fontsize=16)
    fig.legend(*axes.flat[0].get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(.5, .94), ncol=2, frameon=False)
    fig.text(.5, .016, caveat, ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, .86))
    for ext in ("png", "pdf"):
        fig.savefig(output / f"cost_breakdown.{ext}")
    plt.close(fig)


def report(output, rows, events, sources, costs_dir, solver):
    import pandas as pd
    frame = pd.DataFrame(rows)
    native = frame[(frame.cstr_cost_policy == "exact") &
                   ((frame.case_name != "cstr") | (frame.grid_size == 30)) & frame.scenario_total_s.notna()]
    keys = ["case_name", "grid_size", "max_evals", "method"]
    summary = native.groupby(keys, dropna=False, sort=False).agg(
        runs=("seed", "size"), solved=("lookup_solved", "sum"),
        measured_path_success=("measured_path_target_hit", "sum"),
        median_completion_s=("scenario_total_s", "median"),
        median_first_hit_s=("scenario_first_hit_s", "median"),
        mean_search_s=("search_overhead_s", "mean"), mean_nlp_s=("nlp_selected_attempts_s", "mean"),
        infeasible_zero_calls=("infeasible_zero_calls", "sum"),
        objective_disagreements=("objective_disagreement_calls", "sum")).reset_index()
    summary["_case_order"] = summary.case_name.map({"column": 0, "cstr": 1, "small_batch": 2, "dynamic": 3})
    summary["_method_order"] = summary.method.map(dict(zip(METHODS, range(4))))
    summary = summary.sort_values(["_case_order", "grid_size", "max_evals", "_method_order"]).drop(columns=["_case_order", "_method_order"])
    summary.to_csv(output / "case_summary.csv", index=False)
    missing = {}
    for event in events:
        if event["cstr_cost_policy"] != "exact" or event["cost_status"] not in {"unmeasured_logical_point", "missing_successful_point_measurement"}:
            continue
        key = (event["case_name"], event["grid_size"], tuple(event["point"]), event["cost_status"])
        record = missing.setdefault(key, {"case_name": key[0], "grid_size": key[1], "point": list(key[2]),
                                         "reason": key[3], "callback_count": 0})
        record["callback_count"] += 1
    write_csv(output / "unmeasured_coordinates.csv", list(missing.values()))
    unique_runs = frame[frame.cstr_cost_policy == "exact"]
    overview = {"traced_runs": len(unique_runs), "objective_callbacks": int(unique_runs.total_evals.sum()),
                "exact_model_scenario_runs": len(native),
                "exact_model_runs_with_all_required_costs": int(unique_runs.strict_total_s.notna().sum()),
                "exact_model_unmeasured_runs": int(unique_runs.scenario_total_s.isna().sum()),
                "infeasible_zero_calls": int(unique_runs.infeasible_zero_calls.sum()),
                "measured_cost_directory": str(costs_dir), "solver": solver, "sources": sources,
                "cost_inventory_sha256": sha(Path(costs_dir) / "SHA256SUMS"),
                "analysis_source_sha256": sha(__file__),
                "assumptions": ["each actual callback charged; no implicit cross-run cache",
                    "only the selected successful NLP evaluation is charged; earlier failed attempts excluded by user instruction",
                    "Dynamic shared preparation added once per run",
                    "user-specified zero evaluation cost for all lookup-infeasible points; recorded costs remain in the ledger",
                    "CSTR30 transfer is separate from the exact-model analysis",
                    "optimizer clocks belong to the same recorded trace, not old Dantzig runs",
                    "lookup success preserved; measured-objective agreement and fixed-path target hits reported separately",
                    "no online GDP execution or quantum hardware claim"]}
    write_json(output / "manifest.json", overview)
    lines = ["# NLP-inclusive cost reconstruction", "",
             f"Audited {overview['traced_runs']} complete coordinate traces and {overview['objective_callbacks']:,} callbacks. "
             "No optimizer or NLP was rerun. Original data were not modified.", "",
             "## Calculation", "",
             "`estimated total = same-trace search clock - recorded lookup costs + charged point costs + once-per-run Dynamic preparation`", "",
             "Each lookup-feasible callback pays only the selected successful evaluation's `total_wall_s` (`accepted=true`); lookup-infeasible callbacks cost zero. "
             "For the seven repaired CSTR30 points, only the successful individual run is charged. Earlier failed runs are excluded by user instruction. "
             "The original all-attempt history remains available for provenance and does not enter reconstructed totals. "
             "Point cost already includes preparation, preprocessing, solver interface and validation: these overlapping timers are not added again. "
             "Dynamic preparation (0.1090063113 s) is charged once per run. Initial evaluations count. "
             "The separate cache sensitivity charges each coordinate's NLP only once, and is an assumption, not a claim about original solver caching.", "",
             "## Exact-model results", "",
             f"{len(native)} runs cover Column, CSTR30, Small Batch and six Dynamic budgets. "
             f"All {overview['exact_model_runs_with_all_required_costs']} of these runs have measurements for every feasible coordinate, "
             "with infeasible evaluations assigned zero by user instruction.", "",
             "| Case / budget | Method | Lookup target hits | Measured-NLP target hits on fixed path | Median first hit, successful (s) | Median completion, all (s) |",
             "|---|---|---:|---:|---:|---:|"]
    for row in summary.to_dict("records"):
        label = row["case_name"] + (f"{int(row['grid_size'])}" if row["case_name"] == "cstr" else "")
        first = row["median_first_hit_s"]
        first_text = f"{first:.3f}" if math.isfinite(first) else "—"
        lines.append(f"| {label}, B={row['max_evals']} | {row['method']} | {row['solved']}/{row['runs']} | "
                     f"{row['measured_path_success']}/{row['runs']} | {first_text} | {row['median_completion_s']:.3f} |")
    lines += ["", "Success-only medians must be read with their success counts. No successful run is silently substituted for a failure. "
              "Performance-profile denominators contain all paired starts, including all-method failures. Target tolerance is `1e-5 * max(1, abs(target))`.", "",
              "## Declared approximations", "",
              "1. **Infeasible points cost zero.** This is the user's explicit accounting assumption, applied to points marked infeasible "
              "by the original benchmark oracle, including logic/FBBT-infeasible points. Their original measured cost, if available, "
              "is preserved but not charged. This does not mean infeasibility detection was measured to be free. "
              "Failed IPOPT attempts are excluded. A feasible point without a successful measurement stays missing, not zero-cost.", "",
              "2. **CSTR5–25.** The published cost table intentionally retains only CSTR30. The exact-model outputs leave those missing costs blank. "
              "`cstr30_transfer_time_profiles` is a separate scenario using the measured CSTR30 costs at the same coordinates for smaller search domains. "
              "It does not claim measured runtime of the smaller GDP models, and must not be used as a same-model runtime comparison against their full GDP solvers.", "",
              "3. **Clock provenance.** DSDA/RBFOpt/BAM paths and overhead come from the complete Mac trace reruns, not recovered original Dantzig paths. "
              "Some Mac jobs overlapped. FMQA paths/overhead and all NLP point costs come from Dantzig. "
              "The FMQA archive's CPU, physical-core topology and run timestamp are recorded in `manifest.json`; "
              "CPU affinity does not establish exclusive server access. "
              "These are component-based timing estimates with heterogeneous clock provenance, not controlled measured end-to-end speedups.", "",
              "The complete Mac reruns can also have different search outcomes from the old Dantzig runs despite identical initial points. "
              "For example, Column RBFOpt succeeds in 3/9 of the traced reruns versus 4/9 in the older server archive. "
              "The new figures use the actual traced outcomes; they do not silently attach new paths to old success records.", "",
              "4. **Objective values.** The existing lookup trajectory is preserved. IPOPT is a local solver and some CSTR point objectives differ. "
              "Per-point discrepancies and a separate measured-NLP incumbent along the *fixed original path* are included. "
              "That second sequence does not simulate how the optimizer would react to changed observations. "
              "Neither sequence certifies a global optimum.", "",
              "5. **GDP baselines.** `gdp_baseline_comparison.csv` retains measured full-GDP completion times separately, plus one shared template preparation cost. "
              "Missing saved solutions remain missing. These are completion records, not first-hit records, and are not merged into first-hit performance profiles. "
              "The previously identified CSTR initialization, lost-incumbent, Column bound and CPU-overlap qualifications still apply.", "",
              "## Figures and data", "",
              "- `time_performance_profiles.{png,pdf}`: exact-model cases, estimated first-hit time to the original lookup target.",
              "- `completion_time_profiles.{png,pdf}`: full completion time, using the same reconstructed costs.",
              "- `success_vs_time.{png,pdf}`: absolute estimated seconds versus target-hit fraction.",
              "- `cost_breakdown.{png,pdf}`: mean completion cost components; all runs included.",
              "- `completion_vs_quality.{png,pdf,csv}`: measured full-GDP completion versus reconstructed black-box completion, with distinct markers.",
              "- `cstr30_transfer_time_profiles.{png,pdf}`: all original conditions, with smaller-CSTR proxies explicitly labelled.",
              "- `run_costs.csv`, `evaluation_costs.csv`: every total and coordinate join, including provenance and missing values.",
              "- `case_summary.csv`, `time_profile_runs.csv`: summary and performance ratios.",
              "- `cache_sensitivity.csv`: optional within-run memoization assumption.",
              "- `unmeasured_coordinates.csv`: explicit outstanding measurements; source data are preserved.", "",
              "## Reproduce", "",
              "From the repository root, with the original trace bundle, FMQA archive and GDP results at the manifest paths:", "",
              "```bash", "MPLCONFIGDIR=/tmp/nlp-cost-matplotlib python nlp_cost_analysis.py --output results/new_nlp_cost_comparison", "```", "",
              "No shell runner, server execution, Git commit or push is needed for this analysis.", ""]
    (output / "README.md").write_text("\n".join(lines))
    return overview


def baseline_record(row, target):
    objective = row.get("objective") if row.get("has_feasible_solution") else None
    record = {k: row.get(k) for k in ("case", "cstr_size", "instance_id", "method", "status", "termination", "has_feasible_solution",
                                       "objective", "method_wall_s", "template_wall_s", "worker_wall_s", "global_optimality_certified")}
    # Killed workers have no returned method timer; preserve the watchdog timer.
    duration = row.get("method_wall_s", row.get("worker_wall_s"))
    if duration is None or not math.isfinite(duration) or duration < 0:
        raise ValueError("Invalid GDP completion clock")
    record.update({"target_value": target, "target_hit": target_hit(objective, target),
                   "measured_total_with_preparation_s": duration + row.get("template_wall_s", 0),
                   "clock_source": "method_wall_s" if "method_wall_s" in row else "worker_wall_s_watchdog",
                   "time_kind": "measured_completion_not_first_hit"})
    return record


def baseline_comparison(directory, output, trace_runs):
    summary = read_json(Path(directory) / "summary.json")
    records = []
    targets = {(r["spec"]["case_name"], r["spec"]["grid_size"]): r["target"] for r in trace_runs}
    for row in summary["results"]:
        target = targets[(row["case"], row["cstr_size"])]
        records.append(baseline_record(row, target))
    write_csv(output / "gdp_baseline_comparison.csv", records)
    return records


def completion_quality_figure(output, native, baselines):
    """Show measured GDP completion separately from reconstructed DFO completion."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    colors = dict(zip(METHODS, ("#1682cf", "#ee761c", "#209c49", "#9254b5")))
    baseline_styles = {"ric": ("RIC + IPOPT", "#0d4b70"), "gloa": ("GLOA + IPOPT", "#846229"),
                       "bigm": ("Big-M + BARON", "#cd3c50"), "hull": ("Hull + BARON", "#242424")}
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    comparison_rows = []
    for ax, case in zip(axes.flat, ("column", "cstr", "small_batch", "dynamic")):
        subset = [r for r in native if r["case_name"] == case and (case != "dynamic" or r["max_evals"] == 50)]
        plotted_gaps = []
        for row in subset:
            value = row["lookup_best_value"]
            if value is None:
                continue
            gap = max(0.0, (value - row["target_value"]) / max(1, abs(row["target_value"])))
            plotted_gaps.append(gap)
            ax.scatter(row["scenario_total_s"], gap, color=colors[row["method"]], marker="o", s=38, alpha=.65)
            comparison_rows.append({"case_name": case, "method": row["method"], "seed": row["seed"],
                                    "time_s": row["scenario_total_s"], "relative_gap": gap,
                                    "time_kind": "reconstructed_completion", "objective_kind": "original_lookup_incumbent"})
        missing = []
        for row in baselines:
            if row["case"] != case or (case == "cstr" and row["cstr_size"] != 30):
                continue
            name, color = baseline_styles[row["method"]]
            if not row["has_feasible_solution"] or row["objective"] is None:
                missing.append(name)
                continue
            gap = max(0.0, (row["objective"] - row["target_value"]) / max(1, abs(row["target_value"])))
            plotted_gaps.append(gap)
            ax.scatter(row["measured_total_with_preparation_s"], gap, marker="D", s=90, color=color,
                       edgecolors="white", linewidths=.7, zorder=5)
            comparison_rows.append({"case_name": case, "method": name, "seed": None,
                                    "time_s": row["measured_total_with_preparation_s"], "relative_gap": gap,
                                    "time_kind": "measured_completion", "objective_kind": "validated_saved_gdp_solution"})
        title = panel_label(subset[0])
        if missing:
            title += "\nBARON Big-M/Hull: no saved vector at the 30-min limit"
        ax.axhline(TOLERANCE, color="#777777", linestyle=":", linewidth=1)
        ax.set(xscale="log", yscale="symlog", title=title,
               xlabel="Completion time with preparation (s)", ylabel="Relative objective gap (lower is better)")
        ax.set_yscale("symlog", linthresh=1e-5)
        ax.set_ylim(bottom=-2e-6, top=max(2e-5, max(plotted_gaps) * 1.4))
        ax.grid(alpha=.2)
    handles = [Line2D([], [], color=colors[m], marker="o", linestyle="", label=m) for m in METHODS]
    handles += [Line2D([], [], color=c, marker="D", linestyle="", label=m) for m, c in baseline_styles.values()]
    fig.suptitle("Completion time and solution quality — exploratory comparison", fontsize=16)
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .96), ncol=4, frameon=False)
    fig.text(.5, .018,
             "Circles: reconstructed DFO times, original lookup incumbents. Diamonds: measured full-GDP completion and saved solutions.\n"
             "Successful NLP evaluation costs only; infeasible queries cost 0 s. Mixed clocks; GDP CPU overlap remains. No speedup claim.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, .87))
    for ext in ("png", "pdf"):
        fig.savefig(output / f"completion_vs_quality.{ext}")
    plt.close(fig)
    write_csv(output / "completion_vs_quality.csv", comparison_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, default=ROOT / "results/process_evaluation_traces_20260917/summary.json")
    parser.add_argument("--fmqa", type=Path, default=ROOT / "results/archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip")
    parser.add_argument("--costs", type=Path, default=ROOT / "results/gdp_point_timings_20260922")
    parser.add_argument("--solver", choices=("gams_ipopt", "ipopth", "conopt"), default="gams_ipopt")
    parser.add_argument("--gdp-results", type=Path, default=ROOT / "results/dantzig_review/completed_benchmarks_20260923/dantzig_gdp_compare_20260922_181805_4u7k1d0n")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a new output directory; existing analyses are not overwritten")
    costs, preparation = load_costs(args.costs, args.solver)
    runs, sources = load_traces(args.traces, args.fmqa)
    summaries, ledger, cache = [], [], []
    for policy in ("exact", "cstr30_transfer"):
        for run in runs:
            row, events = reconstruct(run, costs, preparation, cstr_policy=policy)
            summaries.append(row)
            ledger.extend(events)
            cached, _ = reconstruct(run, costs, preparation, cstr_policy=policy, cache=True)
            cache.append(cached)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "run_costs.csv", summaries)
    write_csv(args.output / "evaluation_costs.csv", ledger)
    write_csv(args.output / "cache_sensitivity.csv", cache)
    native = [r for r in summaries if r["cstr_cost_policy"] == "exact" and (r["case_name"] != "cstr" or r["grid_size"] == 30)]
    transferred = [r for r in summaries if r["cstr_cost_policy"] == "cstr30_transfer"]
    figures(args.output, native, transferred)
    baselines = baseline_comparison(args.gdp_results, args.output, runs)
    completion_quality_figure(args.output, native, baselines)
    sources.append({"path": str(args.gdp_results / "summary.json"), "sha256": sha(args.gdp_results / "summary.json")})
    overview = report(args.output, summaries, ledger, sources, args.costs, args.solver)
    print(json.dumps({k: v for k, v in overview.items() if k not in {"sources", "assumptions"}}, indent=2))


if __name__ == "__main__":
    main()
