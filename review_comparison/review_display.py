"""Apply presentation comments to retained DFO records; never run optimizers."""

import argparse
import csv
import json
import math
from pathlib import Path
import platform
import statistics

from . import grid_presentation as grid
from . import manuscript as m
from .joint_process import CONDITIONS, METHODS

BASE_REVISION = "a1bf5ea97ba2da528fedf330682c629b62e688e8"
TABLE_CONDITIONS = [("column", 13)] + CONDITIONS[:6] + [("small_batch", 10)] + CONDITIONS[8:]
PLOT_ORDER = ["bam", m.PRE, "dsda", "fmqa_sa", m.GEN, m.UNI]


def process_rows(directory):
    # grid.load_inputs verifies this same file against the archived manifest.
    manifest = json.loads((directory / "manifest.json").read_text())
    path = directory / "tables/run_records.csv"
    grid.require(m.sha(path) == manifest["outputs_sha256"]["tables/run_records.csv"],
                 "Process input hash mismatch")
    rows = [dict(r) for r in m.read(path) if r["scope"] == "process" and r["method"] in METHODS]
    for r in rows:
        r["budget"], r["seed"] = int(r["budget"]), int(r["seed"])
        r["search_s"] = float(r["search_s"])
        r["success"] = r["category"] == "target_reached"
        grid.require((r["hit"] == "True") == r["success"], "Process hit status mismatch")
    validate_process(rows)
    return rows


def validate_process(rows):
    keys = [(r["case"], r["budget"], r["seed"], r["method"]) for r in rows]
    expected = {(case, budget, seed, method) for case, budget in CONDITIONS
                for seed in range(10) for method in METHODS}
    grid.require(len(keys) == len(set(keys)) and set(keys) == expected,
                 "Missing, duplicate, or unexpected process run")
    grid.require(all(math.isfinite(r["search_s"]) and r["search_s"] >= 0 for r in rows),
                 "Invalid process search time")


def process_summary(rows):
    validate_process(rows)
    result = []
    for case, budget in TABLE_CONDITIONS:
        for method in METHODS:
            group = sorted((r for r in rows if
                            (r["case"], r["budget"], r["method"]) == (case, budget, method)),
                           key=lambda r: r["seed"])
            q = statistics.quantiles([r["search_s"] for r in group], n=4, method="inclusive")
            result.append(dict(case=case, budget=budget, method=method, runs=len(group),
                               target_hits=sum(r["success"] for r in group),
                               search_q25_s=q[0], search_q50_s=q[1], search_q75_s=q[2]))
    return result


def process_table(summary):
    lines = []
    for case, budget in TABLE_CONDITIONS:
        group = [r for r in summary if (r["case"], r["budget"]) == (case, budget)]
        best = max(r["target_hits"] for r in group)
        cells = []
        for method in METHODS:
            r = next(r for r in group if r["method"] == method)
            hits = str(r["target_hits"])
            if r["target_hits"] == best:
                hits = r"\textbf{" + hits + "}"
            times = [format(r[f"search_q{q}_s"], ".3g") for q in (25, 50, 75)]
            cells.append(r"\makecell{" + hits + r"\\" + times[1] +
                         r"\\{[" + times[0] + ", " + times[2] + "]}}")
        name = "CSTR" + case[5:] if case.startswith("cstr_") else m.pname(case)
        lines.append(" & ".join([r"\texttt{" + name + "}", str(budget), *cells]) + r" \\")
    return "\n".join(lines) + "\n"


def grid_table(rows):
    lines = []
    for budget in m.BUDGETS:
        hits = [sum(r["hit"] for r in rows if r["budget"] == budget and r["method"] == method)
                for method in m.GRID]
        best = max(hits)
        values = [f"{n / 210 * 100:.1f}" for n in hits]
        values = [r"\textbf{" + v + "}" if n == best else v for n, v in zip(hits, values)]
        lines.append(" & ".join([str(budget), *values]) + r" \\")
    return "\n".join(lines) + "\n"


