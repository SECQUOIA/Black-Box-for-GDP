"""Seven-method Grid profiles and target tables from the audited Dantzig returns; no solver calls.

RBFOpt, BAM, FMQA-SA, uniform sampling, NOMAD, MISO, and the BAM-prefix control come from
results/pr56_dantzig_return_20261031/analysis (verified against its REPRODUCTION.json).
D-SDA comes from results/dsda_no_revisit_20261031 (verified against its FILE_SHA256.json),
the rerun in which no configuration is evaluated twice.

  python -m review_comparison.seven_methods --output /tmp/seven-methods
"""

import argparse
import csv
import io
import json
import math
from pathlib import Path
import platform
import statistics

from . import dsda_no_revisit_runs as dsda
from . import manuscript as ms
from . import mi_dfo_runs as mi

ROOT = Path(__file__).resolve().parents[1]
# Direct search, RBF surrogates, other surrogates, and the uniform baseline.
METHODS = ["dsda", "nomad", ms.GEN, "miso", "bam", "fmqa_sa", ms.UNI]
GRID = METHODS + [ms.PRE]
LABEL = {**ms.LABEL, "nomad": "NOMAD", "miso": "MISO"}
COLOR = {**ms.COLOR, "nomad": "#E69F00", "miso": "#000000"}
STYLE = {**ms.STYLE, "nomad": (0, (3, 1, 1, 1)), "miso": "-"}
MARK = {**ms.MARK, "nomad": "<", "miso": "P"}
TEX = {m: f"\\texttt{{{LABEL[m]}}}" for m in METHODS}
TEX[ms.UNI] = "Uniform"
PROCESS = ([("column", 13)] + [(f"cstr_{n}", b) for n, b in zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43))]
           + [("small_batch", 10)] + [("dynamic", b) for b in (12, 15, 20, 30, 37, 50)])
CASE_TEX = {"column": "Column", "small_batch": "Small Batch", "dynamic": "Dynamic"}
ENUMERATION = "results/revision_diagnostics_20261030"


def number(value):
    return float(value) if value else None


def load(root, inputs):
    rows = []
    for name in ("historical_primary_runs.csv", "historical_control_runs.csv"):
        for r in csv.DictReader(io.StringIO(mi.read(root, name, inputs).decode())):
            # D-SDA comes from the rerun without re-evaluated configurations.
            if r["method"] not in GRID or r["method"] == "dsda":
                continue
            rows.append(dict(scope=r["scope"], case=r["case"], budget=int(r["budget"]), seed=int(r["seed"]),
                             method=r["method"], hit=r["hit"] == "True",
                             first_hit=int(r["first_hit"]) if r["first_hit"] else None,
                             search_s=number(r["retained_search_s"]), point_cost_s=number(r["point_cost_s"]),
                             completion_s=number(r["completion_s"])))
    rows += [dict(r) for r in dsda.runs(root, inputs)] + [dict(r) for r in mi.runs(root, inputs)]
    groups = {}
    for r in rows:
        groups.setdefault((r["scope"], r["case"], r["budget"], r["method"]), []).append(r)
    for key, group in groups.items():
        if key[0] == "process" and key[3] == ms.PRE:
            continue
        if sorted(r["seed"] for r in group) != list(range(10)):
            raise ValueError(f"Incomplete seeds for {key}")
        if any(r["hit"] != (r["first_hit"] is not None) for r in group):
            raise ValueError(f"Inconsistent first hit for {key}")
    return rows


def sig3(x):
    """Three significant figures, keeping trailing zeros as the published tables do."""
    return f"{x:#.3g}".rstrip(".")


