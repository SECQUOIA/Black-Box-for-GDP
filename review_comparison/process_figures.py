"""Process-only rendering using the retained publication style.

Separated from the historical generator so archived analyses remain unchanged.
"""
import statistics as st

from .manuscript import (
    PRIMARY, LABEL, AXIS_LABEL, COLOR, STYLE, MARK, pname,
    label_dynamic_cost_axis, dump,
)


def figures(groups, out, panels, cost_panels):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
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
        ("first_hit", "process_evaluation_profiles"),
        ("total_s", "process_completion_profiles"),
    ]:
        fig, axs = plt.subplots(3, 3, figsize=(8.2, 8))
        for ax, (c, b) in zip(axs.flat, panels):
            for m in PRIMARY:
                profile(ax, groups["process", c, b, m], m, key, 10, b)
            ax.set(title=f"{pname(c)} (B={b})", ylim=(-0.03, 1.04), yticks=[0, 0.5, 1])
            if key == "first_hit":
                ax.axvline(3, color="#777", ls="--", lw=0.8)
                ax.set(xlim=(0, b), xlabel="Charged evaluations")
                ax.set_xticks([0, b // 2, b])
            else:
                ax.set(xscale="log", xlabel="Completion cost (s)")
                ax.xaxis.set_major_locator(LogLocator(numticks=3))
                ax.xaxis.set_minor_formatter(NullFormatter())
                if c == "dynamic" and b in (30, 37):
                    label_dynamic_cost_axis(ax, "x")
            ax.grid(axis="y", alpha=0.2)
        for ax in axs[:, 0]:
            ax.set_ylabel("Target-hit fraction")
        fig.legend(
            handles=handles(PRIMARY),
            loc="lower center",
            ncol=3,
            frameon=False,
            fontsize=10,
        )
        fig.tight_layout(rect=(0, 0.085, 1, 1), h_pad=1.5, w_pad=1)
        save(fig, name)
    fig, axs = plt.subplots(2, 2, figsize=(8.2, 6))
    components = [
        ("#5086ad", "///", "Search"),
        ("#c2c7cc", "", "Point evaluations"),
        ("#b58fc4", "xx", "Preparation"),
    ]
    for ax, (c, b) in zip(
        axs.flat,
        cost_panels,
    ):
        for j, m in enumerate(PRIMARY):
            rr = groups["process", c, b, m]
            v = [
                st.mean(r[k] for r in rr)
                for k in ("search_s", "point_cost_s", "prep_s")
            ]
            total = sum(v)
            bottom = 0
            for value, (color, hatch, _) in zip(v, components):
                pct = 100 * value / total
                ax.bar(
                    j,
                    pct,
                    bottom=bottom,
                    color=color,
                    hatch=hatch,
                    edgecolor="#444",
                    lw=0.4,
                    width=0.7,
                )
                if pct >= 8:
                    ax.text(
                        j,
                        bottom + pct / 2,
                        f"{pct:.0f}%",
                        ha="center",
                        va="center",
                        fontsize=9.5,
                    )
                bottom += pct
            ax.text(j, 103, f"{total:.1f}", ha="center", fontsize=10)
            checks.append(
                dict(
                    scope="process",
                    case=c,
                    budget=b,
                    method=m,
                    mean_total=total,
                    mean_components=v,
                )
            )
        ax.set(
            title=f"{pname(c)} (B={b})",
            ylim=(0, 128),
            yticks=[0, 50, 100],
            xticks=range(5),
            xticklabels=[AXIS_LABEL[m] for m in PRIMARY],
            ylabel="Share of mean total (%)",
        )
        ax.text(
            0.5,
            0.96,
            "Mean total (s)",
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=10,
        )
    fig.legend(
        handles=[
            Patch(facecolor=c, hatch=h, label=label, edgecolor="#444")
            for c, h, label in components
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save(fig, "process_cost_breakdown")
    fig, axs = plt.subplots(3, 3, figsize=(8.2, 8.7))
    for ax, (c, b) in zip(axs.flat, panels):
        for j, m in enumerate(PRIMARY):
            rr = groups["process", c, b, m]
            for r in rr:
                ax.scatter(
                    j + (r["seed"] - 4.5) * 0.045,
                    r["total_s"],
                    color=COLOR[m],
                    marker="s"
                    if r["category"] == "execution_failed"
                    else "o"
                    if r["hit"]
                    else "x",
                    s=24,
                )
            med = st.median(r["total_s"] for r in rr)
            ax.plot([j - 0.3, j + 0.3], [med, med], color="black", lw=1.2)
        ax.set(
            title=f"{pname(c)} (B={b})",
            yscale="log",
            xticks=range(5),
            xticklabels=[AXIS_LABEL[m] for m in PRIMARY],
        )
        ax.tick_params(axis="x", labelsize=9)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
        ax.yaxis.set_major_locator(LogLocator(numticks=3))
        ax.yaxis.set_minor_formatter(NullFormatter())
        if c == "dynamic" and b in (30, 37):
            label_dynamic_cost_axis(ax, "y")
        ax.grid(axis="y", alpha=0.2)
    for ax in axs[:, 0]:
        ax.set_ylabel("Completion cost (s)")
    fig.legend(
        handles=[
            Line2D([], [], color="black", marker=mk, ls="", label=lab)
            for mk, lab in [
                ("o", "Target hit"),
                ("x", "Target miss"),
                ("s", "Execution failure"),
            ]
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1), h_pad=1.8)
    save(fig, "process_completion_scatter")
    dump(out / "figure_values.json", checks)
