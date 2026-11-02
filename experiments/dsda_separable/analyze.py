"""Compare D-SDA with the separable and the unit L-infinity neighborhoods.

  python experiments/dsda_separable/analyze.py --results results/dsda_separable_20261101

Reads the separable Grid and process runs (RESULTS/grid_process, written by run.py), the
separable Lomustine runs (RESULTS/lomustine/<order>, written by the harness of
experiments/catalytic_distillation_live with the case lomustine_case.py), and
the L-infinity runs of results/dsda_no_revisit_20261031 and
results/lomustine_simulation_20261031.  Every separable run is paired with the L-infinity
run of the same condition and seed.  Writes RESULTS/analysis/{conditions.csv, facts.json,
neighborhood_table.tex}.
"""

import argparse
import csv
import io
import json
from math import comb
from pathlib import Path
import statistics
import zipfile

REPO = Path(__file__).resolve().parents[2]
LOMUSTINE = REPO / "results/lomustine_simulation_20261031"
ORDERS = ["source", "reversed", "backmixing", "random1", "random2", "random3"]
ORDER_LABEL = {"source": "Source", "reversed": "Reversed", "backmixing": "Back-mixing",
               "random1": "Random 1", "random2": "Random 2", "random3": "Random 3"}
PROCESS_LABEL = {"column": "\\texttt{Column}", "small_batch": "\\texttt{Small Batch}", "dynamic": "\\texttt{Dynamic}",
                 **{f"cstr_{n}": f"\\texttt{{CSTR{n}}}" for n in (5, 10, 15, 20, 25, 30)}}
PROCESS_ORDER = ["column", "cstr_5", "cstr_10", "cstr_15", "cstr_20", "cstr_25", "cstr_30", "small_batch", "dynamic"]