def grid_table(rows):
    data, lines = [], []
    for b in ms.BUDGETS:
        pct = {}
        for m in GRID:
            group = [r for r in rows if r["scope"] == "grid" and r["budget"] == b and r["method"] == m]
            pct[m] = 100 * sum(r["hit"] for r in group) / len(group)
            data.append(dict(budget=b, method=m, runs=len(group), hits=sum(r["hit"] for r in group), percent=pct[m]))
        top = max(pct.values())
        cells = [f"\\textbf{{{pct[m]:.1f}}}" if abs(pct[m] - top) < 1e-9 else f"{pct[m]:.1f}" for m in GRID]
        lines.append(f"{b} & " + " & ".join(cells) + " \\\\")
    head = ("Budget \\(B\\) & " + " & ".join(TEX[m] for m in METHODS)
            + " & \\shortstack{\\texttt{BAM}-prefix\\\\control}\\\\\\midrule")
    tex = ("\\begin{tabular}{r" + "c" * len(GRID) + "}\\toprule\n" + head + "\n" + "\n".join(lines)
           + "\n\\bottomrule\n\\end{tabular}\n")
    return tex, data


def process_table(rows):
    data, lines = [], []
    for case, b in PROCESS:
        hits, cells = {}, {}
        for m in METHODS:
            group = [r for r in rows if r["scope"] == "process" and (r["case"], r["budget"], r["method"]) == (case, b, m)]
            times = [r["search_s"] for r in group]
            q25, median, q75 = statistics.quantiles(times, n=4, method="inclusive")
            hits[m] = sum(r["hit"] for r in group)
            cells[m] = (median, q25, q75)
            data.append(dict(case=case, budget=b, method=m, hits=hits[m], median_search_s=median,
                             q25_search_s=q25, q75_search_s=q75))
        top = max(hits.values())
        name = CASE_TEX[case] if case in CASE_TEX else "CSTR" + case.split("_")[1]
        out = [f"\\texttt{{{name}}}", str(b)]
        for m in METHODS:
            h = f"\\textbf{{{hits[m]}}}" if hits[m] == top else str(hits[m])
            median, q25, q75 = cells[m]
            out.append(f"\\makecell{{{h}\\\\{sig3(median)}\\\\{{[{sig3(q25)}, {sig3(q75)}]}}}}")
        lines.append(" & ".join(out) + " \\\\")
    head = "Case & \\(B\\) & " + " & ".join(TEX[m] for m in METHODS) + " \\\\\n\\midrule"
    tex = ("\\begin{tabular}{@{}lr" + "c" * len(METHODS) + "@{}}\\toprule\n" + head + "\n" + "\n".join(lines)
           + "\n\\bottomrule\n\\end{tabular}\n")
    return tex, data


def case_tex(case):
    return "\\texttt{" + (CASE_TEX[case] if case in CASE_TEX else "CSTR" + case.split("_")[1]) + "}"


def enumeration(root, inputs):
    """Cost of evaluating every configuration of each DFO box once, from the sealed diagnostics."""
    path = root / ENUMERATION / "enumeration_cost.csv"
    expected = json.loads((root / ENUMERATION / "manifest.json").read_text())["outputs_sha256"]["enumeration_cost.csv"]
    if ms.sha(path) != expected:
        raise ValueError(f"{path} does not match its manifest")
    inputs[str(path.relative_to(root))] = expected
    with open(path) as f:
        return {r["case"]: float(r["enumeration_s"]) for r in csv.DictReader(f)}


def completion_table(rows, enum):
    """Median full-run completion time of every process condition, including misses."""
    data, lines = [], []
    for case, b in PROCESS:
        medians = {}
        for m in METHODS:
            group = [r for r in rows if r["scope"] == "process" and (r["case"], r["budget"], r["method"]) == (case, b, m)]
            if len(group) != 10 or any(r["completion_s"] is None for r in group):
                raise ValueError(f"Missing completion time: {case}/{b}/{m}")
            medians[m] = statistics.median(r["completion_s"] for r in group)
            data.append(dict(case=case, budget=b, method=m, median_completion_s=medians[m]))
        lines.append(" & ".join([case_tex(case), str(b), *(f"{medians[m]:.2f}" for m in METHODS),
                                 f"{enum[case]:.2f}"]) + " \\\\")
    head = "Case & \\(B\\) & " + " & ".join(TEX[m] for m in METHODS) + " & Enumeration \\\\\\midrule"
    tex = ("\\begin{tabular}{@{}lr" + "c" * (len(METHODS) + 1) + "@{}}\\toprule\n" + head + "\n"
           + "\n".join(lines) + "\n\\bottomrule\\end{tabular}\n")
    return tex, data


