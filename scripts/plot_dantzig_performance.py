"""Plot completion-time profiles and TTS99 from the current Dantzig point costs.

Run with: python -m scripts.plot_dantzig_performance
No optimizer or NLP solver is executed.
"""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics

from benchmark_analysis import runs_to_target_probability
from scripts.plot_dantzig_cost_breakdown import (
    LABELS, METHODS, OUTPUT, ROOT, SOURCE, load_runs, read_csv, sha, write_csv,
)

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator


PANELS = (("column", "", 16, "Column"), ("cstr", "30", 43, "CSTR 30"),
          ("small_batch", "", 10, "Small Batch"),
          *(("dynamic", "", budget, "Dynamic") for budget in (12, 15, 20, 30, 37, 50)))
COLORS = ("#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd")
BASELINES = ("ric", "gloa", "loa", "bigm", "hull")
FULL_PANELS = (*(("cstr", str(size), budget, f"CSTR {size}") for size, budget in
                ((5, 8), (10, 15), (15, 22), (20, 29), (25, 36), (30, 43))),
               PANELS[0], PANELS[2], PANELS[-1])
GDP_SOURCE = ROOT / "results/gdp_comparison_current/analysis"


def performance_tables(runs):
    """Keep failed paired runs in profiles and all run times in TTS99 medians."""
    pairs, groups = defaultdict(list), defaultdict(list)
    for row in runs:
        if not math.isfinite(row["estimated_total_s"]) or row["estimated_total_s"] <= 0:
            raise ValueError("Invalid completion cost")
        key = row["case"], row["cstr_size"], row["budget"]
        pairs[(*key, row["seed"])].append(row)
        groups[(*key, row["method"])].append(row)
    ratios = []
    for group in pairs.values():
        if Counter(r["method"] for r in group) != Counter(METHODS):
            raise ValueError("Profile requires one run per method and paired seed")
        fastest = min((r["estimated_total_s"] for r in group if r["lookup_target_hit"]), default=math.inf)
        for row in group:
            ratios.append({**row, "time_ratio": row["estimated_total_s"] / fastest
                           if row["lookup_target_hit"] else math.inf})
    summary = []
    for (case, size, budget, method), group in groups.items():
        hits = sum(r["lookup_target_hit"] for r in group)
        rate = hits / len(group)
        repeats = runs_to_target_probability(rate)
        median = statistics.median(r["estimated_total_s"] for r in group)
        summary.append({"case": case, "cstr_size": size, "budget": budget, "method": method,
                        "runs": len(group), "target_hits": hits, "hit_rate": rate,
                        "median_completion_s": median, "runs_99": repeats, "tts99_s": repeats * median})
    return ratios, summary


def panel_rows(rows, panel):
    return [r for r in rows if (r["case"], r["cstr_size"], r["budget"]) == panel[:3]]


def plot_profiles(ratios):
    fig, axes = plt.subplots(3, 3, figsize=(13.8, 10))
    for ax, panel in zip(axes.flat, PANELS):
        group = panel_rows(ratios, panel)
        finite = [r["time_ratio"] for r in group if math.isfinite(r["time_ratio"])]
        right = max(1.2, max(finite, default=1) * 1.04)
        for method, color in zip(METHODS, COLORS):
            values = [r["time_ratio"] for r in group if r["method"] == method]
            steps = sorted({1., right, *(v for v in values if math.isfinite(v))})
            ax.step(steps, [sum(v <= x for v in values) / len(values) for x in steps],
                    where="post", color=color, linewidth=1.8)
        ax.set(xscale="log", xlim=(1, right), ylim=(0, 1.035),
               yticks=(0, .25, .5, .75, 1), xlabel="Time / fastest successful method",
               ylabel="Fraction of all runs reaching target")
        candidates = (1, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4) if right < 1.5 else (1, 1.5, 2, 3, 5, 10, 20, 50, 100)
        ticks = [x for x in candidates if x <= right]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.set_title(f"{panel[3]}, B={panel[2]}\n{len(group) // 4} paired starts", fontsize=11)
        ax.grid(alpha=.2, linewidth=.6)
    decorate(fig, "NLP-inclusive completion-time performance profiles",
             "All paired starts remain in the denominator, including target failures.")
    return fig