def mcnemar(b, c):
    """Exact two-sided McNemar p-value from the discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def read_zip_csv(path, member):
    with zipfile.ZipFile(path) as z:
        return list(csv.DictReader(io.StringIO(z.read(member).decode())))


def lomustine_pairs(results):
    pairs = []
    for order in ORDERS:
        if order == "source":
            linf = read_zip_csv(LOMUSTINE / "evidence/lomustine_runs.zip", "lomustine_full/runs.csv")
        else:
            linf = read_zip_csv(LOMUSTINE / f"variants/{order}/evidence/runs.zip", f"{order}/runs.csv")
        linf = {(r["budget"], r["seed"]): r for r in linf if r["method"] == "dsda"}
        for r in csv.DictReader((results / "lomustine" / order / "runs.csv").open()):
            old = linf[r["budget"], r["seed"]]
            pairs.append(dict(scope="lomustine", case=order, budget=int(r["budget"]), seed=int(r["seed"]),
                              hit_linf=old["hit"] == "True", hit_separable=r["hit"] == "True",
                              evaluations_linf=int(old["evaluations"]), evaluations_separable=int(r["evaluations"]),
                              completion_linf_s=float(old["completion_s"]),
                              completion_separable_s=float(r["completion_s"])))
    return pairs


def grid_process_pairs(results):
    pairs = []
    for r in csv.DictReader((results / "grid_process/paired_runs.csv").open()):
        pairs.append(dict(scope=r["scope"], case=r["case"], budget=int(r["budget"]), seed=int(r["seed"]),
                          hit_linf=r["hit_linf"] == "True", hit_separable=r["hit_separable"] == "True",
                          evaluations_linf=int(r["evaluations_linf"]),
                          evaluations_separable=int(r["evaluations_separable"]),
                          completion_linf_s=float(r["completion_linf_s"]),
                          completion_separable_s=float(r["completion_separable_s"])))
    return pairs


def summarize(group):
    b = sum(g["hit_separable"] and not g["hit_linf"] for g in group)
    c = sum(g["hit_linf"] and not g["hit_separable"] for g in group)
    return dict(runs=len(group), hits_linf=sum(g["hit_linf"] for g in group),
                hits_separable=sum(g["hit_separable"] for g in group), separable_only=b, linf_only=c,
                p_value=mcnemar(b, c),
                median_evaluations_linf=statistics.median(g["evaluations_linf"] for g in group),
                median_evaluations_separable=statistics.median(g["evaluations_separable"] for g in group),
                median_completion_linf_s=statistics.median(g["completion_linf_s"] for g in group),
                median_completion_separable_s=statistics.median(g["completion_separable_s"] for g in group))


def group_by(pairs, key):
    groups = {}
    for p in pairs:
        groups.setdefault(key(p), []).append(p)
    return groups


def table(conditions):
    def bold(x, y):
        if x > y:
            return f"\\textbf{{{x}}}", str(y)
        if y > x:
            return str(x), f"\\textbf{{{y}}}"
        return str(x), str(y)

    def row(label, c):
        linf, sep = bold(c["hits_linf"], c["hits_separable"])
        return (f"{label} & {linf} & {sep} & {c['separable_only']} & {c['linf_only']} & {c['median_evaluations_linf']:g} & "
                f"{c['median_evaluations_separable']:g} \\\\")

    lines = ["\\begin{tabular}{@{}llrrrrrr@{}}\\toprule",
             "Case & \\(B\\) & \\(L_\\infty\\) & Separable & Separable only & \\(L_\\infty\\) only & "
             "\\makecell{Median evals\\\\\\(L_\\infty\\)} & \\makecell{Median evals\\\\separable} \\\\\\midrule"]
    for c in conditions:
        if c["scope"] == "grid":
            lines.append(row(f"Grid (210 runs) & {c['budget']}", c))
    lines.append("\\midrule")
    for case in PROCESS_ORDER:
        for c in conditions:
            if c["scope"] == "process" and c["case"] == case:
                lines.append(row(f"{PROCESS_LABEL[case]} & {c['budget']}", c))
    lines.append("\\midrule")
    for c in conditions:
        if c["scope"] == "lomustine_pooled":
            lines.append(row(f"\\texttt{{Lomustine}}, six orders (60 runs) & {c['budget']}", c))
    lines.append("\\bottomrule\\end{tabular}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args(argv)
    gp, lom = grid_process_pairs(args.results), lomustine_pairs(args.results)
    conditions = []
    for (budget,), group in sorted(group_by([p for p in gp if p["scope"] == "grid"], lambda p: (p["budget"],)).items()):
        conditions.append(dict(scope="grid", case="all", budget=budget, **summarize(group)))
    for (case, budget), group in sorted(group_by([p for p in gp if p["scope"] == "process"],
                                                 lambda p: (p["case"], p["budget"])).items()):
        conditions.append(dict(scope="process", case=case, budget=budget, **summarize(group)))
    for (order, budget), group in sorted(group_by(lom, lambda p: (p["case"], p["budget"])).items()):
        conditions.append(dict(scope="lomustine", case=order, budget=budget, **summarize(group)))
    for (budget,), group in sorted(group_by(lom, lambda p: (p["budget"],)).items()):
        conditions.append(dict(scope="lomustine_pooled", case="all_orders", budget=budget, **summarize(group)))
    process = [p for p in gp if p["scope"] == "process"]
    pooled = {
        "process": summarize(process),
        "cstr": summarize([p for p in process if p["case"].startswith("cstr")]),
        "dynamic_b12_b15": summarize([p for p in process if p["case"] == "dynamic" and p["budget"] in (12, 15)]),
        "lomustine": summarize(lom),
        "lomustine_source": summarize([p for p in lom if p["case"] == "source"]),
    }
    out = args.results / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    fields = list(conditions[0])
    with (out / "conditions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(conditions)
    (out / "facts.json").write_text(json.dumps(dict(pooled=pooled, runs=dict(grid_process=len(gp), lomustine=len(lom))),
                                               indent=2) + "\n")
    (out / "neighborhood_table.tex").write_text(table(conditions))
    for name, c in pooled.items():
        print(f"{name:18s} L-inf {c['hits_linf']:4d}  separable {c['hits_separable']:4d}  "
              f"discordant {c['separable_only']}/{c['linf_only']}  p={c['p_value']:.3g}")
    for c in conditions:
        if c["scope"] in ("grid", "lomustine_pooled"):
            print(f"{c['scope']:16s} B={c['budget']:<4d} L-inf {c['hits_linf']:4d} separable {c['hits_separable']:4d} "
                  f"discordant {c['separable_only']}/{c['linf_only']} p={c['p_value']:.3g} "
                  f"evals {c['median_evaluations_linf']:g}/{c['median_evaluations_separable']:g}")


if __name__ == "__main__":
    main()