COST_METRICS = ["completion_s", "point_cost_s", "search_s"]


def grid_cost_table(rows):
    """Grid quartiles at B=100; NOMAD runs that crashed on every attempt have no times."""
    data, lines = [], []
    for m in GRID:
        group = [r for r in rows if r["scope"] == "grid" and r["budget"] == 100 and r["method"] == m]
        timed = [r for r in group if all(r[k] is not None for k in COST_METRICS)]
        row = dict(method=m, runs=len(group), timed_runs=len(timed), target_hits=sum(r["hit"] for r in group))
        cells = []
        for k in COST_METRICS:
            q = statistics.quantiles([r[k] for r in timed], n=4, method="inclusive")
            row.update({f"{k}_q{p}": v for p, v in zip((25, 50, 75), q)})
            digits = 4 if k == "search_s" and q[1] < .01 else 2
            q25, q50, q75 = (f"{v:.{digits}f}" for v in q)
            cells.append(f"\\shortstack{{{q50}\\\\{{[{q25}, {q75}]}}}}")
        label = ("\\texttt{BAM}-prefix control" if m == ms.PRE else TEX[m])
        if len(timed) < len(group):
            label += "\\({}^{a}\\)"
        lines.append(" & ".join([label, f"{row['target_hits']}/{row['runs']}", *cells]) + " \\\\")
        data.append(row)
    return "\n".join(lines) + "\n", data


CONTRASTS = [("nomad", "dsda"), ("nomad", ms.GEN), ("miso", "dsda"), ("miso", ms.GEN), ("miso", "nomad")]


def mcnemar_exact(first_only, second_only):
    """Two-sided exact McNemar test, as in revision_diagnostics."""
    n, k = first_only + second_only, min(first_only, second_only)
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def ptex(p):
    if p == 1:
        return "1"
    if p < 1e-3:
        mantissa, exponent = f"{p:.2e}".split("e")
        return rf"\({mantissa}\times10^{{{int(exponent)}}}\)"
    return sig3(p)


