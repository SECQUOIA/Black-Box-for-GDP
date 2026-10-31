"""Seed spread, tolerance sensitivity, search overhead, and GDPopt enumeration.

Summarizes retained records only; no optimizer, NLP solver, or server run.
"""

import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import platform
import re
import statistics
import zipfile

from . import manuscript as m
from .joint_process import LABELS, METHODS

RUNS = m.ROOT / "results/dsda_publication_20261028/tables/run_records.csv"
DSDA_ARCHIVE = m.ROOT / "results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip"
DSDA_ARCHIVE_SHA256 = "e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e"
DSDA_JOBS = "dsda_abs1e5_rerun_20261028_020753_2004611/reproduction/inputs/jobs.json"
GDPOPT = m.ROOT / "results/gdpopt_scip_ipopt_analysis_20261030"
FAMILIES = [("cstr", r"\texttt{CSTR}"), ("column", r"\texttt{Column}"),
            ("small_batch", r"\texttt{Small Batch}"), ("dynamic", r"\texttt{Dynamic}")]
TOLERANCES = (1e-3, 1e-2, 5e-2)
ADMISSIBLE = {**{f"cstr_{n}": n * (n + 1) // 2 for n in (5, 10, 15, 20, 25, 30)}, "dynamic": 37}


def require(test, message):
    if not test:
        raise ValueError(message)


def family(case):
    return "cstr" if case.startswith("cstr_") else case


def g3(x):
    """Three significant figures, keeping trailing zeros."""
    s = format(x, "#.3g")
    return s[:-1] if s.endswith(".") else s


def references():
    """Exact process reference values from the sealed D-SDA input package."""
    require(m.sha(DSDA_ARCHIVE) == DSDA_ARCHIVE_SHA256, "D-SDA archive hash mismatch")
    with zipfile.ZipFile(DSDA_ARCHIVE) as z:
        jobs = json.loads(z.read(DSDA_JOBS))
    refs = defaultdict(set)
    for job in jobs:
        if job["spec"]["scope"] == "process":
            refs[job["spec"]["case"]].add(job["target"])
    require(all(len(v) == 1 for v in refs.values()) and len(refs) == 9, "Ambiguous references")
    return {case: v.pop() for case, v in refs.items()}


def load_runs():
    manifest = json.loads((RUNS.parents[1] / "manifest.json").read_text())
    require(m.sha(RUNS) == manifest["outputs_sha256"]["tables/run_records.csv"],
            "Run-record hash mismatch")
    rows = [dict(r) for r in m.read(RUNS) if r["method"] in METHODS]
    for r in rows:
        r["budget"], r["seed"], r["evaluations"] = int(r["budget"]), int(r["seed"]), int(r["evaluations"])
        for k in ("best_objective", "search_s", "point_cost_s", "prep_s"):
            r[k] = float(r[k])
        r["hit"] = r["hit"] == "True"
    process = [r for r in rows if r["scope"] == "process"]
    require(len(process) == 700, "Expected 700 primary process runs")
    require(len([r for r in rows if r["scope"] == "grid"]) == 5250, "Expected 5,250 primary Grid runs")
    return rows


def spread_rows(rows, refs):
    """Exact and relaxed attainment, distinct final objectives, and miss gaps."""
    out = []
    for fam, _ in FAMILIES:
        for method in METHODS:
            group = [r for r in rows if r["scope"] == "process" and family(r["case"]) == fam
                     and r["method"] == method]
            gaps = [(r["best_objective"] - refs[r["case"]]) / max(1.0, abs(refs[r["case"]]))
                    for r in group]
            require(all(math.isfinite(g) for g in gaps), "Nonfinite final objective")
            conditions = defaultdict(set)
            for r in group:
                conditions[r["case"], r["budget"]].add(r["best_objective"])
            misses = [g for g, r in zip(gaps, group) if not r["hit"]]
            row = dict(family=fam, method=method, runs=len(group), exact=sum(r["hit"] for r in group))
            row.update({f"within_{t:g}": sum(g <= t for g in gaps) for t in TOLERANCES})
            row.update(max_distinct_final=max(len(v) for v in conditions.values()),
                       min_miss_gap=min(misses) if misses else None,
                       max_miss_gap=max(misses) if misses else None)
            require(row["exact"] <= row["within_0.001"], "Exact hit outside relaxed tolerance")
            out.append(row)
    return out


PAIRED = [("rbfopt_msrsm_genetic", "dsda")]
CASE_ORDER = ["cstr_5", "cstr_10", "cstr_15", "cstr_20", "cstr_25", "cstr_30", "column", "small_batch", "dynamic"]


def mcnemar_exact(first_only, second_only):
    """Two-sided exact McNemar test: binomial test on the discordant pairs."""
    n, k = first_only + second_only, min(first_only, second_only)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def paired_rows(rows):
    """Seed-paired target outcomes per process condition and pooled over CSTR sizes."""
    hits = {(r["case"], r["budget"], r["seed"], r["method"]): r["hit"]
            for r in rows if r["scope"] == "process"}
    conditions = sorted({(c, b) for c, b, _, _ in hits}, key=lambda k: (CASE_ORDER.index(k[0]), k[1]))
    groups = [(c, b, [(c, b)]) for c, b in conditions]
    groups.insert(6, ("cstr_all", None, [k for k in conditions if k[0].startswith("cstr_")]))
    out = []
    for first, second in PAIRED + [("bam", "rbfopt_msrsm_genetic")]:
        for case, budget, members in groups:
            if first == "bam" and case != "cstr_5":
                continue
            pairs = [(hits[c, b, s, first], hits[c, b, s, second]) for c, b in members for s in range(10)]
            counts = dict(both=sum(a and b for a, b in pairs), first_only=sum(a and not b for a, b in pairs),
                          second_only=sum(b and not a for a, b in pairs),
                          neither=sum(not a and not b for a, b in pairs))
            out.append(dict(case=case, budget=budget, first=first, second=second, pairs=len(pairs),
                            **counts, p_exact=mcnemar_exact(counts["first_only"], counts["second_only"])))
    return out


def paired_table(rows):
    names = {"cstr_all": r"\texttt{CSTR}, all sizes", "column": r"\texttt{Column}",
             "small_batch": r"\texttt{Small Batch}", "dynamic": r"\texttt{Dynamic}",
             **{f"cstr_{n}": rf"\texttt{{CSTR{n}}}" for n in (5, 10, 15, 20, 25, 30)}}
    lines = [r"\begin{tabular}{llrrrrrr}\toprule",
             r"Contrast & Case & \(B\) & Both & First only & Second only & Neither & \(p\)\\\midrule"]
    for r in rows:
        contrast = f"{LABELS[r['first']]} vs {LABELS[r['second']]}"
        p = r["p_exact"]
        if p == 1:
            p = "1"
        elif p < 1e-3:
            mantissa, exponent = f"{p:.2e}".split("e")
            p = rf"\({mantissa}\times10^{{{int(exponent)}}}\)"
        else:
            p = g3(p)
        lines.append(f"{contrast} & {names[r['case']]} & {r['budget'] or '--'} & {r['both']} & "
                     f"{r['first_only']} & {r['second_only']} & {r['neither']} & {p} \\\\")
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def overhead_rows(rows):
    """Median per-evaluation configuration cost and search time per evaluation."""
    out = []
    for fam in ["grid"] + [f for f, _ in FAMILIES]:
        group = [r for r in rows if (r["scope"] == "grid" if fam == "grid"
                                     else r["scope"] == "process" and family(r["case"]) == fam)]
        row = dict(family=fam, runs=len(group),
                   evaluation_cost_s=statistics.median(r["point_cost_s"] / r["evaluations"] for r in group))
        for method in METHODS:
            row[f"search_per_evaluation_s_{method}"] = statistics.median(
                r["search_s"] / r["evaluations"] for r in group if r["method"] == method)
        out.append(row)
    return out


def enumeration_rows():
    """Distinct fixed configurations behind every GDPopt NLP subproblem."""
    out = []
    for archive in sorted((GDPOPT / "evidence").glob("*.zip")):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                match = re.match(r"run/jobs/process__(.+)__(ric|loa|gloa)/gdp_path\.jsonl$", name)
                if not match:
                    continue
                events = [json.loads(x) for x in z.read(name).splitlines()]
                configs = [tuple(sorted((k, round(v)) for k, v in e["binary_values"].items()))
                           for e in events if e["event"] == "before_subproblem"]
                calls = [json.loads(x) for x in
                         z.read(name.replace("gdp_path", "solver_calls")).splitlines()]
                ipopt = sum(c["solver"] == "ipopt" and c["mtype"] == "nlp" for c in calls)
                require(ipopt == len(configs), f"Subproblem/IPOPT mismatch: {match[1]} {match[2]}")
                out.append(dict(case=match[1], method=match[2], subproblems=len(configs),
                                distinct_configurations=len(set(configs)),
                                admissible_configurations=ADMISSIBLE.get(match[1]),
                                source=f"{archive.relative_to(m.ROOT)}#{name}"))
    require(len(out) == 27, "Expected 27 process GDPopt jobs")
    return sorted(out, key=lambda r: (r["case"], r["method"]))


COVERAGE = m.ROOT / "results/dsda_publication_20261028/tables/configuration_coverage.csv"
FULL_TABLE = "dsda_abs1e5_rerun_20261028_020753_2004611/reproduction/inputs/process/{}_full.csv"


def enumeration_cost_rows(rows):
    """Cost and NLP solves of evaluating every configuration of each DFO box once."""
    statuses = defaultdict(list)
    for r in m.read(COVERAGE):
        statuses[r["case"]].append(r["status"])
    prep = {}
    for r in rows:
        if r["scope"] == "process":
            prep.setdefault(r["case"], set()).add(float(r["prep_s"]))
    require(all(len(v) == 1 for v in prep.values()), "Preparation cost differs between runs")
    out = []
    with zipfile.ZipFile(DSDA_ARCHIVE) as z:
        for case in CASE_ORDER:
            table = list(csv.DictReader(z.read(FULL_TABLE.format(case)).decode().splitlines()))
            require(len(table) == len(statuses[case]), f"Coverage and lookup sizes differ: {case}")
            costs = [float(t["total_wall_s"]) for t in table]
            require(all(math.isfinite(c) and c > 0 for c in costs), f"Missing point cost: {case}")
            (prep_s,) = prep[case]
            out.append(dict(case=case, configurations=len(table),
                            nlp_solves=sum(s in ("accepted", "rejected", "solver_error") for s in statuses[case]),
                            point_cost_s=math.fsum(costs), prep_s=prep_s,
                            enumeration_s=math.fsum(costs) + prep_s))
    return out


def spread_table(rows):
    lines = [r"\begin{tabular}{llrrrrrr}\toprule",
             r"Family & Method & Exact & \(\leq0.1\%\) & \(\leq1\%\) & \(\leq5\%\) & "
             r"\makecell{Distinct\\finals} & \makecell{Miss gap\\range (\%)}\\\midrule"]
    for i, (fam, label) in enumerate(FAMILIES):
        group = [r for r in rows if r["family"] == fam]
        for j, r in enumerate(group):
            gap = ("--" if r["min_miss_gap"] is None else
                   f"{g3(100 * r['min_miss_gap'])}--{g3(100 * r['max_miss_gap'])}")
            first = rf"\multirow{{5}}{{*}}{{{label}}}" if j == 0 else ""
            lines.append(f"{first} & {LABELS[r['method']]} & {r['exact']}/{r['runs']} & "
                         f"{r['within_0.001']} & {r['within_0.01']} & {r['within_0.05']} & "
                         f"{r['max_distinct_final']} & {gap} \\\\")
        lines.append(r"\midrule" if i < len(FAMILIES) - 1 else r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def overhead_table(rows):
    names = {"grid": "Grid-GDP", **dict(FAMILIES)}
    lines = [r"\begin{tabular}{lrrrrrr}\toprule",
             r" & & \multicolumn{5}{c}{Search time per evaluation (ms)}\\\cmidrule(l){3-7}",
             r"Family & \makecell{Evaluation\\cost (s)} & "
             + " & ".join(LABELS[mm] for mm in METHODS) + r"\\\midrule"]
    for r in rows:
        lines.append(f"{names[r['family']]} & {g3(r['evaluation_cost_s'])} & "
                     + " & ".join(g3(1e3 * r[f'search_per_evaluation_s_{mm}']) for mm in METHODS) + r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def write_csv(path, rows):
    with Path(path).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(out):
    require(not out.exists() or not any(out.iterdir()), "Output directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    rows, refs = load_runs(), references()
    spread, overhead, enumeration = spread_rows(rows, refs), overhead_rows(rows), enumeration_rows()
    paired = paired_rows(rows)
    write_csv(out / "enumeration_cost.csv", enumeration_cost_rows(rows))
    write_csv(out / "paired_exact_tests.csv", paired)
    (out / "paired_exact_tests.tex").write_text(paired_table(paired))
    write_csv(out / "process_spread_tolerance.csv", spread)
    write_csv(out / "evaluation_cost_overhead.csv", overhead)
    write_csv(out / "gdpopt_enumeration.csv", enumeration)
    (out / "process_spread_tolerance.tex").write_text(spread_table(spread))
    (out / "evaluation_cost_overhead.tex").write_text(overhead_table(overhead))
    m.dump(out / "references.json", refs)
    files = sorted(p for p in out.iterdir() if p.is_file())
    m.dump(out / "manifest.json", {
        "no_new_experiments": True,
        "input_sha256": {str(RUNS.relative_to(m.ROOT)): m.sha(RUNS),
                         str(DSDA_ARCHIVE.relative_to(m.ROOT)): DSDA_ARCHIVE_SHA256,
                         **{str(p.relative_to(m.ROOT)): m.sha(p)
                            for p in sorted((GDPOPT / "evidence").glob("*.zip"))}},
        "source_sha256": {str(Path(__file__).relative_to(m.ROOT)): m.sha(__file__)},
        "outputs_sha256": {p.name: m.sha(p) for p in files},
        "gap_definition": "(best accepted objective - f_ref) / max(1, |f_ref|), as in the target rule",
        "evaluation_cost": "median over runs of summed point cost divided by evaluations, all five methods",
        "search_per_evaluation": "median over runs of stored search_s divided by evaluations",
        "paired_test": "two-sided exact McNemar test on seed-paired target outcomes; descriptive, unadjusted",
        "environment": {"python": platform.python_version()},
        "reproduce": "python -m review_comparison.revision_diagnostics --output /tmp/revision-diagnostics",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output.resolve())


if __name__ == "__main__":
    main()
