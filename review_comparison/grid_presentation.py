"""Clarify the Grid figure and report cost quartiles from completed records only."""

import argparse
import csv
import json
import math
from pathlib import Path
import platform
import statistics

from . import manuscript as m

BASE = m.ROOT / "results/dsda_publication_20261028"
REVISION = "49d4bcbeb10fe49b74fe2333d27829046e93bf03"
INPUTS = ["tables/run_records.csv", "figures/grid_figure_values.json"]
METRICS = ["total_s", "point_cost_s", "search_s"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_inputs(directory=BASE):
    manifest = json.loads((directory / "manifest.json").read_text())
    for name in INPUTS:
        require(m.sha(directory / name) == manifest["outputs_sha256"][name],
                f"Input hash mismatch: {name}")
    rows = []
    for raw in m.read(directory / INPUTS[0]):
        if raw["scope"] != "grid" or raw["method"] not in m.GRID:
            continue
        r = dict(raw)
        for k in ("budget", "seed", "evaluations"):
            r[k] = int(r[k])
        for k in METRICS:
            r[k] = float(r[k])
        r["hit"] = r["category"] == "target_reached"
        require((raw["hit"] == "True") == r["hit"], "Success status mismatch")
        r["first_hit"] = int(r["first_hit"]) if r["first_hit"] else None
        rows.append(r)
    curves = [r for r in json.loads((directory / INPUTS[1]).read_text())
              if r["axis"] == "first_hit"]
    validate(rows, curves)
    return rows, curves


def validate(rows, curves):
    cases = {r["case"] for r in rows}
    require(len(cases) == 21, "Expected exactly 21 Grid functions")
    expected = {(c, b, s, method) for c in cases for b in m.BUDGETS
                for s in range(10) for method in m.GRID}
    keys = [(r["case"], r["budget"], r["seed"], r["method"]) for r in rows]
    require(len(keys) == len(set(keys)) and set(keys) == expected,
            "Missing, duplicate, or unexpected Grid run")
    for r in rows:
        require(all(math.isfinite(r[k]) and r[k] >= 0 for k in METRICS),
                "Invalid full-run cost")
        require(not r["hit"] or
                (r["first_hit"] is not None and 1 <= r["first_hit"] <= r["budget"]),
                "Invalid first-target evaluation")
    curve_keys = [(c["budget"], c["method"]) for c in curves]
    require(len(curve_keys) == len(set(curve_keys)) == 30 and
            set(curve_keys) == {(b, method) for b in m.BUDGETS for method in m.GRID},
            "Missing or duplicate archived curve")
    for c in curves:
        rr = [r for r in rows if r["budget"] == c["budget"] and r["method"] == c["method"]]
        hits = [r["first_hit"] for r in rr if r["hit"]]
        xs = sorted({0, c["budget"], *hits})
        ys = [sum(v <= x for v in hits) / 210 for x in xs]
        require(c["n"] == 210 and c["hits"] == len(hits) and
                c["x"] == xs and c["y"] == ys, "Archived curve does not match run records")


def cost_quartiles(rows):
    result = []
    for method in m.GRID:
        rr = [r for r in rows if r["budget"] == 100 and r["method"] == method]
        require(len(rr) == 210, "Cost summary requires all 210 runs")
        row = dict(method=method, runs=len(rr), target_hits=sum(r["hit"] for r in rr))
        for metric in METRICS:
            quartiles = statistics.quantiles([r[metric] for r in rr], n=4, method="inclusive")
            row.update({f"{metric}_q{q}": v for q, v in zip((25, 50, 75), quartiles)})
        result.append(row)
    return result


def table_rows(summary):
    def cell(r, metric):
        digits = 4 if metric == "search_s" and r[f"{metric}_q50"] < .01 else 2
        values = [f"{r[f'{metric}_q{q}']:.{digits}f}" for q in (25, 50, 75)]
        return r"\shortstack{" + values[1] + r"\\{[" + values[0] + ", " + values[2] + "]}}"
    lines = []
    for r in summary:
        label = (r"\texttt{BAM}-prefix control" if r["method"] == m.PRE else
                 "Uniform" if r["method"] == m.UNI else r"\texttt{" + m.LABEL[r["method"]] + "}")
        lines.append(" & ".join([label, f"{r['target_hits']}/{r['runs']}",
                                  *(cell(r, k) for k in METRICS)]) + r" \\")
    return "\n".join(lines) + "\n"


def render(curves, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.titlesize": 11, "axes.labelsize": 10.5,
                         "xtick.labelsize": 10, "ytick.labelsize": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42}):
        fig, axs = plt.subplots(2, 3, figsize=(8.2, 5.8), sharey=True)
        for ax, budget in zip(axs.flat, m.BUDGETS):
            for method in m.GRID:
                c = next(c for c in curves if c["budget"] == budget and c["method"] == method)
                ax.step(c["x"], c["y"], where="post", color=m.COLOR[method],
                        ls=m.STYLE[method], lw=1.6, marker=m.MARK[method], ms=3.5,
                        markevery=max(1, len(c["x"]) // 5))
            ax.axvline(3, color="#777777", ls="--", lw=.8)
            ax.set(title=f"Budget B={budget}", ylim=(-.02, 1.03), yticks=[0, .5, 1],
                   xlim=(0, budget), xlabel="Configuration evaluations",
                   xticks=[0, budget // 2, budget])
            ax.grid(axis="y", alpha=.2)
        for ax in axs[:, 0]:
            ax.set_ylabel("Fraction of runs\nreaching target")
        axs.flat[-1].axis("off")
        handles = [Line2D([], [], color=m.COLOR[k], ls=m.STYLE[k], marker=m.MARK[k],
                          ms=4, lw=1.5, label=m.LABEL[k]) for k in m.GRID]
        axs.flat[-1].legend(handles=handles, loc="upper left", frameon=False, fontsize=10)
        fig.suptitle(r"Grid-GDP: target $|F-0|\leq 10^{-5}$", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, .95), h_pad=1.8, w_pad=.8)
        name = out / "figure_B_grid_evaluation_profiles"
        fig.savefig(name.with_suffix(".pdf"), bbox_inches="tight", pad_inches=.04,
                    metadata={"CreationDate": None, "ModDate": None})
        fig.savefig(name.with_suffix(".png"), dpi=160, bbox_inches="tight", pad_inches=.04)
        plt.close(fig)


def build(directory, out):
    rows, curves = load_inputs(directory)
    require(not out.exists() or not any(out.iterdir()), "Output directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    summary = cost_quartiles(rows)
    with (out / "grid_cost_quartiles.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)
    (out / "grid_cost_rows.tex").write_text(table_rows(summary))
    m.dump(out / "grid_evaluation_curve_values.json", curves)
    render(curves, out)
    table = "\n".join(f"| {m.LABEL[r['method']]} | {r['target_hits']}/210 | " +
                       " | ".join(f"{r[k + '_q50']:.4f} [{r[k + '_q25']:.4f}, {r[k + '_q75']:.4f}]"
                                  for k in METRICS) + " |" for r in summary)
    (out / "README.md").write_text("""# Grid figure and cost quartiles

This is a presentation update using completed experiments; no searches or solvers are run.
The input is the archived D-SDA publication analysis from 28 October 2026.
Its input hashes, all 6,300 primary Grid run slots, and all 30 evaluation curves are verified before rendering.
The figure retains every archived curve coordinate and method style, labels configuration evaluations and the target explicitly, and removes the prefix shading and legend notes.
The target is agreement with the normalized reference zero within an absolute tolerance of 1e-5.

The cost table uses all 210 runs per method at B=100, including target misses.
Entries are Q50 [Q25, Q75] in seconds, computed separately for each component by inclusive linear interpolation at ranks (n-1)p.
Summed configuration-evaluation cost includes every callback along the full recorded path, with the original stored costs unchanged.
These quartiles describe variation across 21 functions and ten seeds, not confidence intervals or repeated timing measurements.
Component quartiles need not sum to the completion quartiles.

| Method | Targets | Full-run completion | Summed configuration evaluation | Retained search |
| --- | --- | --- | --- | --- |
""" + table + "\n\nReproduce from the repository root:\n\n```sh\npython -m review_comparison.grid_presentation --input results/dsda_publication_20261028 --output /tmp/grid-presentation\n```\n")
    import matplotlib
    files = sorted(p for p in out.iterdir() if p.is_file())
    m.dump(out / "manifest.json", {
        "baseline_revision": REVISION,
        "no_new_experiments": True,
        "execution_provenance": "Unchanged; see the input analysis manifest and its execution_records",
        "input_sha256": {str((directory / n).relative_to(m.ROOT)): m.sha(directory / n)
                         for n in ["manifest.json", *INPUTS]},
        "source_sha256": {str(p.relative_to(m.ROOT)): m.sha(p)
                          for p in [Path(__file__), m.ROOT / "review_comparison/manuscript.py"]},
        "outputs_sha256": {p.name: m.sha(p) for p in files},
        "environment": {"python": platform.python_version(), "matplotlib": matplotlib.__version__,
                        "platform": platform.platform()},
        "quartiles": {"probabilities": [.25, .5, .75], "method": "inclusive linear interpolation",
                      "runs_per_method": 210, "include_target_misses": True},
        "curve_verification": "All 30 curves exactly equal archived x/y arrays and match run records",
        "reproduction_command": "python -m review_comparison.grid_presentation --input results/dsda_publication_20261028 --output /tmp/grid-presentation",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.input.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