def holm(pvalues):
    """Holm step-down adjusted p-values, in the input order."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def exploratory_table(root, inputs, rows):
    """The 70 exploratory tests with Holm correction, and pooled CSTR tests outside that family.

    The PR #56 return defined the family; its D-SDA contrasts used the earlier D-SDA, so all
    tests are recomputed from the runs. Contrasts without D-SDA must match the return.
    """
    tests = list(csv.DictReader(io.StringIO(mi.read(root, "process_paired_tests.csv", inputs).decode())))
    hit = {(r["case"], r["budget"], r["seed"], r["method"]): r["hit"] for r in rows if r["scope"] == "process"}

    def discordant(members, a, b):
        pairs = [(hit[c, bb, s, a], hit[c, bb, s, b]) for c, bb in members for s in range(10)]
        return sum(x and not y for x, y in pairs), sum(y and not x for x, y in pairs)

    cells, data = {}, []
    for t in tests:
        key = (t["case"], int(t["budget"]), t["first"], t["second"])
        counts = discordant([key[:2]], t["first"], t["second"])
        p = mcnemar_exact(*counts)
        if "dsda" not in key[2:] and (counts != (int(t["first_only"]), int(t["second_only"]))
                                      or abs(p - float(t["p_exact"])) > 1e-12):
            raise ValueError(f"Paired test does not match the runs: {key}")
        cells[key] = (*counts, p)
        data.append(dict(case=key[0], budget=key[1], first=key[2], second=key[3], first_only=counts[0],
                         second_only=counts[1], p_exact=p, family="exploratory_70"))
    if sorted(cells) != sorted((c, b, f, s) for c, b in PROCESS for f, s in CONTRASTS):
        raise ValueError("Expected five contrasts in each of the 14 process conditions")
    for d, adjusted in zip(data, holm([d["p_exact"] for d in data])):
        d["p_holm_70"] = adjusted
    cstr = [k for k in PROCESS if k[0].startswith("cstr_")]
    for f, s in CONTRASTS:
        counts = discordant(cstr, f, s)
        cells["cstr_all", None, f, s] = (*counts, mcnemar_exact(*counts))
        data.append(dict(case="cstr_all", budget=None, first=f, second=s, first_only=counts[0], second_only=counts[1],
                         p_exact=cells["cstr_all", None, f, s][2], family="pooled_descriptive", p_holm_70=None))
    lines = []
    for case, b in PROCESS + [("cstr_all", None)]:
        if case == "cstr_all":
            lines.append(r"\midrule")
        name = r"\texttt{CSTR}, all sizes" if case == "cstr_all" else case_tex(case)
        out = [name, str(b) if b else "--"]
        for f, s in CONTRASTS:
            a, z, p = cells[case, b, f, s]
            out.append(rf"\makecell{{{a}:{z}\\{ptex(p)}}}")
        lines.append(" & ".join(out) + r" \\")
    head = ("Case & \\(B\\) & " + " & ".join(rf"\makecell{{{TEX[f]}\\vs {TEX[s]}}}" for f, s in CONTRASTS)
            + r"\\\midrule")
    tex = ("\\begin{tabular}{@{}lr" + "c" * len(CONTRASTS) + "@{}}\\toprule\n" + head + "\n" + "\n".join(lines)
           + "\n\\bottomrule\\end{tabular}\n")
    return tex, data



def restart_table(root, inputs):
    """Process D-SDA restart diagnostic from the rerun without re-evaluated configurations."""
    runs = [r for r in dsda.all_runs(root, inputs) if r["scope"] == "process"]
    lines, data = [], []
    for case, b in PROCESS:
        g = {v: [r for r in runs if (r["case"], r["budget"], r["variant"]) == (case, b, v)] for v in dsda.RESTARTS}
        if any(len(group) != 10 for group in g.values()):
            raise ValueError(f"Missing restart runs: {case}/{b}")
        row = dict(case=case, budget=b)
        for v, group in g.items():
            row.update({f"{v}_hits": sum(r["hit"] for r in group),
                        f"{v}_full_budget_runs": sum(r["unused_budget"] == 0 for r in group),
                        f"{v}_median_evaluations": statistics.median(r["evaluations"] for r in group),
                        f"{v}_median_completion_s": statistics.median(r["completion_s"] for r in group)})
        data.append(row)
        cells = [case_tex(case), str(b), *(str(row[f"{v}_hits"]) for v in dsda.RESTARTS),
                 *(str(row[f"{v}_full_budget_runs"]) for v in dsda.RESTARTS[:2]),
                 *(f"{row[f'{v}_median_evaluations']:g}" for v in dsda.RESTARTS),
                 *(f"{row[f'{v}_median_completion_s']:.2f}" for v in dsda.RESTARTS)]
        lines.append(" & ".join(cells) + r" \\")
    head = (r" & & \multicolumn{3}{c}{Target hits} & \multicolumn{2}{c}{Full-budget runs} & "
            r"\multicolumn{3}{c}{Median evaluations} & \multicolumn{3}{c}{Median completion (s)}\\"
            r"\cmidrule(lr){3-5}\cmidrule(lr){6-7}\cmidrule(lr){8-10}\cmidrule(l){11-13}" + "\n"
            r"Case & \(B\) & S & R & RR & S & R & S & R & RR & S & R & RR\\\midrule")
    return ("\\begin{tabular}{@{}lrccccccccccc@{}}\\toprule\n" + head + "\n" + "\n".join(lines)
            + "\n\\bottomrule\\end{tabular}\n"), data


EXCLUDED = ("bohachevsky2", "xin_she_yang3")


def grid_exclusions(rows):
    """Grid target-hit rates without the two functions discussed in the supplement."""
    data = []
    for b in (10, 100):
        for m in GRID:
            group = [r for r in rows if r["scope"] == "grid" and r["budget"] == b and r["method"] == m
                     and r["case"] not in EXCLUDED]
            if len(group) != 190:
                raise ValueError(f"Expected 190 runs without the excluded functions: {m}/{b}")
            data.append(dict(budget=b, method=m, runs=len(group), hits=sum(r["hit"] for r in group),
                             percent=100 * sum(r["hit"] for r in group) / len(group)))
    return data


def grid_profiles(rows, out):
    """Cumulative target hits at B = 100; the per-budget checks still cover every budget."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    params = {"font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 11, "axes.labelsize": 10.5,
              "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10.5, "axes.spines.top": False,
              "axes.spines.right": False, "pdf.fonttype": 42}
    checks = []
    for b in ms.BUDGETS:
        for m in GRID:
            group = [r for r in rows if r["scope"] == "grid" and r["budget"] == b and r["method"] == m]
            vals = sorted(r["first_hit"] for r in group if r["hit"])
            checks.append(dict(method=m, budget=b, runs=len(group), hits=len(vals), final=len(vals) / len(group)))
    b = max(ms.BUDGETS)
    with plt.rc_context(params):
        fig, ax = plt.subplots(figsize=(7.4, 4.0))
        for m in GRID:
            group = [r for r in rows if r["scope"] == "grid" and r["budget"] == b and r["method"] == m]
            vals = sorted(r["first_hit"] for r in group if r["hit"])
            xs = sorted({0, b, *vals})
            ys = [sum(v <= x for v in vals) / len(group) for x in xs]
            ax.step(xs, ys, where="post", color=COLOR[m], ls=STYLE[m], lw=1.6, marker=MARK[m], ms=3.5,
                    markevery=max(1, len(xs) // 8))
        ax.axvline(3, color="#777777", ls="--", lw=0.8)
        ax.axvspan(3, 13, color="#008b8b", alpha=0.09)
        ax.set(ylim=(-0.02, 1.03), yticks=[0, 0.25, 0.5, 0.75, 1], xlim=(0, b), xlabel="Evaluations",
               ylabel="Target-hit fraction")
        ax.set_xticks([0, 10, 30, 50, 70, 100])
        ax.grid(axis="y", alpha=0.2)
        handles = [Line2D([], [], color=COLOR[m], ls=STYLE[m], marker=MARK[m], ms=4, lw=1.5, label=LABEL[m])
                   for m in GRID]
        ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, fontsize=9.5)
        fig.tight_layout()
        for ext, kw in (("pdf", dict(metadata={"CreationDate": None, "ModDate": None})), ("png", dict(dpi=160))):
            fig.savefig(out / f"figure_B_grid_evaluation_profiles.{ext}", bbox_inches="tight", pad_inches=0.04, **kw)
        plt.close(fig)
    return checks


# Dynamic at B = 50 only: its profile at 12 to 37 evaluations equals the runs with those budgets.
PROFILE_PANELS = [("cstr_30", 43), ("column", 13), ("small_batch", 10), ("dynamic", 50)]


def process_profiles(rows, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    params = {"font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 11, "axes.labelsize": 10.5,
              "xtick.labelsize": 10, "ytick.labelsize": 10, "axes.spines.top": False, "axes.spines.right": False,
              "pdf.fonttype": 42}
    with plt.rc_context(params):
        fig, axs = plt.subplots(2, 2, figsize=(7.4, 6.2))
        for ax, (case, b) in zip(axs.flat, PROFILE_PANELS):
            for m in METHODS:
                group = [r for r in rows if r["scope"] == "process" and (r["case"], r["budget"], r["method"]) == (case, b, m)]
                vals = sorted(r["first_hit"] for r in group if r["hit"])
                xs = sorted({0, b, *vals})
                ys = [sum(v <= x for v in vals) / len(group) for x in xs]
                ax.step(xs, ys, where="post", color=COLOR[m], ls=STYLE[m], lw=1.6, marker=MARK[m], ms=3.5,
                        markevery=max(1, len(xs) // 5))
            ax.axvline(3, color="#777", ls="--", lw=0.8)
            ax.set(title=f"{ms.pname(case).replace('CSTR ', 'CSTR')}, B={b}", ylim=(-0.03, 1.04),
                   yticks=[0, 0.5, 1], xlim=(0, b), xlabel="Evaluations")
            ax.set_xticks([0, b // 2, b])
            ax.grid(axis="y", alpha=0.2)
        for ax in axs[:, 0]:
            ax.set_ylabel("Target-hit fraction")
        handles = [Line2D([], [], color=COLOR[m], ls=STYLE[m], marker=MARK[m], ms=4, lw=1.5, label=LABEL[m])
                   for m in METHODS]
        fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=10)
        fig.tight_layout(rect=(0, 0.085, 1, 1), h_pad=1.5, w_pad=1)
        for ext, kw in (("pdf", dict(metadata={"CreationDate": None, "ModDate": None})), ("png", dict(dpi=160))):
            fig.savefig(out / f"process_evaluation_profiles.{ext}", bbox_inches="tight", pad_inches=0.04, **kw)
        plt.close(fig)


def write_csv(path, data):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def build(root, out):
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output must be empty")
    out.mkdir(parents=True, exist_ok=True)
    inputs = {}
    rows = load(root, inputs)
    grid_tex, grid_data = grid_table(rows)
    process_tex, process_data = process_table(rows)
    completion_tex, completion_data = completion_table(rows, enumeration(root, inputs))
    cost_tex, cost_data = grid_cost_table(rows)
    tests_tex, tests_data = exploratory_table(root, inputs, rows)
    (out / "grid_hits_table.tex").write_text(grid_tex)
    (out / "process_targets_table.tex").write_text(process_tex)
    (out / "process_completion_table.tex").write_text(completion_tex)
    (out / "grid_cost_rows.tex").write_text(cost_tex)
    (out / "exploratory_paired_tests.tex").write_text(tests_tex)
    restart_tex, restart_data = restart_table(root, inputs)
    (out / "dsda_restarts_table.tex").write_text(restart_tex)
    write_csv(out / "dsda_restarts.csv", restart_data)
    write_csv(out / "grid_hits.csv", grid_data)
    write_csv(out / "process_targets.csv", process_data)
    write_csv(out / "process_completion.csv", completion_data)
    write_csv(out / "grid_cost.csv", cost_data)
    write_csv(out / "exploratory_paired_tests.csv", tests_data)
    write_csv(out / "grid_exclusions.csv", grid_exclusions(rows))
    checks = grid_profiles(rows, out)
    process_profiles(rows, out)
    write_csv(out / "grid_profile_checks.csv", checks)
    import matplotlib
    (out / "manifest.json").write_text(json.dumps(dict(
        input_sha256=inputs, source_sha256={p: ms.sha(root / p) for p in (
            "review_comparison/seven_methods.py", "review_comparison/mi_dfo_runs.py",
            "review_comparison/dsda_no_revisit_runs.py", "review_comparison/manuscript.py")},
        new_solver_calls=0, environment=dict(python=platform.python_version(), matplotlib=matplotlib.__version__),
        reproduce="python -m review_comparison.seven_methods --output /tmp/seven-methods",
        output_sha256={f.name: ms.sha(f) for f in sorted(out.iterdir())}), indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.output)
