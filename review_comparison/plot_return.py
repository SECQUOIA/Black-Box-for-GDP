"""Plot verified summary tables; no lookup evaluation or solver calls."""

import argparse
from collections import defaultdict
from pathlib import Path
import statistics

from .common import csvrows, save, sha


METHODS = {
    "rbfopt_msrsm_solver": ("RBFOpt solver (retained)", "#0072B2", "--"),
    "rbfopt_msrsm_genetic": ("RBFOpt genetic (new)", "#D55E00", "-"),
    "bam": ("BAM (retained)", "#009E73", "-"),
    "bam_predetermined_uniform": ("BAM prefix + uniform (new)", "#009E73", ":"),
    "uniform_without_replacement": ("Uniform (new)", "#777777", "--"),
    "dsda": ("Budgeted DSDA (retained)", "#CC79A7", "-"),
    "fmqa_sa": ("FMQA-SA (retained)", "#E69F00", "-"),
}


def plot(tables, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    rows = csvrows(tables / "completed_runs.csv")
    groups = defaultdict(list)
    for r in rows:
        if r["scope"] == "grid":
            groups[r["method"], int(r["budget"])].append(r)
    budgets = [10, 30, 50, 70, 100]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for method, (label, color, style) in METHODS.items():
        hit, search, total = [], [], []
        for b in budgets:
            rr = groups[method, b]
            hit.append(100 * sum(r["category"] == "target_reached" for r in rr) / len(rr))
            search.append(statistics.median(float(r["search_s"]) for r in rr))
            total.append(statistics.median(float(r["search_s"]) + float(r["point_cost_s"]) + float(r["prep_s"]) for r in rr))
        for ax, values in zip(axes, (hit, search, total)):
            ax.plot(budgets, values, label=label, color=color, linestyle=style, marker="o", markersize=4)
    for ax, title in zip(axes, ("Target attainment", "Median retained search time", "Median reconstructed completion cost")):
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Callback budget B")
        ax.set_xticks(budgets)
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Target hits / 210 runs (%)")
    axes[0].set_ylim(0, 100)
    for ax in axes[1:]:
        ax.set_yscale("log")
        ax.set_ylabel("Seconds (log scale)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=9, frameon=False)
    fig.suptitle("21 Grid functions · 10 seeds per function and budget", fontsize=13)
    fig.tight_layout(rect=(0, 0.20, 1, 0.95))
    save_figure(fig, output, "grid_comparison")
    plt.close(fig)

    conditions = [(f"cstr_{n}", b) for n, b in zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43))]
    conditions += [("column", 16), ("small_batch", 10)]
    conditions += [("dynamic", b) for b in (12, 15, 20, 30, 37, 50)]
    methods = [m for m in METHODS if m != "bam_predetermined_uniform"]
    summary = csvrows(tables / "condition_summary.csv")
    index = {(r["case"], int(r["budget"]), r["method"]): r for r in summary if r["scope"] == "process"}
    values = [[int(index[c, b, m]["target_reached"]) for m in methods] for c, b in conditions]
    fig, ax = plt.subplots(figsize=(10, 7.5))
    im = ax.imshow(values, vmin=0, vmax=10, cmap="Blues", aspect="auto")
    for i, (case, budget) in enumerate(conditions):
        for k, method in enumerate(methods):
            r = index[case, budget, method]
            failed = int(r["execution_failed"])
            ax.text(k, i, f"{values[i][k]}/10" + (f" ({failed}F)" if failed else ""),
                    ha="center", va="center", color="white" if values[i][k] >= 6 else "black")
    ax.set_yticks(range(len(conditions)), [f"{c.replace('_', ' ').upper()} · B={b}" for c, b in conditions])
    ax.set_xticks(range(len(methods)), [METHODS[m][0].replace(" (", "\n(") for m in methods])
    ax.tick_params(axis="x", length=0, pad=10)
    ax.set_title("Process target attainment: all ten seeds retained", pad=15)
    fig.colorbar(im, ax=ax, label="Target hits / 10 seeds", fraction=0.035, pad=0.03)
    fig.text(0.5, 0.015, "F denotes a retained execution failure; targets are frozen IPOPT-table best values.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save_figure(fig, output, "process_target_counts")
    plt.close(fig)
    save(output / "manifest.json", {
        "matplotlib": matplotlib.__version__,
        "inputs_sha256": {n: sha(tables / n) for n in ("completed_runs.csv", "condition_summary.csv")},
        "outputs_sha256": {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        "note": "New analysis figures; original manuscript and execution artifacts unchanged.",
    })


def save_figure(fig, directory, name):
    fig.savefig(directory / (name + ".pdf"), metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(directory / (name + ".png"), dpi=160)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.tables, args.output)


if __name__ == "__main__":
    main()
