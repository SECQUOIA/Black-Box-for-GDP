"""Summarize the seven-method lomustine runs; stored responses only, no simulation.

  python experiments/lomustine_simulation/analyze.py --runs DIR --output DIR

Reads plan.json and runs/<job>/{spec,result}.json and callbacks.jsonl written by
experiments/catalytic_distillation_live/run.py with LIVE_DFO_CASE pointing to case.py.
A run reaches the target when its best accepted objective is within the relative
tolerance 1e-5 of the best objective of the 36 enumerated configurations.  As in the
PR #56 NOMAD runs, a native crash that repeats on both attempts after identical
evaluations is scored on the evaluations completed before the crash, and counted.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("lomustine_case", HERE / "case.py")
case = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(case)

METHODS = ["dsda", "nomad", "rbfopt", "miso", "bam", "fmqa_sa", "uniform"]
TEX = {"dsda": r"\texttt{D-SDA}", "nomad": r"\texttt{NOMAD}", "rbfopt": r"\texttt{RBFOpt}", "miso": r"\texttt{MISO}",
       "bam": r"\texttt{BAM}", "fmqa_sa": r"\texttt{FMQA-SA}", "uniform": "Uniform"}
HIT_RTOL = 1e-5


def sig3(x):
    return f"{x:#.3g}".rstrip(".")


def identical_attempts(directory, calls):
    """Every attempt evaluated the same configurations as the recorded path."""
    attempts = sorted(directory.glob("attempt*.jsonl"))
    paths = [[json.loads(line)["point"] for line in a.read_text().splitlines()] for a in attempts]
    return len(paths) >= 2 and all(p == [c["point"] for c in calls] for p in paths)


def load(runs):
    plan = json.loads((runs / "plan.json").read_text())
    if Path(plan["case"]).name != "case.py" or plan["case_sha256"] != case.sha256(HERE / "case.py"):
        raise ValueError("Runs were planned with a different case module")
    if plan.get("case_options", case.OPTIONS) != case.OPTIONS:
        raise ValueError("Set LOMUSTINE_ORDER and LOMUSTINE_OBJECTIVE as in the planned runs")
    rows = []
    for job in plan["jobs"]:
        d = runs / "runs" / job["job_id"]
        result = json.loads((d / "result.json").read_text())
        calls = [json.loads(line) for line in (d / "callbacks.jsonl").read_text().splitlines()]
        crashed = result["status"].startswith("crashed_exit_") and identical_attempts(d, calls)
        if len(calls) != result["evaluations"] or not (
                crashed or result["status"] in ("completed", "completed_after_verified_rerun")):
            raise ValueError(f"Incomplete run {job['job_id']}")
        rows.append(dict(job=job, result=result, calls=calls, crashed=crashed))
    if len(rows) != len(plan["jobs"]):
        raise ValueError("Missing runs")
    return plan, rows


def summarize(rows, reference):
    target = HIT_RTOL * max(1.0, abs(reference))
    out = []
    for r in rows:
        calls, job = r["calls"], r["job"]
        first = next((c["index"] for c in calls if c["accepted"] and abs(c["raw_objective"] - reference) <= target), None)
        out.append(dict(method=job["method"], budget=job["budget"], seed=job["seed"], crashed_identical=r["crashed"],
                        hit=first is not None,
                        first_hit=first, best_objective=r["result"]["best_objective"],
                        evaluations=len(calls), distinct=len({tuple(c["point"]) for c in calls}),
                        point_cost_h=sum(c["point_cost_s"] for c in calls) / 3600,
                        search_s=r["result"]["search_overhead_s"],
                        completion_h=r["result"]["completion_s"] / 3600))
    return out


def conditions(runs):
    out = []
    for b in sorted({r["budget"] for r in runs}):
        for m in METHODS:
            g = [r for r in runs if r["budget"] == b and r["method"] == m]
            hits = [r["first_hit"] for r in g if r["hit"]]
            out.append(dict(budget=b, method=m, runs=len(g), hits=len(hits),
                            median_first_hit=statistics.median(hits) if hits else None,
                            median_best_objective=statistics.median(r["best_objective"] for r in g),
                            median_completion_h=statistics.median(r["completion_h"] for r in g),
                            median_search_s=statistics.median(r["search_s"] for r in g)))
    return out


def table(cond):
    budgets = sorted({c["budget"] for c in cond})
    lines = [r"\begin{tabular}{@{}l" + "c" * len(budgets) + "@{}}\\toprule",
             "Method & " + " & ".join(rf"\(B={b}\)" for b in budgets) + r"\\\midrule"]
    top = {b: max(c["hits"] for c in cond if c["budget"] == b) for b in budgets}
    for m in METHODS:
        cells = []
        for b in budgets:
            c = next(c for c in cond if c["budget"] == b and c["method"] == m)
            h = rf"\textbf{{{c['hits']}}}" if c["hits"] == top[b] else str(c["hits"])
            cells.append(rf"\makecell{{{h}\\{sig3(c['median_completion_h'])}}}")
        lines.append(TEX[m] + " & " + " & ".join(cells) + r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def configurations_table(responses):
    """Objective and inner-optimization time of all 36 configurations, R01-R02 rows by CR01 columns."""
    names = {"batch": "batch", "CSTR": "CSTR", "PFR": "PFR"}
    head = ("R01 & R02 & " + " & ".join({"batchU": "batch", "cont1": "1 MSMPR", "cont2": "2 MSMPR",
                                         "cont3": "3 MSMPR"}[c] for c in case.CRYSTALLIZERS) + r"\\\midrule")
    lines = [r"\begin{tabular}{@{}ll" + "r" * len(case.CRYSTALLIZERS) + "@{}}\\toprule", head]
    best = min(r["objective"] for r in responses.values())
    for i, r1 in enumerate(case.REACTORS):
        for j, r2 in enumerate(case.REACTORS):
            cells = []
            for k in range(len(case.CRYSTALLIZERS)):
                r = responses[i, j, k]
                value = f"{r['objective']:.2f}"
                value = rf"\textbf{{{value}}}" if r["objective"] == best else value
                cells.append(rf"\makecell{{{value}\\({r['inner_optimization_s']:.0f}~s)}}")
            lines.append(f"{names[r1]} & {names[r2]} & " + " & ".join(cells) + r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    return "\n".join(lines) + "\n"


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    responses = case.table()
    best = min(responses, key=lambda p: responses[p]["objective"])
    reference = responses[best]["objective"]
    plan, rows = load(args.runs)
    runs = summarize(rows, reference)
    cond = conditions(runs)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "runs.csv", runs)
    write_csv(args.output / "conditions.csv", cond)
    (args.output / "hits_table.tex").write_text(table(cond))
    (args.output / "configurations_table.tex").write_text(configurations_table(responses))
    enumeration_h = sum(r["inner_optimization_s"] for r in responses.values()) / 3600
    facts = dict(reference_objective=reference, reference_point=list(best), reference_layout=list(case.positions(best)),
                 configurations=len(responses), enumeration_h=enumeration_h,
                 inner_optimization_s=dict(min=min(r["inner_optimization_s"] for r in responses.values()),
                                           max=max(r["inner_optimization_s"] for r in responses.values())),
                 objective_range=[min(r["objective"] for r in responses.values()),
                                  max(r["objective"] for r in responses.values())],
                 simulations_per_configuration=sorted({r["simulations"] for r in responses.values()}),
                 continuous_variables=sorted({r["continuous_variables"] for r in responses.values()}),
                 runs=len(runs), crashed_identical_runs=[f"{r['method']}_B{r['budget']}_seed{r['seed']}"
                                                         for r in runs if r["crashed_identical"]],
                 options=case.OPTIONS, starts={k: v for k, v in plan["starts"].items()},
                 case_sha256=plan["case_sha256"], data_sha256=case.DATA_SHA256)
    (args.output / "facts.json").write_text(json.dumps(facts, indent=2) + "\n")
    files = sorted(p for p in args.output.iterdir() if p.name != "manifest.json")
    (args.output / "manifest.json").write_text(json.dumps(dict(
        source_sha256={p: hashlib.sha256((HERE / p).read_bytes()).hexdigest() for p in ("case.py", "analyze.py")},
        outputs_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        reproduce="python experiments/lomustine_simulation/analyze.py --runs RUNS --output OUT"), indent=2) + "\n")
    for c in cond:
        print(c)
    print(json.dumps({k: v for k, v in facts.items() if k != "starts"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
