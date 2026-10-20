"""Regenerate Figure 8 from the manuscript's pinned process run inventory.

Adapted from scripts/process_ipopt/build_figures.py at
SECQUOIA/RBFopt_Test@cb70771b2037301bb6d0e38a2362d49b53fcda7d.
Preserves the manuscript's descriptive axis labels and color palette.
Execution failures use filled squares, distinct from target-miss crosses.
"""

from pathlib import Path
from collections import defaultdict, Counter
import csv
import math
import statistics
import json
import hashlib
import argparse
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
INPUT = args.input.resolve()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(INPUT.open()))
groups = defaultdict(list)
for r in rows:
    groups[r["case"], int(r["budget"]), r["method"]].append(r)
assert len(rows) == 560 and len(groups) == 56
assert all(len(rr) == 10 for rr in groups.values())
assert Counter(r["category"] for r in rows) == {
    "target_reached": 291,
    "target_not_reached": 268,
    "execution_failed": 1,
}
ORDER = ["dsda", "rbfopt", "bam", "fmqa_sa"]
COLORS = dict(zip(ORDER, ["#1976b9", "#e77818", "#27952a", "#9467bd"]))
PANELS = [("column", 16), ("cstr_30", 43), ("small_batch", 10)] + [
    ("dynamic", b) for b in [12, 15, 20, 30, 37, 50]
]
NAMES = {
    "column": "Column",
    "cstr_30": "CSTR 30",
    "small_batch": "Small Batch",
    "dynamic": "Dynamic",
}
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "pdf.fonttype": 42,
        "axes.linewidth": 0.65,
        "grid.linewidth": 0.5,
    }
)


def logticks(axis, lo, hi):
    vs = [
        f * 10.0**k
        for k in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1)
        for f in (1, 2, 5)
        if lo <= f * 10.0**k <= hi
    ]
    if len(vs) > 4:
        vs = vs[:: math.ceil(len(vs) / 4)]
    axis.set_major_locator(FixedLocator(vs))
    axis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:g}"))
    axis.set_minor_formatter(NullFormatter())


fig, axs = plt.subplots(3, 3, figsize=(8.2, 7.3))
checks = []
for ax, (c, b) in zip(axs.flat, PANELS):
    ax.set_title(f"{NAMES[c]} (B={b})", pad=5)
    ax.grid(alpha=0.28)
    ax.set_axisbelow(True)
    vals = []
    for j, m in enumerate(ORDER):
        rr = groups[c, b, m]
        values = [float(r["reconstructed_total_s"]) for r in rr]
        assert all(math.isfinite(v) and v > 0 for v in values)
        vals.extend(values)
        for r, v in zip(rr, values):
            marker = {
                "target_reached": "o",
                "execution_failed": "s",
                "target_not_reached": "x",
            }[r["category"]]
            ax.scatter(
                j + (int(r["seed"]) - 4.5) * 0.048,
                v,
                color=COLORS[m],
                marker=marker,
                s=15,
                linewidths=0.8,
                zorder=4,
            )
            checks.append(
                {
                    "case": c,
                    "budget": b,
                    "method": m,
                    "seed": int(r["seed"]),
                    "category": r["category"],
                    "marker": marker,
                    "completion_s": v,
                }
            )
        ax.hlines(statistics.median(values), j - 0.3, j + 0.3, color="#202020", lw=1)
    ax.set(
        yscale="log",
        ylim=(min(vals) * 0.65, max(vals) * 1.65),
        xticks=range(4),
        xticklabels=["D", "R", "B", "F"],
        ylabel="Estimated full-run completion\ntime (s; log scale)",
    )
    logticks(ax.yaxis, min(vals) * 0.65, max(vals) * 1.65)
fig.legend(
    handles=[
        Line2D([], [], ls="", marker=z, color="#555555", ms=4, label=t)
        for z, t in [
            ("o", "Target hit"),
            ("x", "Target miss"),
            ("s", "Execution failure"),
        ]
    ],
    loc="lower center",
    ncol=3,
    frameon=False,
    bbox_to_anchor=(0.5, 0.005),
)
fig.tight_layout(rect=(0.01, 0.065, 0.995, 0.995), h_pad=1.8, w_pad=1.6)
pdf = OUT / "process_completion_scatter.pdf"
fig.savefig(
    pdf,
    bbox_inches="tight",
    pad_inches=0.04,
    metadata={"CreationDate": None, "ModDate": None},
)
fig.savefig(
    OUT / "process_completion_scatter.png",
    dpi=170,
    bbox_inches="tight",
    pad_inches=0.04,
)
plt.close(fig)
assert len(checks) == 360 and sum(r["marker"] == "s" for r in checks) == 1
manifest = {
    "source_revision": "cb70771b2037301bb6d0e38a2362d49b53fcda7d",
    "input_path": "results/process_ipopt_bam_v2_20261015/tables/run_results.csv",
    "input_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
    "output_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
    "plotted_points": 360,
    "groups": 36,
    "points": checks,
}
(OUT / "figure8_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({k: v for k, v in manifest.items() if k != "points"}, indent=2))
