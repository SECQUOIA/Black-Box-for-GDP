"""Generate publication figures and tables from retained runs; never run optimizers."""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
import platform
import sys
from pathlib import Path
import statistics as st
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/review_comparison_20261020"
ARCHIVE = (
    ROOT
    / "results/archives/review_comparison_20261020_124949_return_1792527395393579314.zip"
)
GEN = "rbfopt_msrsm_genetic"
SOL = "rbfopt_msrsm_solver"
UNI = "uniform_without_replacement"
PRE = "bam_predetermined_uniform"
PRIMARY = ["dsda", GEN, "bam", "fmqa_sa", UNI]
GRID = PRIMARY + [PRE]
ALL = GRID + [SOL]
BUDGETS = [10, 30, 50, 70, 100]
CONDITIONS = (
    [("column", 16)]
    + [
        (f"cstr_{n}", b)
        for n, b in zip([5, 10, 15, 20, 25, 30], [8, 15, 22, 29, 36, 43])
    ]
    + [("small_batch", 10)]
    + [("dynamic", b) for b in [12, 15, 20, 30, 37, 50]]
)
PANELS = [("column", 16), ("cstr_30", 43), ("small_batch", 10)] + [
    ("dynamic", b) for b in [12, 15, 20, 30, 37, 50]
]
LABEL = dict(
    zip(
        ALL,
        [
            "D-SDA",
            "RBFOpt",
            "BAM",
            "FMQA-SA",
            "Uniform",
            "BAM-prefix control",
            "RBFOpt (solver)",
        ],
    )
)
AXIS_LABEL = dict(LABEL)
AXIS_LABEL[PRE] = "BAM-prefix\ncontrol"
COLOR = dict(
    zip(
        ALL,
        ["#1976b9", "#df710c", "#238b45", "#9063b8", "#555555", "#008b8b", "#b05d43"],
    )
)
STYLE = dict(zip(ALL, ["-", "--", "-.", ":", (0, (5, 2)), (0, (1, 1)), "--"]))
MARK = dict(zip(ALL, ["o", "s", "^", "D", "x", "v", "+"]))


def read(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def csvwrite(path, rows):
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def pname(c):
    return (
        "CSTR " + c.split("_")[1]
        if c.startswith("cstr_")
        else {
            "column": "Column",
            "small_batch": "Small Batch",
            "dynamic": "Dynamic",
        }.get(c, c.replace("_", " ").title())
    )


def process_pair(groups, case, budget, new, reference):
    """Summarize one complete, seed-paired Process condition without pooling."""
    from .analysis import paired_interval

    pairs = []
    for method in (new, reference):
        records = groups["process", case, budget, method]
        by_seed = {r["seed"]: r["hit"] for r in records}
        if len(records) != 10 or set(by_seed) != set(range(10)):
            raise ValueError(f"Incomplete or duplicate paired seeds: {case}, {budget}, {method}")
        pairs.append(by_seed)
    a, b = pairs
    differences = [int(a[s]) - int(b[s]) for s in range(10)]
    low, high = paired_interval([differences], seed=20261020, replications=2000, clustered=False)
    return dict(
        scope="process", case=case, budget=budget, new=new, reference=reference,
        pairs=10, both_success=sum(a[s] and b[s] for s in range(10)),
        new_only_success=sum(a[s] and not b[s] for s in range(10)),
        reference_only_success=sum(not a[s] and b[s] for s in range(10)),
        neither_success=sum(not a[s] and not b[s] for s in range(10)),
        difference=st.mean(differences), low=low, high=high,
        bootstrap_seed=20261020, bootstrap_replications=2000,
        bootstrap_unit="paired seeds within this condition",
    )


def label_dynamic_cost_axis(ax, axis):
    """Label intermediate seconds in the narrow B30/B37 logarithmic panels."""
    from matplotlib.ticker import FixedLocator, FuncFormatter

    limits = ax.get_xlim() if axis == "x" else ax.get_ylim()
    ticks = [v for v in (10, 15, 20, 30, 40, 50, 60, 80, 100) if limits[0] <= v <= limits[1]]
    target = ax.xaxis if axis == "x" else ax.yaxis
    target.set_major_locator(FixedLocator(ticks))
    target.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))


