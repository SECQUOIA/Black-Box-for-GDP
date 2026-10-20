"""Render all eight figures from saved data; no objective or solver calls."""

import math
import subprocess
import sys

from common import DATA, GRID, PROCESS, ROOT, METHODS, read_json, rows, write_json


def generate(output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np

    output.mkdir(parents=True, exist_ok=True)
    # Supplied manuscript renderers retain their display conventions.
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "reproduction/renderers/figures_2_6_7.py"),
            "--repository",
            str(ROOT),
            "--output",
            str(output.parent),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "reproduction/renderers/figure8.py"),
            "--input",
            str(PROCESS / "run_results.csv"),
            "--output",
            str(output),
        ],
        check=True,
    )
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "pdf.fonttype": 42,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    def save(fig, name):
        fig.savefig(
            output / f"{name}.pdf",
            bbox_inches="tight",
            metadata={"CreationDate": None, "ModDate": None},
        )
        fig.savefig(output / f"{name}.png", dpi=170, bbox_inches="tight")
        plt.close(fig)

    checks = {}
    # Figure 1: use the frozen normalized response, not a new analytic evaluation.
    grid = rows(ROOT / "benchmark_grids/rosenbrock.csv")
    inv = next(
        r
        for r in read_json(DATA / "supporting_data/grid_inventory.json")
        if r["name"] == "rosenbrock"
    )
    z = np.empty((31, 31))
    for r in grid:
        z[int(r["y"]), int(r["x"])] = float(r["z_norm"])
    x = np.linspace(-2, 2, 31)
    y = np.linspace(-1, 3, 31)
    fig, ax = plt.subplots(figsize=(5.6, 5.5))
    mesh = ax.pcolormesh(
        x,
        y,
        np.log10(1 + z / 1e-5),
        shading="nearest",
        edgecolors=(1, 1, 1, 0.35),
        linewidth=0.2,
        cmap="viridis",
        rasterized=True,
    )
    ticks = np.array([0, 1e-4, 1e-3, 0.01, 0.1, 1])
    colorbar = fig.colorbar(
        mesh,
        ax=ax,
        ticks=np.log10(1 + ticks / 1e-5),
        orientation="horizontal",
        pad=0.14,
        fraction=0.04,
    )
    colorbar.ax.set_xticklabels(
        ["0", r"$10^{-4}$", r"$10^{-3}$", r"$10^{-2}$", r"$10^{-1}$", "1"]
    )
    colorbar.set_label("Normalized objective F")
    # Both near-equal Rosenbrock lattice minima are identified by the stated target rule.
    points = inv["target_points"]
    ax.scatter(
        [x[i] for i, j in points],
        [y[j] for i, j in points],
        marker="D",
        facecolor="white",
        edgecolor="black",
        s=40,
    )
    ax.set(
        xlabel="Physical coordinate x",
        ylabel="Physical coordinate y",
        title="Discrete objective landscape",
        aspect="equal",
    )
    save(fig, "grid_rosenbrock_landscape")
    checks["figure1"] = {
        "target_indices": points,
        "normalized_values": z.tolist(),
        "interpolation": False,
    }
    colors = dict(zip(METHODS, ["#1976b9", "#e77818", "#27952a", "#9467bd"]))
    labels = dict(zip(METHODS, ["DSDA", "RBFOpt", "BAM", "FMQA-SA"]))
    styles = dict(zip(METHODS, ["-", "--", "-.", ":"]))
    markers = dict(zip(METHODS, ["o", "s", "^", "D"]))
    handles = [
        Line2D(
            [],
            [],
            color=colors[m],
            ls=styles[m],
            marker=markers[m],
            ms=3,
            label=labels[m],
        )
        for m in METHODS
    ]
    gr = rows(GRID / "runs.csv")
    fig, axes = plt.subplots(2, 3, figsize=(8.2, 5.4), sharey=True)
    checks["figure3"] = []
    for ax, budget in zip(axes.flat, [10, 30, 50, 70, 100]):
        selected = [r for r in gr if int(r["max_evals"]) == budget]
        right = max(float(r["estimated_total_s"]) for r in gr) * 1.2
        for m in METHODS:
            rr = [r for r in selected if r["method"] == m]
            values = [
                float(r["estimated_total_s"]) for r in rr if r["target_hit"] == "True"
            ]
            xs = sorted({0.1, right, *values})
            ys = [sum(v <= t for v in values) / len(rr) for t in xs]
            ax.step(
                xs,
                ys,
                where="post",
                color=colors[m],
                ls=styles[m],
                marker=markers[m],
                ms=2,
                markevery=max(1, len(xs) // 6),
            )
            checks["figure3"].append(
                dict(budget=budget, method=m, x=xs, y=ys, n=len(rr))
            )
        ax.set(
            xscale="log",
            xlim=(0.1, right),
            ylim=(-0.015, 1.025),
            title=f"Evaluation budget B={budget}",
            xlabel="Estimated full-run completion\ntime (s; log scale)",
        )
        ax.grid(alpha=0.25)
    axes.flat[-1].axis("off")
    axes.flat[-1].legend(handles=handles, frameon=False)
    for ax in axes[:, 0]:
        ax.set_ylabel("Fraction reaching target")
    fig.tight_layout()
    save(fig, "figure_C_grid_completion_profiles")
    sys.path.insert(0, str(ROOT / "scripts"))
    from analyze_grid_gdp_paths import load_tts99_groups
    from tts_figure import plot_tts99

    groups = load_tts99_groups(GRID / "tts99_summary.csv")
    fig = plot_tts99(groups)
    save(fig, "figure_D_grid_tts99")
    checks["figure4"] = [
        {
            k: ("infinity" if isinstance(v, float) and math.isinf(v) else v)
            for k, v in g.items()
            if k != "values"
        }
        for g in groups
    ]
    pr = rows(PROCESS / "run_results.csv")
    panels = [("column", 16), ("cstr_30", 43), ("small_batch", 10)] + [
        ("dynamic", b) for b in (12, 15, 20, 30, 37, 50)
    ]
    checks["figure5"] = []
    fig, axes = plt.subplots(3, 3, figsize=(8.2, 7.3))
    for ax, (case, budget) in zip(axes.flat, panels):
        for m in METHODS:
            rr = [
                r
                for r in pr
                if r["case"] == case and int(r["budget"]) == budget and r["method"] == m
            ]
            xs = list(range(1, budget + 1))
            ys = [
                sum(
                    r["category"] == "target_reached"
                    and float(r["first_hit_callback"]) <= t
                    for r in rr
                )
                / len(rr)
                for t in xs
            ]
            ax.step(
                xs,
                ys,
                where="post",
                color=colors[m],
                ls=styles[m],
                marker=markers[m],
                ms=2,
                markevery=max(1, budget // 5),
            )
            checks["figure5"].append(
                dict(case=case, budget=budget, method=m, x=xs, y=ys, n=len(rr))
            )
        ax.axvline(3, color="#707070", ls="--", lw=0.8)
        ax.set(
            title=f"{case.replace('_', ' ').title()} (B={budget})",
            xlabel="Charged evaluations",
            ylabel="Target-hit fraction",
            ylim=(-0.03, 1.05),
        )
        ax.grid(alpha=0.25)
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, "process_evaluation_profiles")
    write_json(output.parent / "additional_figure_values.json", checks)
    return sorted(str(p.relative_to(output.parent)) for p in output.glob("*.pdf"))
