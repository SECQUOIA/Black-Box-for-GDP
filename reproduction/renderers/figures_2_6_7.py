from pathlib import Path
import csv
import json
import math
import statistics
from collections import defaultdict
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--repository", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
R = args.repository.resolve()
W = args.output.resolve()
W.mkdir(parents=True, exist_ok=True)
F = W / "figures"
F.mkdir(exist_ok=True)
P = W / "previews"
P.mkdir(exist_ok=True)
GP = R / "results/grid_gdp_dfo_20261011/runs.csv"
PP = R / "results/process_ipopt_bam_v2_20261015/tables/run_results.csv"


def read(p):
    with p.open() as stream:
        return list(csv.DictReader(stream))


grid = read(GP)
proc = read(PP)
M = ["dsda", "rbfopt", "bam", "fmqa_sa"]
B = [10, 30, 50, 70, 100]
LABEL = dict(zip(M, ["DSDA", "RBFOpt", "BAM", "FMQA-SA"]))
C = dict(zip(M, ["#1976b9", "#e77818", "#27952a", "#9467bd"]))
LS = dict(zip(M, ["-", "--", "-.", ":"]))
MK = dict(zip(M, ["o", "s", "^", "D"]))
gg = defaultdict(list)
pg = defaultdict(list)
for r in grid:
    gg[int(r["max_evals"]), r["method"]].append(r)
for r in proc:
    pg[r["case"], int(r["budget"]), r["method"]].append(r)
assert len(grid) == 4200 and len(proc) == 560
assert all(len(r) == 210 for r in gg.values()) and all(
    len(r) == 10 for r in pg.values()
)
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
    }
)