def load():
    manifest = json.loads((BASE / "manifest.json").read_text())
    assert sha(ARCHIVE) == manifest["return_archive"]["sha256"]
    p = BASE / "tables/completed_runs.csv"
    assert sha(p) == manifest["published_files_sha256"]["tables/completed_runs.csv"]
    rows = read(p)
    index = {}
    for r in rows:
        for k in ("budget", "seed", "evaluations"):
            r[k] = int(r[k])
        for k in ("search_s", "point_cost_s", "prep_s"):
            r[k] = float(r[k])
        r["total_s"] = r["search_s"] + r["point_cost_s"] + r["prep_s"]
        r["hit"] = r["category"] == "target_reached"
        r["first_hit"] = None
        key = tuple(r[k] for k in ("scope", "case", "budget", "seed", "method"))
        assert key not in index
        index[key] = r
    for r in read(ROOT / "results/grid_gdp_dfo_20261011/runs.csv"):
        m = SOL if r["method"] == "rbfopt" else r["method"]
        q = index["grid", r["grid_name"], int(r["max_evals"]), int(r["seed"]), m]
        q["first_hit"] = int(float(r["first_hit_evaluation"])) if q["hit"] else None
    for r in read(
        ROOT / "results/process_ipopt_bam_v2_20261015/tables/run_results.csv"
    ):
        m = SOL if r["method"] == "rbfopt" else r["method"]
        q = index["process", r["case"], int(r["budget"]), int(r["seed"]), m]
        q["first_hit"] = int(r["first_hit_callback"]) if q["hit"] else None
    terminals = []
    counts = defaultdict(int)
    with zipfile.ZipFile(ARCHIVE) as z:
        root = manifest["return_archive"]["root"]
        for r in rows:
            if r["method"] not in (GEN, UNI, PRE):
                continue
            directory = root + "/" + r["record_source"]
            result = json.loads(z.read(directory + "/result.json"))
            ev = [
                json.loads(line)
                for line in z.read(directory + "/evaluations.jsonl")
                .decode()
                .splitlines()
            ]
            assert len(ev) == r["evaluations"] == r["budget"]
            assert math.isclose(
                math.fsum(e["historical_point_cost_s"] for e in ev),
                r["point_cost_s"],
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            assert math.isclose(
                result["reconstructed_total_s"],
                r["total_s"],
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            hits = [
                e
                for e in ev
                if e["accepted"]
                and abs(e["raw_objective"] - result["target"])
                <= 1e-5 * max(1, abs(result["target"]))
            ]
            assert bool(hits) == r["hit"]
            r["first_hit"] = hits[0]["index"] if r["hit"] else None
            counts[r["scope"]] += len(ev)
            if r["scope"] == "process" and r["first_hit"] == r["budget"]:
                terminals.append(
                    {k: r[k] for k in ("case", "budget", "seed", "method")}
                    | {
                        "point": json.dumps(hits[0]["point"]),
                        "objective": hits[0]["raw_objective"],
                        "returned": hits[0]["value_returned_to_optimizer"],
                    }
                )
    assert len(rows) == 8190 and sum(counts.values()) == 170660
    groups = defaultdict(list)
    for r in rows:
        groups[r["scope"], r["case"], r["budget"], r["method"]].append(r)
        assert (r["first_hit"] is not None) == r["hit"]
    assert all(
        len(rr) == 10 and {r["seed"] for r in rr} == set(range(10))
        for rr in groups.values()
    )
    return rows, groups, terminals


def summarize(rr):
    n = len(rr)
    h = sum(r["hit"] for r in rr)
    med = st.median(r["total_s"] for r in rr)
    tts = (
        (
            med * (1 if h == n else math.ceil(math.log(0.01) / math.log1p(-h / n)))
            if h
            else math.inf
        )
        if n == 10
        else None
    )
    return dict(
        n=n,
        hits=h,
        rate=h / n,
        median=med,
        tts=tts,
        search=st.median(r["search_s"] for r in rr),
        point=st.median(r["point_cost_s"] for r in rr),
        callbacks=sum(r["evaluations"] for r in rr),
    )


def fmt(x):
    return r"\(\infty\)" if math.isinf(x) else f"{x:.2f}"


def tables(rows, groups, out):
    def interval(h):
        def root(tail, increasing):
            lo, hi = 0.0, 1.0
            for _ in range(60):
                p = (lo + hi) / 2
                val = sum(math.comb(10, k) * p**k * (1 - p) ** (10 - k) for k in tail)
                if (val < 0.025) == increasing:
                    lo = p
                else:
                    hi = p
            return (lo + hi) / 2

        lower = 0 if h == 0 else root(range(h, 11), True)
        upper = 1 if h == 10 else root(range(h + 1), False)
        return f"{h} [{lower:.2f}, {upper:.2f}]"

    def write(name, lines):
        (out / name).write_text("\n".join(lines) + "\n")

    lines = []
    for b in BUDGETS:
        cells = [
            f"{100 * sum(r['hit'] for r in rows if r['scope'] == 'grid' and r['budget'] == b and r['method'] == m) / 210:.1f}"
            for m in GRID
        ]
        lines.append(str(b) + " & " + " & ".join(cells) + r" \\")
    write("grid_hits.tex", lines)
    lines = []
    for m in GRID:
        s = summarize(
            [
                r
                for r in rows
                if r["scope"] == "grid" and r["budget"] == 100 and r["method"] == m
            ]
        )
        lines.append(
            f"{LABEL[m]} & {s['hits']}/210 & {s['median']:.2f} & {s['point']:.2f} & {s['search']:.4f}"
            + r" \\"
        )
    write("grid_cost.tex", lines)
    write(
        "rbfopt_process_variants.tex",
        [
            f"{pname(c)} & {b} & "
            + " & ".join(
                f"{summarize(groups['process', c, b, m])['hits']}/10 & {summarize(groups['process', c, b, m])['median']:.2f}"
                for m in (SOL, GEN)
            )
            + r" \\"
            for c, b in CONDITIONS
        ],
    )
    write(
        "rbfopt_grid_variants.tex",
        [
            str(b)
            + " & "
            + " & ".join(
                f"{summarize([r for r in rows if r['scope'] == 'grid' and r['budget'] == b and r['method'] == m])['hits']}/210 & {summarize([r for r in rows if r['scope'] == 'grid' and r['budget'] == b and r['method'] == m])['median']:.2f}"
                for m in (SOL, GEN)
            )
            + r" \\"
            for b in BUDGETS
        ],
    )
    write(
        "alpha_grid_B100.tex",
        [
            f"{alpha:g} & "
            + " & ".join(
                f"{st.median(r['search_s'] + alpha * r['point_cost_s'] + r['prep_s'] for r in rows if r['scope'] == 'grid' and r['budget'] == 100 and r['method'] == m):.2f}"
                for m in PRIMARY + [SOL]
            )
            + r" \\"
            for alpha in [0.01, 0.1, 1, 10, 100]
        ],
    )
    from .analysis import paired_interval

    paired = []
    for new, ref in [
        (GEN, SOL),
        (GEN, UNI),
        ("bam", PRE),
        ("fmqa_sa", UNI),
        ("dsda", GEN),
    ]:
        for scope in ("grid", "process"):
            for case, b in (
                [("all_grid_problems", b) for b in BUDGETS]
                if scope == "grid"
                else CONDITIONS
            ):
                cases = (
                    sorted({r["case"] for r in rows if r["scope"] == "grid"})
                    if scope == "grid"
                    else [case]
                )
                if any((scope, c, b, ref) not in groups for c in cases):
                    continue
                vectors = []
                for c in cases:
                    a = {r["seed"]: r["hit"] for r in groups[scope, c, b, new]}
                    d = {r["seed"]: r["hit"] for r in groups[scope, c, b, ref]}
                    vectors.append([int(a[s]) - int(d[s]) for s in range(10)])
                low, high = paired_interval(
                    vectors, seed=20261020, replications=2000, clustered=scope == "grid"
                )
                paired.append(
                    dict(
                        scope=scope,
                        case=case,
                        budget=b,
                        new=new,
                        reference=ref,
                        difference=st.mean(st.mean(v) for v in vectors),
                        low=low,
                        high=high,
                        problem_groups=len(cases),
                        seeds_per_group=10,
                    )
                )
    csvwrite(out / "paired_comparisons.csv", paired)
    selected_process = [
        process_pair(groups, "dynamic", 12, GEN, "dsda"),
        process_pair(groups, "small_batch", 10, "fmqa_sa", UNI),
    ]
    csvwrite(out / "paired_process_selected.csv", selected_process)
    write(
        "paired_process_selected.tex",
        [
            f"{pname(r['case'])} & {r['budget']} & {LABEL[r['new']]} -- {LABEL[r['reference']]} & "
            + "/".join(str(r[k]) for k in ("both_success", "new_only_success", "reference_only_success", "neither_success"))
            + f" & {100 * r['difference']:.0f} & [{100 * r['low']:.0f}, {100 * r['high']:.0f}]"
            + r" \\"
            for r in selected_process
        ],
    )
    write(
        "paired_grid.tex",
        [
            f"{r['budget']} & {LABEL[r['new']]} -- {LABEL[r['reference']]} & {100 * r['difference']:.2f} & [{100 * r['low']:.2f}, {100 * r['high']:.2f}]"
            + r" \\"
            for r in paired
            if r["scope"] == "grid" and r["budget"] in (10, 100)
        ],
    )
    for kind in ("hits", "cost", "tts", "intervals"):
        lines = []
        for c, b in CONDITIONS:
            cells = []
            for m in PRIMARY:
                s = summarize(groups["process", c, b, m])
                cell = (
                    f"{s['hits']}/10"
                    if kind == "hits"
                    else fmt(s["median" if kind == "cost" else "tts"])
                    if kind in ("cost", "tts")
                    else interval(s["hits"])
                )
                if kind == "hits" and m == "dsda" and c == "column":
                    cell += r"\textsuperscript{F1}"
                cells.append(cell)
            lines.append(f"{pname(c)} & {b} & " + " & ".join(cells) + r" \\")
        write("process_" + kind + ".tex", lines)
    names = sorted({r["case"] for r in rows if r["scope"] == "grid"})
    for b in BUDGETS:
        write(
            f"grid_intervals_B{b}.tex",
            [
                pname(c)
                + " & "
                + " & ".join(
                    interval(summarize(groups["grid", c, b, m])["hits"]) for m in GRID
                )
                + r" \\"
                for c in names
            ],
        )
    numeric = {}
    for scope, methods in [("grid", ALL), ("process", PRIMARY + [SOL])]:
        numeric[scope] = {
            m: summarize([r for r in rows if r["scope"] == scope and r["method"] == m])
            for m in methods
        }
    numeric["grid_B100"] = {
        m: summarize(
            [
                r
                for r in rows
                if r["scope"] == "grid" and r["budget"] == 100 and r["method"] == m
            ]
        )
        for m in ALL
    }
    numeric["grid_tts_B100"] = {
        m: {
            "median_tts": fmt(
                st.median(summarize(groups["grid", c, 100, m])["tts"] for c in names)
            ),
            "zero_hits": sum(
                summarize(groups["grid", c, 100, m])["hits"] == 0 for c in names
            ),
        }
        for m in ALL
    }
    numeric["process_conditions"] = {
        f"{c}_B{b}": {m: summarize(groups["process", c, b, m]) for m in PRIMARY + [SOL]}
        for c, b in CONDITIONS
    }
    numeric["process_primary_outcomes"] = {
        k: sum(
            r["category"] == k
            for r in rows
            if r["scope"] == "process" and r["method"] in PRIMARY
        )
        for k in ["target_reached", "target_not_reached", "execution_failed"]
    }
    numeric["process_primary_callbacks"] = sum(
        r["evaluations"]
        for r in rows
        if r["scope"] == "process" and r["method"] in PRIMARY
    )
    numeric["grid_primary_callbacks"] = sum(
        r["evaluations"] for r in rows if r["scope"] == "grid" and r["method"] in GRID
    )

    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        return "infinity" if isinstance(x, float) and not math.isfinite(x) else x

    dump(out / "numerical_summary.json", clean(numeric))
    return numeric


def figures(rows, groups, out):
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
    for key, name in [
        ("first_hit", "process_evaluation_profiles"),
        ("total_s", "process_completion_profiles"),
    ]:
        fig, axs = plt.subplots(3, 3, figsize=(8.2, 8))
        for ax, (c, b) in zip(axs.flat, PANELS):
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
        [("column", 16), ("cstr_30", 43), ("small_batch", 10), ("dynamic", 50)],
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
    for ax, (c, b) in zip(axs.flat, PANELS):
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "manuscript")
    args = p.parse_args()
    out = args.output
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(exist_ok=True)
    rows, groups, terminals = load()
    csvwrite(out / "tables/run_records.csv", rows)
    csvwrite(out / "tables/new_terminal_hits.csv", terminals)
    tables(rows, groups, out / "tables")
    figures(rows, groups, out / "figures")
    dump(
        out / "analysis_manifest.json",
        {
            "input_revision": "6e083eb49b497ce4fea90131e18cc0459db682e8",
            "execution_provider_revision": "38d917ef75ef6767c2a9f238d88be19bf0b89160",
            "input_sha256": {
                str(p.relative_to(ROOT)): sha(p)
                for p in [
                    BASE / "tables/completed_runs.csv",
                    ARCHIVE,
                    ROOT / "results/grid_gdp_dfo_20261011/runs.csv",
                    ROOT
                    / "results/process_ipopt_bam_v2_20261015/tables/run_results.csv",
                ]
            },
            "source_sha256": sha(__file__),
            "paired_interval_source_sha256": sha(
                ROOT / "review_comparison/analysis.py"
            ),
            "bootstrap": {
                "seed": 20261020,
                "replications": 2000,
                "ordering": "lexicographic case, then seed 0 through 9",
                "grid_unit": "intact function vectors",
                "process_unit": "paired seeds within each condition",
            },
            "generation_environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "matplotlib": __import__("matplotlib").__version__,
            },
            "runs": len(rows),
            "no_new_optimization_or_nlp_runs": True,
            "reproduce": "python -m review_comparison.manuscript --output manuscript",
            "outputs_sha256": {
                str(p.relative_to(out)): sha(p)
                for folder in ["tables", "figures"]
                for p in sorted((out / folder).iterdir())
                if p.is_file()
            },
        },
    )


if __name__ == "__main__":
    main()
