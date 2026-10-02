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


def load_runs(panels=PANELS):
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
        runs.append(item)
        groups[(*key, row["method"])].append(item)
    summary = []
    for case, size, budget, _ in panels:
        seeds = None
        for method in METHODS:
            group = groups[case, size, budget, method]
            actual = {row["seed"] for row in group}
            if len(actual) != len(group) or (seeds is not None and seeds != actual):
                raise ValueError("Unpaired method seeds")
            seeds = actual
            if len(group) != (9 if case == "column" else 10):
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
        "sources": {str((SOURCE / name).relative_to(ROOT)): sha(SOURCE / name) for name in inputs},
        "script_sha256": sha(Path(__file__)),
        "artifacts": {name: sha(output / name) for name in
            ("cost_breakdown.png", "cost_breakdown.pdf", "cost_breakdown_runs.csv", "cost_breakdown_means.csv")}}
    (output / "cost_breakdown.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "selected_runs": len(runs), "panels": len(PANELS)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    build(parser.parse_args().output_dir)