def plot_tts99(summary):
    fig, axes = plt.subplots(3, 3, figsize=(13.8, 10))
    for ax, panel in zip(axes.flat, PANELS):
        group = panel_rows(summary, panel)
        finite = [r["tts99_s"] for r in group if math.isfinite(r["tts99_s"])]
        ax.set(yscale="log", ylim=(min(finite) / 3, max(finite) * 3.5), xlim=(-.6, 3.6),
               xticks=range(4), xticklabels=LABELS, ylabel="Estimated TTS99 (s, log scale)")
        for i, (method, color) in enumerate(zip(METHODS, COLORS)):
            row = next(r for r in group if r["method"] == method)
            value = row["tts99_s"]
            if math.isfinite(value):
                ax.plot(i, value, "o", color=color, markersize=8)
                ax.annotate(f"{value:.2f}", (i, value), xytext=(0, 9), textcoords="offset points",
                            ha="center", fontsize=10)
                ax.annotate(f"{row['target_hits']}/{row['runs']}", (i, value), xytext=(0, -16),
                            textcoords="offset points", ha="center", color="#606060", fontsize=9)
            else:
                ax.text(i, .85, f"∞\n0/{row['runs']}", transform=ax.get_xaxis_transform(),
                        ha="center", va="center", color=color, fontsize=12)
        ax.set_title(f"{panel[3]}, B={panel[2]}\n{group[0]['runs']} runs per method", fontsize=11)
        ax.grid(axis="y", alpha=.2, linewidth=.6)
        ax.tick_params(axis="x", labelsize=9)
    decorate(fig, "NLP-inclusive TTS99 estimates",
             "TTS99 = median completion time × ceil[log(0.01) / log(1 − hit rate)].  p=1: one run; p=0: ∞.  Labels: hits/runs.")
    return fig


def decorate(fig, title, note):
    fig.subplots_adjust(left=.066, right=.984, bottom=.13, top=.84, hspace=.65, wspace=.32)
    fig.suptitle(title, fontsize=18, y=.98)
    fig.legend([Line2D([], [], color=c, linewidth=2) for c in COLORS], LABELS,
               loc="upper center", bbox_to_anchor=(.5, .948), ncol=4, frameon=False, fontsize=11)
    fig.text(.5, .077, note, ha="center", fontsize=9.2)
    fig.text(.5, .052, "Dantzig DFO traces + separate point costs; successful CSTR30 retry cost only. All unsuccessful evaluation costs included.",
             ha="center", fontsize=9.2)
    fig.text(.5, .027, "Fixed-path completion estimates, not first-hit or measured online NLP times. TTS99 assumes independent restarts with the observed hit rate.",
             ha="center", fontsize=9, color="#555555")


def full_benchmark():
    """Bring in every selected GDPopt/MINLP run without turning it into seed trials."""
    inventory = json.loads((GDP_SOURCE / "artifact_checksums.json").read_text())
    if sha(GDP_SOURCE / "comparison.csv") != inventory["comparison.csv"]:
        raise ValueError("GDP/MINLP comparison checksum mismatch")
    baseline = read_csv(GDP_SOURCE / "comparison.csv")
    expected = {(p[0], p[1], method) for p in FULL_PANELS for method in BASELINES}
    keys = [(r["case"], r["cstr_size"], r["method"]) for r in baseline]
    if len(keys) != 45 or set(keys) != expected:
        raise ValueError("Expected all 45 unique selected GDPopt/MINLP jobs")
    runs, means, _, _, _ = load_runs(FULL_PANELS)
    raw = {r["job_id"]: r for r in read_csv(SOURCE / "dfo_runs.csv")}
    rows = []
    for row in means:
        group = [raw[r["job_id"]] for r in runs if
                 (r["case"], r["cstr_size"], r["budget"], r["method"]) ==
                 (row["case"], row["cstr_size"], row["budget"], row["method"])]
        attained = sum(float(r["recorded_best_value"]) <= float(r["target_value"]) +
                       1e-5 * max(1, abs(float(r["target_value"]))) for r in group)
        if attained != row["lookup_target_hits"]:
            raise ValueError("DFO attainment differs from the published target matches")
        rows.append({"case": row["case"], "cstr_size": row["cstr_size"], "method": row["method"],
                     "family": "DFO", "dfo_budget": row["budget"], "runs": row["runs"],
                     "completion_s": row["estimated_total_s"], "clock_kind": "mean_fixed_path_estimate",
                     "target_attained": attained, "time_limits": 0, "bound_conflicts": 0,
                     "final_objective": statistics.mean(float(r["recorded_best_value"]) for r in group),
                     "objective_statistic": "mean", "target_value": float(group[0]["target_value"]),
                     "source": str((SOURCE / "dfo_runs.csv").relative_to(ROOT))})
    for row in baseline:
        duration = float(row["measured_total_with_preparation_s"])
        if not math.isfinite(duration) or duration <= 0 or row["source_host"] != "dantzig.ecn.purdue.edu":
            raise ValueError("Invalid GDP/MINLP source or completion time")
        rows.append({"case": row["case"], "cstr_size": row["cstr_size"], "method": row["method"],
                     "family": "GDPopt" if row["method"] in BASELINES[:3] else "MINLP", "dfo_budget": "",
                     "runs": 1, "completion_s": duration, "clock_kind": "single_measured_completion_with_preparation",
                     "target_attained": int(row["target_attained"] == "True"),
                     "time_limits": int(row["termination"] == "maxTimeLimit"),
                     "bound_conflicts": int(row["bound_conflict_with_saved_solution"] == "True"),
                     "final_objective": float(row["objective"]), "objective_statistic": "single_run",
                     "target_value": float(row["target_value"]), "source": row["source_directory"]})
    return rows


