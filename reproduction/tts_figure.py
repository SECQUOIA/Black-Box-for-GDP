"""Manuscript Figure 4: separate zero-hit counts and infinite-median strip."""

import hashlib
import math

from common import METHODS


def plot_tts99(groups):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    colors = dict(zip(METHODS, ["#1976b9", "#e77818", "#27952a", "#9467bd"]))
    labels = dict(zip(METHODS, ["DSDA", "RBFOpt", "BAM", "FMQA-SA"]))
    budgets = [10, 30, 50, 70, 100]
    markers = dict(zip(budgets, ["o", "s", "D", "^", "P"]))
    names = sorted(
        groups[0]["grids"], key=lambda n: hashlib.sha256(n.encode()).hexdigest()
    )
    jitter = {n: -0.21 + 0.42 * i / (len(names) - 1) for i, n in enumerate(names)}
    fig = plt.figure(figsize=(9, 5.5))
    layout = fig.add_gridspec(3, 1, height_ratios=[0.45, 0.35, 4.1], hspace=0.02)
    counts = fig.add_subplot(layout[0])
    infinity = fig.add_subplot(layout[1], sharex=counts)
    ax = fig.add_subplot(layout[2], sharex=counts)
    counts.axis("off")
    infinity.axis("off")
    counts.set_title("Functions with zero observed hits (out of 21)", fontsize=9, pad=8)
    for group in groups:
        method, budget = group["method"], group["budget"]
        x = 6 * METHODS.index(method) + budgets.index(budget)
        points = [
            (n, v) for n, v in zip(group["grids"], group["values"]) if math.isfinite(v)
        ]
        ax.scatter(
            [x + jitter[n] for n, v in points],
            [v for n, v in points],
            marker=markers[budget],
            color=colors[method],
            s=23,
            alpha=0.78,
            edgecolors="none",
        )
        counts.text(
            x,
            0.5,
            str(group["infinite"]),
            color=colors[method],
            ha="center",
            va="center",
            fontsize=9,
        )
        if math.isfinite(group["median"]):
            ax.hlines(group["median"], x - 0.31, x + 0.31, color="black", lw=1.5)
        else:
            infinity.text(x, 0.55, "∞", ha="center", va="center")
    infinity.text(
        0.5,
        0.1,
        "∞ marks a median that remains infinite",
        transform=infinity.transAxes,
        ha="center",
        fontsize=7,
        color="#666",
    )
    values = [v for g in groups for v in g["values"] if math.isfinite(v)]
    ax.set(
        yscale="log",
        ylim=(min(values) / 1.6, 10 ** math.ceil(math.log10(max(values)))),
        xlim=(-0.65, 22.65),
        ylabel="Empirical median-cost restart estimate\n(TTS99; s, log scale)",
    )
    positions = [6 * i + j for i in range(4) for j in range(5)]
    ax.set_xticks(positions, [str(b) for _ in METHODS for b in budgets])
    ax.tick_params(axis="x", length=0, labelsize=8)
    ax.grid(axis="y", alpha=0.25)
    for i, method in enumerate(METHODS):
        ax.text(
            6 * i + 2,
            -0.14,
            labels[method],
            transform=ax.get_xaxis_transform(),
            color=colors[method],
            weight="semibold",
            ha="center",
            va="top",
        )
    legend = [
        Line2D([], [], ls="", marker=markers[b], color="#555", ms=5, label=f"B={b}")
        for b in budgets
    ]
    legend.append(Line2D([], [], color="black", label="Median"))
    fig.legend(
        handles=legend,
        loc="upper center",
        ncol=6,
        frameon=False,
        bbox_to_anchor=(0.54, 1),
        fontsize=8,
    )
    fig.subplots_adjust(left=0.11, right=0.99, bottom=0.13, top=0.87)
    return fig
