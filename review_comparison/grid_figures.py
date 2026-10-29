"""Grid-only rendering with the retained publication layout and new records."""

import math
import statistics as st
from .manuscript import (
    BUDGETS,
    GRID,
    COLOR,
    STYLE,
    MARK,
    LABEL,
    AXIS_LABEL,
    summarize,
    dump,
)


def figures(rows, groups, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import LogLocator, NullFormatter

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 11,
            "axes.labelsize": 10.5,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
        }
    )
    checks = []

    def save(fig, name):
        fig.savefig(
            out / (name + ".pdf"),
            bbox_inches="tight",
            pad_inches=0.04,
            metadata={"CreationDate": None, "ModDate": None},
        )
        fig.savefig(
            out / (name + ".png"), dpi=160, bbox_inches="tight", pad_inches=0.04
        )
        plt.close(fig)

    def handles(methods):
        return [
            Line2D(
                [],
                [],
                color=COLOR[m],
                ls=STYLE[m],
                marker=MARK[m],
                ms=4,
                lw=1.5,
                label=LABEL[m],
            )
            for m in methods
        ]

    def profile(ax, rr, m, key, n, right=None):
        vals = sorted(r[key] for r in rr if r["hit"])
        if key == "first_hit":
            xs = sorted({0, right, *vals})
        else:
            allv = [r[key] for r in rr]
            xs = sorted({min(allv) * 0.8, max(allv) * 1.2, *vals})
        ys = [sum(v <= x for v in vals) / n for x in xs]
        ax.step(
            xs,
            ys,
            where="post",
            color=COLOR[m],
            ls=STYLE[m],
            lw=1.6,
            marker=MARK[m],
            ms=3.5,
            markevery=max(1, len(xs) // 5),
        )
        checks.append(
            dict(
                method=m,
                scope=rr[0]["scope"],
                case=rr[0]["case"] if n == 10 else "all_grid",
                budget=rr[0]["budget"],
                axis=key,
                n=n,
                hits=len(vals),
                x=xs,
                y=ys,
            )
        )

    for key, name in [
        ("first_hit", "figure_B_grid_evaluation_profiles"),
        ("total_s", "figure_C_grid_completion_profiles"),
    ]:
        fig, axs = plt.subplots(2, 3, figsize=(8.2, 5.8), sharey=True)
        for ax, b in zip(axs.flat, BUDGETS):
            for m in GRID:
                rr = [
                    r
                    for r in rows
                    if r["scope"] == "grid" and r["budget"] == b and r["method"] == m
                ]
                profile(ax, rr, m, key, 210, b)
            ax.set(title=f"Budget B={b}", ylim=(-0.02, 1.03), yticks=[0, 0.5, 1])
            if key == "first_hit":
                ax.axvline(3, color="#777777", ls="--", lw=0.8)
                ax.axvspan(3, min(13, b), color="#008b8b", alpha=0.09)
                ax.set(xlim=(0, b), xlabel="Charged evaluations")
                ax.set_xticks([0, b // 2, b])
            else:
                ax.set(xscale="log", xlabel="Completion cost (s)")
                ax.xaxis.set_major_locator(LogLocator(numticks=3))
                ax.xaxis.set_minor_formatter(NullFormatter())
            ax.grid(axis="y", alpha=0.2)
        for ax in axs[:, 0]:
            ax.set_ylabel("Target-hit fraction")
        ax = axs.flat[-1]
        ax.axis("off")
        ax.legend(handles=handles(GRID), loc="upper left", frameon=False, fontsize=10)
        if key == "first_hit":
            ax.text(
                0.02,
                0.12,
                "Dashed: shared starts end (3)\nShaded: BAM fixed prefix",
                fontsize=9.5,
                transform=ax.transAxes,
            )
        fig.tight_layout(h_pad=1.8, w_pad=0.8)
        save(fig, name)
    # Per-function TTS99 points retain infinite estimates and all 21 functions.
    fig, axs = plt.subplots(1, 2, figsize=(8.2, 4.3))
    fn = sorted({r["case"] for r in rows if r["scope"] == "grid"})
    for ax, b in zip(axs, [10, 100]):
        values = [[summarize(groups["grid", c, b, m])["tts"] for c in fn] for m in GRID]
        finite = [v for vv in values for v in vv if math.isfinite(v)]
        top = max(finite) * 4
        for j, (m, vv) in enumerate(zip(GRID, values)):
            for i, v in enumerate(vv):
                ax.scatter(
                    j + (i - 10) * 0.022,
                    top if math.isinf(v) else v,
                    color=COLOR[m],
                    marker="^" if math.isinf(v) else "o",
                    s=16,
                    alpha=0.8,
                )
            med = st.median(vv)
            if math.isfinite(med):
                ax.plot([j - 0.28, j + 0.28], [med, med], color="black", lw=1.6)
        ax.axhline(top, color="#888", ls=":", lw=0.7)
        ax.text(-0.55, top, "∞", va="bottom", fontsize=12)
        ax.set(
            yscale="log",
            title=f"Budget B={b}",
            xticks=range(len(GRID)),
            xticklabels=[AXIS_LABEL[m] for m in GRID],
            ylabel="Empirical TTS99 (s)",
        )
        ax.tick_params(axis="x", labelsize=9)
        plt.setp(ax.get_xticklabels(), rotation=35, ha="right", rotation_mode="anchor")
        ax.grid(axis="y", alpha=0.2)
    fig.legend(
        handles=handles(GRID), loc="lower center", ncol=3, frameon=False, fontsize=9.8
    )
    fig.tight_layout(rect=(0, 0.17, 1, 1))
    save(fig, "figure_D_grid_tts99")
    dump(out / "grid_figure_values.json", checks)