def plot_full_benchmark(rows):
    fig, ax = plt.subplots(figsize=(16.8, 7.8))
    ax.axis("off")
    cells = []
    for panel in FULL_PANELS:
        line = [f"{panel[3]}\nDFO B={panel[2]}"]
        for method in (*METHODS, *BASELINES):
            r = next(r for r in rows if (r["case"], r["cstr_size"], r["method"]) == (*panel[:2], method))
            markers = (" TL" if r["time_limits"] else "") + (" †" if r["bound_conflicts"] else "")
            line.append(f"{r['completion_s']:.2f} s{markers}\n{r['target_attained']}/{r['runs']}")
        cells.append(line)
    table = ax.table(cellText=cells, colLabels=("Model", *LABELS, "RIC\nGDPopt", "GLOA\nGDPopt",
                    "LOA\nGDPopt", "Big-M\nMINLP", "Hull\nMINLP"), cellLoc="center",
                     colWidths=[.13] + [.096] * 9, bbox=(0, .16, 1, .73))
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#d7dfe5")
        cell.set_linewidth(.6)
        if row == 0:
            cell.set_facecolor("#dcebf5" if 1 <= col <= 4 else "#e7e9eb")
            cell.set_text_props(weight="bold")
        elif row % 2:
            cell.set_facecolor("#f7f9fb")
    fig.suptitle("DFO, GDPopt and MINLP completion times — all nine models", fontsize=18, y=.97)
    fig.text(.5, .907, "Each cell: completion time / target attainment count. All 45 GDPopt and MINLP jobs are included.",
             ha="center", fontsize=11)
    fig.text(.5, .128, "DFO: mean estimated completion time over 9 or 10 starts. GDPopt/MINLP: one measured run per model, including template preparation.",
             ha="center", fontsize=10)
    fig.text(.5, .098, "Target attained: final objective ≤ lookup target + tolerance. TL: time limit. †: reported bound conflicts with a saved feasible solution.",
             ha="center", fontsize=10)
    fig.text(.5, .068, "GDPopt: BARON + HiGHS (Oct 1). Big-M/Hull: BARON (Sep 25). All on Dantzig; different dates/CPUs. Completion times, not first-hit times.",
             ha="center", fontsize=10)
    fig.text(.5, .038, "CSTR5–25 DFO costs include NLP attempts that did not reproduce feasible lookup outcomes; the recorded search targets remain lookup-based.",
             ha="center", fontsize=9.5, color="#555555")
    return fig


def build(output=OUTPUT):
    runs, _, preparation, inputs, source_manifest = load_runs(PANELS)
    ratios, summary = performance_tables(runs)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "performance_profile_runs.csv", ratios)
    write_csv(output / "tts99_summary.csv", summary)
    benchmark = full_benchmark()
    write_csv(output / "all_method_completion_times.csv", benchmark)
    (output / "gdp_minlp_runs.csv").write_bytes((GDP_SOURCE / "comparison.csv").read_bytes())
    artifacts = ["performance_profile_runs.csv", "tts99_summary.csv", "all_method_completion_times.csv", "gdp_minlp_runs.csv"]
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False}):
        for name, fig in (("performance_profiles", plot_profiles(ratios)), ("tts99", plot_tts99(summary)),
                          ("all_method_completion_times", plot_full_benchmark(benchmark))):
            for ext in ("png", "pdf"):
                filename = f"{name}.{ext}"
                fig.savefig(output / filename, dpi=220, facecolor="white",
                            metadata={"CreationDate": None} if ext == "pdf" else None)
                artifacts.append(filename)
            plt.close(fig)
    manifest = {"panels": [list(p) for p in PANELS], "runs": len(runs),
                "time_kind": "fixed_path_completion_estimate", "measured_online_runtime": False,
                "time_formula": "DFO runtime - lookup calls + selected point costs + one Dynamic preparation per run",
                "target_definition": "Frozen lookup target within 1e-5 * max(1, abs(target))",
                "profile_definition": "Successful completion time / fastest successful method on the paired start; failures have infinite ratios and stay in the denominator",
                "tts99_definition": "Median completion time over all seeds * ceil(log(0.01) / log(1 - observed hit rate)); p=0: infinity, p=1: one run",
                "tts99_assumption": "Independent restarts with the observed hit probability; an estimate from 9 or 10 runs, not a 99% confidence guarantee",
                "point_cost_policy": source_manifest["cost_policy"], "dynamic_preparation_reference": preparation,
                "sources": {str((SOURCE / name).relative_to(ROOT)): sha(SOURCE / name) for name in inputs},
                "gdp_minlp_source": {str((GDP_SOURCE / "comparison.csv").relative_to(ROOT)): sha(GDP_SOURCE / "comparison.csv")},
                "gdp_minlp_runs": 45, "all_method_comparison_rows": len(benchmark),
                "gdp_minlp_policy": "Single measured completion per method/model; preserve time limits, target attainment and bound conflicts; no restart probability or TTS99 inferred from one run",
                "scripts": {str(path.relative_to(ROOT)): sha(path) for path in
                            (Path(__file__), ROOT / "scripts/plot_dantzig_cost_breakdown.py", ROOT / "benchmark_analysis.py")},
                "artifacts": {name: sha(output / name) for name in artifacts}}
    (output / "performance.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "panels": len(PANELS), "runs": len(runs)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    build(parser.parse_args().output_dir)
