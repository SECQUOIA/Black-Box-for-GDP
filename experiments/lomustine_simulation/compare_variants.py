"""Compare the lomustine campaigns run with other option orders and with the capital-cost objective.

  python experiments/lomustine_simulation/compare_variants.py --variants DIR --output DIR

DIR holds one folder per campaign (source, reversed, backmixing, random1..3, capex), each
with the analysis/conditions.csv and analysis/facts.json written by analyze.py.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics

ORDERS = ["source", "reversed", "backmixing", "random1", "random2", "random3"]
METHODS = ["dsda", "nomad", "rbfopt", "miso", "bam", "fmqa_sa", "uniform"]
TEX = {"dsda": r"\texttt{D-SDA}", "nomad": r"\texttt{NOMAD}", "rbfopt": r"\texttt{RBFOpt}", "miso": r"\texttt{MISO}",
       "bam": r"\texttt{BAM}", "fmqa_sa": r"\texttt{FMQA-SA}", "uniform": "Uniform"}
LABEL = {"source": "Source", "reversed": "Reversed", "backmixing": "Back-mixing",
         "random1": "Random 1", "random2": "Random 2", "random3": "Random 3"}


def read(root, name):
    with open(root / name / "analysis/conditions.csv") as f:
        rows = list(csv.DictReader(f))
    facts = json.loads((root / name / "analysis/facts.json").read_text())
    return {(int(r["budget"]), r["method"]): int(r["hits"]) for r in rows}, facts


def order_table(hits, budgets):
    """Hits in the source order, with the range over all orders."""
    lines = [r"\begin{tabular}{@{}l" + "c" * len(budgets) + "@{}}\\toprule",
             "Method & " + " & ".join(rf"\(B={b}\)" for b in budgets) + r"\\\midrule"]
    for m in METHODS:
        cells = []
        for b in budgets:
            values = [hits[o][b, m] for o in ORDERS]
            cells.append(f"{hits['source'][b, m]} [{min(values)}, {max(values)}]")
        lines.append(TEX[m] + " & " + " & ".join(cells) + r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def orders_table(facts):
    lines = [r"\begin{tabular}{@{}lll@{}}\toprule", r"Order & Reactors & Crystallizers\\\midrule"]
    for o in ORDERS:
        opts = facts[o]["options"]
        cryst = [{"batchU": "batch", "cont1": "1", "cont2": "2", "cont3": "3"}[c] for c in opts["crystallizers"]]
        lines.append(f"{LABEL[o]} & {', '.join(opts['reactors'])} & {', '.join(cryst)}" + r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def capex_table(hits, budgets):
    lines = [r"\begin{tabular}{@{}l" + "c" * len(budgets) + "@{}}\\toprule",
             "Method & " + " & ".join(rf"\(B={b}\)" for b in budgets) + r"\\\midrule"]
    top = {b: max(hits[b, m] for m in METHODS) for b in budgets}
    for m in METHODS:
        cells = [rf"\textbf{{{hits[b, m]}}}" if hits[b, m] == top[b] else str(hits[b, m]) for b in budgets]
        lines.append(TEX[m] + " & " + " & ".join(cells) + r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variants", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    hits, facts = {}, {}
    for name in ORDERS + ["capex"]:
        hits[name], facts[name] = read(args.variants, name)
    budgets = sorted({b for b, _ in hits["source"]})
    rows = []
    for name in ORDERS + ["capex"]:
        for b in budgets:
            for m in METHODS:
                rows.append(dict(variant=name, objective=facts[name]["options"]["objective"],
                                 reactors=",".join(facts[name]["options"]["reactors"]),
                                 crystallizers=",".join(facts[name]["options"]["crystallizers"]),
                                 budget=b, method=m, hits=hits[name][b, m],
                                 crashed_identical=sum(1 for j in facts[name]["crashed_identical_runs"]
                                                       if j.startswith(f"{m}_B{b}_"))))
    summary = []
    for b in budgets:
        for m in METHODS:
            values = [hits[o][b, m] for o in ORDERS]
            summary.append(dict(budget=b, method=m, source=hits["source"][b, m], minimum=min(values),
                                maximum=max(values), mean=statistics.mean(values)))
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in (("variant_hits.csv", rows), ("order_summary.csv", summary)):
        with open(args.output / name, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(data)
    (args.output / "order_table.tex").write_text(order_table(hits, budgets))
    (args.output / "orders_table.tex").write_text(orders_table(facts))
    (args.output / "capex_table.tex").write_text(capex_table(hits["capex"], budgets))
    capex = facts["capex"]
    (args.output / "facts.json").write_text(json.dumps(dict(
        capex_reference=capex["reference_objective"], capex_reference_layout=capex["reference_layout"],
        crashed_identical_runs={n: facts[n]["crashed_identical_runs"] for n in facts}), indent=2) + "\n")
    files = sorted(p for p in args.output.iterdir() if p.name != "manifest.json")
    (args.output / "manifest.json").write_text(json.dumps(dict(
        source_sha256={"compare_variants.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        outputs_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}), indent=2) + "\n")
    for r in summary:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
