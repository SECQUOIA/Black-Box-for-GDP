"""Plot an all-outcome fixed-path cost estimate from verified Dantzig records.

No optimizers run. Estimated time = recorded DFO time - recorded lookup time
+ separately measured point costs + one reference Dynamic preparation per run.
"""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/dfo_trace_nlp_20261002/analysis"
OUTPUT = ROOT / "results/dfo_trace_nlp_20261002/figures"
FOLLOWUP = ROOT / "results/process_followup_20261012"
FULL_BATCH = ROOT / "results/small_batch_full_domain_20261012"
METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa")
LABELS = ("DSDA", "RBFOpt", "BAM 5.0.0", "FMQA-SA")
PANELS = (("column", "", 16, "Column"), ("cstr", "30", 43, "CSTR 30"),
          ("small_batch", "", 10, "Small Batch"), ("dynamic", "", 50, "Dynamic"))
COMPONENTS = (
    ("search_overhead_s", "Search overhead (Dantzig)", "#537b99"),
    ("accepted_nlp_s", "Solution found (including retries)", "#80b1d3"),
    ("unaccepted_nlp_s", "No accepted solution (all checks/attempts)", "#d37464"),
    ("dynamic_preparation_s", "One-time Dynamic preparation", "#48a18c"),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def followup_runs():
    """Read the audited supplement; retain each method's original timer scope."""
    audit = json.loads((FOLLOWUP / "audit.json").read_text())
    for name, digest in audit["files_sha256"].items():
        if sha(FOLLOWUP / name) != digest:
            raise ValueError(f"Follow-up checksum mismatch: {name}")
    if sha(ROOT / audit["archive"]) != audit["archive_sha256"]:
        raise ValueError("Follow-up archive checksum mismatch")
    cost = json.loads((FOLLOWUP / "nlp_costs.json").read_text())
    if cost["missing_measurements"] or sha(ROOT / cost["point_table"]["path"]) != cost["point_table"]["sha256"]:
        raise ValueError("Missing or changed follow-up point measurements")
    extra = json.loads((FOLLOWUP / "column_8_5_historical_point.json").read_text())
    if sha(FOLLOWUP / "column_8_5_historical_point.json") != cost["extra_point_source"]["sha256"]:
        raise ValueError("Extra historical point checksum mismatch")
    points = {(r["case"], tuple(json.loads(r["point"]))): r
              for r in read_csv(ROOT / cost["point_table"]["path"])}
    points["column", (8, 5)] = {"nlp_evaluation_wall_s": extra["total_wall_s"],
                               "accepted": str(extra["accepted"]),
                               "source_sha256": cost["extra_point_source"]["sha256"]}
    records = {r["job_id"]: r for r in read_csv(FOLLOWUP / "runs.csv")}
    verified = {r["job_id"]: r for r in audit["runs"]}
    plan = json.loads((FOLLOWUP / "run.json").read_text())["plan"]
    expected = {f"column_B16_seed10_{m}" for m in METHODS} | {
        f"small_batch_B10_seed{s}_rbfopt_msrsm_sampling" for s in range(10)}
    if (len(plan) != 14 or set(records) != expected or set(verified) != expected
            or {s["job_id"] for s in plan} != expected):
        raise ValueError("Unexpected follow-up run inventory")
    callbacks = defaultdict(list)
    for event in cost["callbacks"]:
        callbacks[event["job_id"]].append(event)
    if set(callbacks) != expected or sum(map(len, callbacks.values())) != 164:
        raise ValueError("Incomplete follow-up callback ledger")
    runs = []
    for spec in plan:
        identifier = spec["job_id"]
        record, check, events = records[identifier], verified[identifier], callbacks[identifier]
        case, method, seed = spec["case_name"], spec["method"], spec["seed"]
        budget = 16 if case == "column" else 10
        if (record["status"] != "completed" or len(events) != budget
                or spec["max_evaluations"] != budget or int(record["total_evals"]) != budget
                or [e["evaluation_index"] for e in events] != list(range(1, budget + 1))
                or [e["point"] for e in events[:3]] != spec["starting_points"]):
            raise ValueError("Follow-up budget, starts or callback sequence mismatch")
        if case == "small_batch" and spec["settings"] != {
                "algorithm": "MSRSM", "global_search_method": "sampling", "rbf": "auto"}:
            raise ValueError("Small Batch must use the requested MSRSM/sampling runs")
        for event in events:
            point = points[case, tuple(event["point"])]
            if (event["point_evaluation_s"] != float(point["nlp_evaluation_wall_s"])
                    or event["source_sha256"] != point["source_sha256"]
                    or event["accepted"] != (point["accepted"] == "True")):
                raise ValueError("Follow-up callback cost differs from measured point source")
        lookup = math.fsum(e["recorded_lookup_call_s"] for e in events)
        # The October 2 figures use result_record.wall_time_s, not the outer
        # trace runner clock. Apply that same scope to the new observations.
        duration = float(record["wall_time_s"])
        target, best = check["target"], float(record["best_value"])
        hit = best <= target + 1e-5 * max(1, abs(target))
        if hit != check["target_hit"] or not lookup <= duration <= check["search_wall_s"]:
            raise ValueError("Follow-up result or method clock mismatch")
        item = {"case": case, "cstr_size": "", "budget": budget, "method": method,
                "job_id": identifier, "seed": seed, "lookup_target_hit": hit,
                "recorded_dfo_s": duration, "recorded_lookup_s": lookup,
                "search_overhead_s": duration - lookup,
                "accepted_nlp_s": math.fsum(e["point_evaluation_s"] for e in events if e["accepted"]),
                "unaccepted_nlp_s": math.fsum(e["point_evaluation_s"] for e in events if not e["accepted"]),
                "dynamic_preparation_s": 0.}
        item["estimated_total_s"] = math.fsum(item[field] for field, _, _ in COMPONENTS)
        item.update(recorded_best_value=best, target_value=target,
                    source=str((FOLLOWUP / "runs.csv").relative_to(ROOT)))
        runs.append(item)
    inputs = {str((FOLLOWUP / name).relative_to(ROOT)): sha(FOLLOWUP / name)
              for name in ("audit.json", *audit["files_sha256"])}
    inputs[audit["archive"]] = audit["archive_sha256"]
    inputs[cost["point_table"]["path"]] = cost["point_table"]["sha256"]
    return runs, inputs


def input_hashes(inputs, source_manifest):
    return {**{str((SOURCE / name).relative_to(ROOT)): sha(SOURCE / name) for name in inputs},
            **source_manifest.get("followup_sources", {})}


def full_batch_runs():
    """Load full-domain runs and reattach every measured callback cost."""
    audit = json.loads((FULL_BATCH / "audit.json").read_text())
    for name, digest in audit["files_sha256"].items():
        if sha(FULL_BATCH / name) != digest:
            raise ValueError(f"Full-domain checksum mismatch: {name}")
    if (sha(ROOT / audit["archive"]) != audit["archive_sha256"]
            or sha(ROOT / audit["point_reference"]) != audit["point_reference_sha256"]):
        raise ValueError("Full-domain archive or point reference changed")
    ref = json.loads((ROOT / audit["point_reference"]).read_text())
    points = {tuple(p["point"]): p for p in ref["points"]}
    plan = json.loads((FULL_BATCH / "run.json").read_text())["plan"]
    records = {r["job_id"]: r for r in read_csv(FULL_BATCH / "runs.csv")}
    checked = {r["job_id"]: r for r in audit["runs"]}
    expected = {f"small_batch_full_B10_seed{s}_{m}" for s in range(10) for m in METHODS}
    if len(plan) != 40 or {s["job_id"] for s in plan} != expected or set(records) != expected or set(checked) != expected:
        raise ValueError("Expected 40 full-domain Small Batch jobs")
    callbacks = defaultdict(list)
    for row in read_csv(FULL_BATCH / "evaluation_costs.csv"):
        callbacks[row["job_id"]].append(row)
    runs = []
    for spec in plan:
        identifier = spec["job_id"]
        record, check, events = records[identifier], checked[identifier], callbacks[identifier]
        if (record["status"] != "completed" or len(events) != 10 or int(record["total_evals"]) != 10
                or spec["lower_bounds"] != [1, 1, 1] or spec["upper_bounds"] != [3, 3, 3]
                or [int(e["evaluation_index"]) for e in events] != list(range(1, 11))
                or [json.loads(e["point"]) for e in events[:3]] != spec["starting_points"]):
            raise ValueError("Full-domain budget, bounds or initial design mismatch")
        accepted, rejected, lookup = [], [], []
        for event in events:
            point = points[tuple(json.loads(event["point"]))]
            measurement = point["measurement"]
            if (float(event["point_evaluation_s"]) != measurement["total_wall_s"]
                    or event["point_source_sha256"] != point["source_sha256"]
                    or (event["lookup_feasible"] == "True") != measurement["accepted"]):
                raise ValueError("Full-domain callback cost disagrees with point measurement")
            (accepted if measurement["accepted"] else rejected).append(measurement["total_wall_s"])
            lookup.append(float(event["objective_wall_s"]))
        duration, lookup = float(record["wall_time_s"]), math.fsum(lookup)
        best, target = float(record["best_value"]), check["target"]
        hit = best <= target + 1e-5 * max(1, abs(target))
        if hit != check["target_hit"] or duration < lookup or duration != check["recorded_method_s"]:
            raise ValueError("Full-domain outcome or clock mismatch")
        item = {"case": "small_batch", "cstr_size": "", "budget": 10,
                "method": spec["method"], "job_id": identifier, "seed": spec["seed"], "lookup_target_hit": hit,
                "recorded_dfo_s": duration, "recorded_lookup_s": lookup, "search_overhead_s": duration - lookup,
                "accepted_nlp_s": math.fsum(accepted), "unaccepted_nlp_s": math.fsum(rejected), "dynamic_preparation_s": 0.}
        item["estimated_total_s"] = math.fsum(item[field] for field, _, _ in COMPONENTS)
        if not math.isclose(item["estimated_total_s"], check["estimated_completion_s"], rel_tol=1e-12):
            raise ValueError("Full-domain completion estimate does not reconcile")
        item.update(recorded_best_value=best, target_value=target,
                    source=str((FULL_BATCH / "runs.csv").relative_to(ROOT)))
        runs.append(item)
    inputs = {str((FULL_BATCH / name).relative_to(ROOT)): sha(FULL_BATCH / name)
              for name in ("audit.json", *audit["files_sha256"])}
    inputs.update({audit["archive"]: audit["archive_sha256"], audit["point_reference"]: audit["point_reference_sha256"]})
    return runs, inputs


def load_runs(panels=PANELS, *, include_followup=True):
    """Load verified completion costs for the requested case/budget panels."""
    inventory = json.loads((SOURCE / "artifact_checksums.json").read_text())
    inputs = ("dfo_runs.csv", "evaluation_timings.csv", "manifest.json", "dynamic_preparations.json")
    for name in inputs:
        if sha(SOURCE / name) != inventory[name]:
            raise ValueError(f"Published source checksum mismatch: {name}")
    source_manifest = json.loads((SOURCE / "manifest.json").read_text())
    preparations = source_manifest["point_reuse_audit"]["preparations"]
    if len(preparations) != 1 or preparations[0]["included_in_point_total_wall_s"]:
        raise ValueError("Expected one historical, separately timed Dynamic preparation")
    preparation = preparations[0]
    lookup_times = defaultdict(list)
    for event in read_csv(SOURCE / "evaluation_timings.csv"):
        lookup_times[event["job_id"]].append(float(event["dfo_lookup_call_wall_s"]))
    selected = {(case, size, budget) for case, size, budget, _ in panels}
    runs, groups = [], defaultdict(list)
    for row in read_csv(SOURCE / "dfo_runs.csv"):
        key = (row["case"], row["cstr_size"], int(row["budget"]))
        if key not in selected:
            continue
        if int(row["callbacks_missing_nlp_measurement"]) or row["status"] != "completed":
            raise ValueError("Missing measurement or incomplete selected run")
        if len(lookup_times[row["job_id"]]) != int(row["completed_evaluations"]):
            raise ValueError("Callback count mismatch")
        lookup = math.fsum(lookup_times[row["job_id"]])
        item = {"case": key[0], "cstr_size": key[1], "budget": key[2],
                "method": row["method"], "job_id": row["job_id"], "seed": int(row["seed"]),
                "lookup_target_hit": row["lookup_target_hit"] == "True",
                "recorded_dfo_s": float(row["dfo_wall_time_s"]), "recorded_lookup_s": lookup,
                "search_overhead_s": float(row["dfo_wall_time_s"]) - lookup,
                "accepted_nlp_s": float(row["attached_accepted_s"]),
                "unaccepted_nlp_s": float(row["attached_unaccepted_s"]),
                "dynamic_preparation_s": preparation["total_preparation_wall_s"] if key[0] == "dynamic" else 0.}
        if any(not math.isfinite(item[field]) or item[field] < 0 for field, _, _ in COMPONENTS):
            raise ValueError("Invalid cost component")
        item["estimated_total_s"] = math.fsum(item[field] for field, _, _ in COMPONENTS)
        expected = item["recorded_dfo_s"] - lookup + float(row["attached_nlp_evaluation_s"]) + item["dynamic_preparation_s"]
        if not math.isclose(item["estimated_total_s"], expected, rel_tol=1e-12):
            raise ValueError("NLP outcome costs do not reconcile")
        item.update(recorded_best_value=float(row["recorded_best_value"]),
                    target_value=float(row["target_value"]),
                    source=str((SOURCE / "dfo_runs.csv").relative_to(ROOT)))
        runs.append(item)
    if include_followup:
        additions, sources = followup_runs()
        additions = [r for r in additions if r["case"] == "column"]
        batch, batch_sources = full_batch_runs()
        additions += batch
        sources.update(batch_sources)
        additions = [r for r in additions if (r["case"], r["cstr_size"], r["budget"]) in selected]
        removed = [r for r in runs if (r["case"], r["budget"]) == ("small_batch", 10)]
        if ("small_batch", "", 10) in selected and (len(removed) != 40
                or {(r["method"], r["seed"]) for r in removed} != {(m, s) for m in METHODS for s in range(10)}):
            raise ValueError("Expected forty original Small Batch runs to replace")
        runs = [r for r in runs if r not in removed] + additions
        if len({r["job_id"] for r in runs}) != len(runs):
            raise ValueError("Duplicate follow-up job")
        source_manifest["followup_sources"] = sources
        source_manifest["followup_selection"] = {
            "column": "Original seeds 1-9 plus seed 10 for all four methods",
            "small_batch": "Replace all four methods with full-domain {1,2,3}^3 runs, seeds 0-9, budget 10",
            "small_batch_rbfopt": "MSRSM + sampling; restricted-domain follow-up retained only as historical evidence",
            "small_batch_domain": {"lower": [1, 1, 1], "upper": [3, 3, 3], "points": 27, "feasible": 12},
            "added_job_ids": [r["job_id"] for r in additions],
            "replaced_job_ids": [r["job_id"] for r in removed],
            "dfo_clock": "result_record.wall_time_s for every method, matching the original figures",
            "point_costs": "Every callback charged its measured point cost, including repeated and rejected evaluations"}
    for row in runs:
        groups[(row["case"], row["cstr_size"], row["budget"], row["method"])].append(row)
    summary = []
    for case, size, budget, _ in panels:
        seeds = None
        for method in METHODS:
            group = groups[case, size, budget, method]
            actual = {row["seed"] for row in group}
            if len(actual) != len(group) or (seeds is not None and seeds != actual):
                raise ValueError("Unpaired method seeds")
            seeds = actual
            expected_seeds = set(range(1, 11 if include_followup else 10)) if case == "column" else set(range(10))
            if actual != expected_seeds:
                raise ValueError("Unexpected selected run count")
            summary.append({"case": case, "cstr_size": size, "budget": budget, "method": method,
                "runs": len(group), "lookup_target_hits": sum(row["lookup_target_hit"] for row in group),
                **{field: statistics.mean(row[field] for row in group)
                   for field in ("recorded_dfo_s", "recorded_lookup_s", *(c[0] for c in COMPONENTS), "estimated_total_s")}})

    return runs, summary, preparation, inputs, source_manifest


def build(output):
    runs, summary, preparation, inputs, source_manifest = load_runs()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "cost_breakdown_runs.csv", runs)
    write_csv(output / "cost_breakdown_means.csv", summary)
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#4b4b4b", "axes.linewidth": .8}):
        fig, axes = plt.subplots(2, 2, figsize=(12.6, 8.7))
        fig.subplots_adjust(left=.078, right=.985, bottom=.16, top=.76, hspace=.40, wspace=.20)
        for ax, (case, size, budget, title) in zip(axes.flat, PANELS):
            group = [next(row for row in summary if (row["case"], row["method"]) == (case, method)) for method in METHODS]
            base = [0.] * 4
            for field, _, color in COMPONENTS:
                values = [row[field] for row in group]
                ax.bar(range(4), values, bottom=base, width=.77, color=color, edgecolor="none", zorder=3)
                base = [a + b for a, b in zip(base, values)]
            for i, total in enumerate(base):
                ax.annotate(f"{total:.2f}s", (i, total), xytext=(0, 5), textcoords="offset points",
                            ha="center", va="bottom", fontsize=10, color="#202020")
            ax.set(xticks=range(4), xticklabels=LABELS, ylim=(0, max(base) * 1.16),
                   ylabel="Mean estimated total time (s)", title=f"{title}, B={budget}")
            ax.set_title(f"{title}, B={budget}", fontsize=12, pad=12)
            ax.tick_params(axis="x", length=0, pad=7)
            ax.grid(axis="y", color="#dce1e5", linewidth=.7, alpha=.65, zorder=0)
            ax.set_axisbelow(True)
        fig.suptitle("Where the time goes — all runs, including target failures", fontsize=17, y=.974)
        fig.text(.5, .925, "Dantzig traces + separately measured point costs | Fixed-path estimates", ha="center",
                 fontsize=11, color="#505860")
        patches = [Patch(facecolor=color, label=label) for _, label, color in COMPONENTS]
        fig.legend(handles=patches, loc="upper center", bbox_to_anchor=(.5, .893), ncol=2,
                   frameon=False, fontsize=9.8, columnspacing=2.1, handlelength=1.7)
        fig.text(.5, .094, "Estimate = DFO time − lookup-call time + all point-evaluation costs + Dynamic preparation once per run.",
                 ha="center", fontsize=9.2, color="#303840")
        fig.text(.5, .067, "CSTR30: successful retry cost only. Preprocessing and solver rejections share one category.",
                 ha="center", fontsize=9.2, color="#303840")
        fig.text(.5, .040, "Paths and target outcomes remain lookup-based; these totals are not measured online NLP runtimes. Dynamic reference setup: 0.109 s.",
                 ha="center", fontsize=8.8, color="#505860")
        fig.savefig(output / "cost_breakdown.png", dpi=220, facecolor="white")
        fig.savefig(output / "cost_breakdown.pdf", facecolor="white", metadata={"CreationDate": None})
        plt.close(fig)
    manifest = {"kind": "fixed_path_all_outcome_time_estimate", "measured_online_runtime": False,
        "formula": "recorded DFO runtime minus recorded lookup calls plus all linked point costs plus one reference Dynamic preparation per run",
        "selected_runs": len(runs), "all_target_failures_included": True,
        "point_cost_policy": source_manifest["cost_policy"],
        "successful_retry_audit": source_manifest["successful_retry_audit"],
        "dynamic_preparation_policy": "One historical reference preparation per Dynamic run; a scenario assumption, not a new measured setup",
        "dynamic_preparation_reference": preparation,
        "sources": input_hashes(inputs, source_manifest),
        "followup_selection": source_manifest.get("followup_selection"),
        "script_sha256": sha(Path(__file__)),
        "artifacts": {name: sha(output / name) for name in
            ("cost_breakdown.png", "cost_breakdown.pdf", "cost_breakdown_runs.csv", "cost_breakdown_means.csv")}}
    (output / "cost_breakdown.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "selected_runs": len(runs), "panels": len(PANELS)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    build(parser.parse_args().output_dir)