def save(fig, name):
    fig.savefig(
        F / (name + ".pdf"),
        bbox_inches="tight",
        pad_inches=0.05,
        metadata={"CreationDate": None, "ModDate": None},
    )
    fig.savefig(P / (name + ".png"), dpi=170, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def handles():
    return [
        Line2D([], [], color=C[m], ls=LS[m], marker=MK[m], ms=3, lw=1.5, label=LABEL[m])
        for m in M
    ]


checks = []
fig, axs = plt.subplots(2, 3, figsize=(8.2, 5.4), sharey=True)
for ax, b in zip(axs.flat, B):
    for m in M:
        rr = gg[b, m]
        v = [float(r["first_hit_evaluation"]) for r in rr if r["target_hit"] == "True"]
        xs = sorted({0, b, *v})
        ys = [sum(t <= x for t in v) / 210 for x in xs]
        checks.append(
            dict(
                figure="figure_B_grid_evaluation_profiles",
                budget=b,
                method=m,
                hits=len(v),
                n=210,
                x=xs,
                y=ys,
            )
        )
        ax.step(
            xs,
            ys,
            where="post",
            color=C[m],
            ls=LS[m],
            marker=MK[m],
            ms=2.7,
            markevery=max(1, len(xs) // 6),
            lw=1.45,
        )
    ax.axvline(3, color="#707070", lw=1, ls=(0, (4, 3)), zorder=2)
    ax.set(
        title=f"Evaluation budget $B={b}$",
        ylim=(-0.015, 1.025),
        xlim=(0, b),
        yticks=[0, 0.25, 0.5, 0.75, 1],
        xlabel="Objective evaluations to first target",
    )
    ax.set_xticks([0, b // 2, b])
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
for ax in axs[:, 0]:
    ax.set_ylabel("Fraction reaching target")
note = axs.flat[5]
note.axis("off")
note.legend(
    handles=handles()
    + [
        Line2D(
            [],
            [],
            color="#707070",
            ls=(0, (4, 3)),
            lw=1,
            label="Shared initialization ends (3)",
        )
    ],
    loc="upper left",
    frameon=False,
    handlelength=2.7,
    fontsize=8,
)
note.text(
    0.04,
    0.30,
    "21 functions × 10 paired seeds\nMisses retained in denominator\nInitial and repeated calls count",
    va="top",
    fontsize=8.5,
    linespacing=1.55,
)
fig.tight_layout(h_pad=2.1, w_pad=1.4)
save(fig, "figure_B_grid_evaluation_profiles")

PANELS = [("column", 16), ("cstr_30", 43), ("small_batch", 10)] + [
    ("dynamic", b) for b in [12, 15, 20, 30, 37, 50]
]


def pname(c, b):
    return {
        "column": "Column",
        "cstr_30": "CSTR 30",
        "small_batch": "Small Batch",
        "dynamic": "Dynamic",
    }[c] + f" (B={b})"


ticks = []


def logticks(axis, lo, hi):
    vs = [
        f * 10.0**k
        for k in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1)
        for f in (1, 2, 5)
        if lo <= f * 10.0**k <= hi
    ]
    if len(vs) < 2:
        vs = [
            f * 10.0**k
            for k in range(
                math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1
            )
            for f in (1, 1.5, 2, 3, 4, 5, 7.5)
            if lo <= f * 10.0**k <= hi
        ]
    if len(vs) > 4:
        vs = vs[:: math.ceil(len(vs) / 4)]
    axis.set_major_locator(FixedLocator(vs))
    axis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:g}"))
    axis.set_minor_formatter(NullFormatter())
    return vs


fig, axs = plt.subplots(3, 3, figsize=(8.2, 7.3))
for ax, (c, b) in zip(axs.flat, PANELS):
    ax.set_title(pname(c, b))
    vals = [float(r["reconstructed_total_s"]) for m in M for r in pg[c, b, m]]
    left, right = min(vals) * 0.8, max(vals) * 1.25
    for m in M:
        rr = pg[c, b, m]
        v = [
            float(r["reconstructed_total_s"])
            for r in rr
            if r["category"] == "target_reached"
        ]
        xs = sorted({left, right, *v})
        ys = [sum(t <= x for t in v) / 10 for x in xs]
        checks.append(
            dict(
                figure="process_completion_profiles",
                case=c,
                budget=b,
                method=m,
                hits=len(v),
                n=10,
                x=xs,
                y=ys,
            )
        )
        ax.step(
            xs,
            ys,
            where="post",
            color=C[m],
            ls=LS[m],
            marker=MK[m],
            ms=2.7,
            markevery=max(1, len(xs) // 5),
            lw=1.3,
        )
    ax.set(
        xscale="log",
        xlim=(left, right),
        ylim=(-0.03, 1.05),
        yticks=[0, 0.5, 1],
        xlabel="Estimated full-run completion\ntime (s; log scale)",
        ylabel="Target-hit fraction",
    )
    ts = logticks(ax.xaxis, left, right)
    ticks.append(dict(case=c, budget=b, limits=[left, right], ticks=ts))
    ax.grid(alpha=0.25)
    ax.set_axisbelow(True)
fig.legend(
    handles=handles(),
    loc="lower center",
    ncol=4,
    frameon=False,
    bbox_to_anchor=(0.5, 0.005),
)
fig.tight_layout(rect=(0.01, 0.06, 0.995, 0.995), h_pad=1.8, w_pad=1.2)
save(fig, "process_completion_profiles")

# Reproduce the displayed mean-component bars from the same ten runs per condition.
plt.rcParams.update(
    {
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 8,
        "grid.linewidth": 0.5,
    }
)
fig, axs = plt.subplots(2, 2, figsize=(7.5, 5.2))
costchecks = []
components = [
    ("#5086ad", "///", "Search overhead"),
    ("#c2c7cc", "", "Point evaluations"),
    ("#b58fc4", "xx", "Dynamic preparation"),
]
for ax, (c, b) in zip(
    axs.flat, [("column", 16), ("cstr_30", 43), ("small_batch", 10), ("dynamic", 50)]
):
    for j, m in enumerate(M):
        rr = pg[c, b, m]
        v = [
            statistics.mean(
                float(r["dfo_wall_s"]) - float(r["lookup_wall_s"]) for r in rr
            ),
            statistics.mean(
                float(r["historical_nlp_known_within_budget_s"]) for r in rr
            ),
            statistics.mean(float(r["dynamic_preparation_s"]) for r in rr),
        ]
        total = sum(v)
        bt = 0
        assert math.isclose(
            total,
            statistics.mean(float(r["reconstructed_total_s"]) for r in rr),
            rel_tol=1e-12,
        )
        for vv, (color, hatch, label) in zip(v, components):
            pc = 100 * vv / total
            ax.bar(
                j,
                pc,
                bottom=bt,
                color=color,
                hatch=hatch,
                edgecolor="#444444",
                linewidth=0.4,
                width=0.66,
            )
            if pc >= 5:
                ax.text(
                    j, bt + pc / 2, f"{pc:.1f}%", ha="center", va="center", fontsize=7.5
                )
            bt += pc
        ax.text(j, 102, f"{total:.2f}", ha="center", va="bottom", fontsize=7.5)
        costchecks.append(
            dict(case=c, budget=b, method=m, mean_total=total, mean_components=v)
        )
    ax.text(
        0.5,
        0.98,
        "Mean total (s)",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=8,
        color="#444444",
    )
    ax.set(
        title=pname(c, b),
        xticks=range(4),
        xticklabels=[LABEL[m] for m in M],
        ylim=(0, 128),
        yticks=[0, 25, 50, 75, 100],
        ylabel="Share of mean total (%)",
    )
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
fig.legend(
    handles=[
        Patch(facecolor=c, hatch=h, edgecolor="#444444", label=label)
        for c, h, label in components
    ],
    loc="lower center",
    ncol=3,
    frameon=False,
    bbox_to_anchor=(0.5, 0.002),
)
fig.tight_layout(rect=(0.01, 0.075, 0.995, 0.995), h_pad=1.8, w_pad=1.6)
save(fig, "process_cost_breakdown")


(W / "figure_values.json").write_text(
    json.dumps(
        {"profiles": checks, "cost_components": costchecks, "ticks": ticks}, indent=2
    )
    + "\n"
)