def render(curves, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MultipleLocator

    colors = dict(m.COLOR)
    styles = dict(m.STYLE)
    styles["bam"] = "-"
    styles[m.PRE] = (0, (5, 2, 1, 2))
    markers = dict(m.MARK)
    markers[m.PRE] = "v"
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10.5,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42}):
        fig, ax = plt.subplots(figsize=(6.5, 3.7))
        # Draw the thin prefix last so that BAM remains visible through the gaps
        # where the two methods have identical curve coordinates.
        for method in [k for k in PLOT_ORDER if k != m.PRE] + [m.PRE]:
            c = next(c for c in curves if c["budget"] == 100 and c["method"] == method)
            stride = max(1, len(c["x"]) // 9)
            ax.step(c["x"], c["y"], where="post", color=colors[method], ls=styles[method],
                    lw=2.3 if method == "bam" else 1.25 if method == m.PRE else 1.6,
                    marker=markers[method], ms=5 if method in ("bam", m.PRE) else 4,
                    markerfacecolor="white" if method == m.PRE else colors[method],
                    markeredgewidth=1.0,
                    markevery=(stride // 2 if method == m.PRE else 0, stride),
                    label=m.LABEL[method])
        ax.axvline(3, color="#999999", ls="--", lw=.8, zorder=0)
        ax.set(xlim=(0, 100), ylim=(-.015, 1.0), xticks=list(range(0, 101, 10)),
               yticks=[0, .2, .4, .6, .8, 1], xlabel="Configuration evaluations",
               ylabel="Fraction of runs reaching target")
        ax.xaxis.set_minor_locator(MultipleLocator(5))
        ax.grid(axis="y", alpha=.18)
        handles = [Line2D([], [], color=colors[k], ls=styles[k], marker=markers[k],
                          markerfacecolor="white" if k == m.PRE else colors[k],
                          ms=5, lw=2.3 if k == "bam" else 1.25 if k == m.PRE else 1.6,
                          label=m.LABEL[k]) for k in PLOT_ORDER]
        fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False,
                   fontsize=9.5, handlelength=3.5, columnspacing=1.5)
        fig.tight_layout(rect=(0, 0, 1, .85), pad=.5)
        name = out / "figure_B_grid_evaluation_profiles"
        fig.savefig(name.with_suffix(".pdf"), bbox_inches="tight", pad_inches=.03,
                    metadata={"CreationDate": None, "ModDate": None})
        fig.savefig(name.with_suffix(".png"), dpi=180, bbox_inches="tight", pad_inches=.03)
        plt.close(fig)


def build(directory, out):
    grid_rows, all_curves = grid.load_inputs(directory)
    rows = process_rows(directory)
    summary = process_summary(rows)
    curves = [c for c in all_curves if c["budget"] == 100]
    grid.require(not out.exists() or not any(out.iterdir()), "Output directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    (out / "grid_hits.tex").write_text(grid_table(grid_rows))
    (out / "process_hits_search.tex").write_text(process_table(summary))
    with (out / "process_search_quartiles.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)
    m.dump(out / "grid_B100_curve_values.json", curves)
    render(curves, out)
    (out / "README.md").write_text("""# Review presentation follow-up

This update addresses the Grid hit-table, Figure 1 distinction, and process search-time comments using completed DFO records only.
No optimizer, NLP solver, training, or server experiment is run.
The archived input manifest and data remain unchanged.

The input is `results/dsda_publication_20261028/tables/run_records.csv`.
Input SHA256 is checked against its archived manifest before use.
All 6,300 primary Grid runs and all 30 archived curves are checked before selecting the six B=100 curves for Figure 1.
The separate five-budget Grid table retains its original percentages and highlights all row maxima, including ties.
Figure 1 has no internal title and preserves every B=100 curve coordinate.
BAM uses a thicker bluish-green solid line and filled triangles; its prefix control uses a thinner sky-blue dash-dot line and open downward triangles (Okabe-Ito colors).
The overlap is not displaced, and staggered markers help reveal both methods where their curves coincide.

The process table uses exactly 700 current DFO runs: 14 case-budget conditions, five methods, and seeds 0--9 in every group.
Historical RBFOpt solver-mode records are excluded.
Missing, duplicate, unexpected, nonfinite, or negative-time records cause an error.
Each table cell reports target hits, Q50 search time, and [Q25, Q75] in seconds.
All ten seeds remain in each summary, including target misses or execution failures if present.
Search time is the stored `search_s`, which excludes lookup processing and configuration-evaluation costs.
It retains candidate-selection overhead, including surrogate subsolver calls where applicable.
Quartiles use inclusive linear interpolation at rank (n-1)p and are descriptive seed variability, not confidence intervals.
Conditions are summarized separately, including the six Dynamic budgets.
Displayed times use three significant digits; the CSV retains full precision.
Only target-hit maxima are bold, and ties are retained.

Reproduce from the repository root:

```sh
python -m review_comparison.review_display --output /tmp/review-display-replay
```

Overleaf remains the manuscript source of truth.
The TeX outputs are table-row fragments for localized edits, not replacement manuscript files.
""")
    import matplotlib
    files = sorted(p for p in out.iterdir() if p.is_file())
    sources = [Path(__file__), Path(grid.__file__), m.ROOT / "review_comparison/manuscript.py",
               m.ROOT / "review_comparison/joint_process.py"]
    m.dump(out / "manifest.json", {
        "baseline_revision": BASE_REVISION,
        "no_new_experiments": True,
        "input_sha256": {str((directory / n).relative_to(m.ROOT)): m.sha(directory / n)
                         for n in ["manifest.json", *grid.INPUTS]},
        "source_sha256": {str(p.relative_to(m.ROOT)): m.sha(p) for p in sources},
        "outputs_sha256": {p.name: m.sha(p) for p in files},
        "process_runs": 700, "process_conditions": 14, "process_seeds": list(range(10)),
        "process_methods": METHODS,
        "quartiles": "inclusive linear interpolation at rank (n-1)p, all ten seeds",
        "execution_provider_revisions": "Unchanged; see the archived input manifest",
        "environment": {"python": platform.python_version(), "matplotlib": matplotlib.__version__},
        "reproduce": "python -m review_comparison.review_display --output /tmp/review-display-replay",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=grid.BASE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.input.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
