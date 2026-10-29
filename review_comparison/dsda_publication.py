"""Adopt completed D-SDA tolerance runs; read data only, never run a search."""

import argparse
from collections import defaultdict
import copy
import csv
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics as st
import sys
import zipfile

from . import manuscript as m
from .analysis import paired_interval
from .column_publication import CONDITIONS, PANELS, typed_records, verified
from .cstr30_publication import require, close, key, validate_slots, csvwrite
from .grid_figures import figures as grid_figures
from .process_figures import figures as process_figures

BASE = m.ROOT / "results/column_publication_20261025"
GRID = m.ROOT / "results/archives/dsda_grid_target_stop_20261028_032943_2346732.zip"
PROCESS = m.ROOT / "results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip"
HASHES = {
    GRID: "3611ba036df02ef8b155e32be7557c4bf7b88dfa1a5aff6e91c6d82fe7fb135a",
    PROCESS: "e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e",
}
POINTS = m.ROOT / "results/grid_gdp_20261009/raw/point_timings.csv"
REVISION = "b8fc38b31ee0ef9cb6ad28f4b5e41add53694c6c"


def read_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def hit(value, target):
    return (
        value is not None
        and math.isfinite(value)
        and abs(value - target) <= 1e-5 * max(1, abs(target))
    )


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    return (
        "infinity" if isinstance(value, float) and not math.isfinite(value) else value
    )


def load_inputs():
    verified(BASE, ["tables/run_records.csv", "tables/configuration_coverage.csv"])
    for path, digest in HASHES.items():
        require(m.sha(path) == digest, f"Changed return archive: {path.name}")
    # The common Grid costs must be the exact table supplied to the original comparison.
    with zipfile.ZipFile(m.ARCHIVE) as z:
        member = next(
            n for n in z.namelist() if n.endswith("/data/grid_point_timings.csv")
        )
        require(z.read(member) == POINTS.read_bytes(), "Grid point-cost table changed")
    cost_rows = m.read(POINTS)
    grid_costs = {(r["grid_name"], tuple(json.loads(r["point"]))): r for r in cost_rows}
    require(
        len(grid_costs) == len(cost_rows) == 21 * 961,
        "Duplicate/missing Grid point costs",
    )
    baseline = typed_records(m.read(BASE / "tables/run_records.csv"))
    results = []
    for scope, path in [("grid", GRID), ("process", PROCESS)]:
        with zipfile.ZipFile(path) as z:
            prefix = path.stem + "/"
            jobs = json.loads(z.read(prefix + "reproduction/inputs/jobs.json"))
            jobs = [j for j in jobs if j["spec"]["scope"] == scope]
            for job in jobs:
                spec = job["spec"]
                member = prefix + "runs/" + spec["job_id"] + "/"
                result = json.loads(z.read(member + "result.json"))
                require(result["spec"] == spec, "Job/result specification mismatch")
                events = [
                    json.loads(line)
                    for line in z.read(member + "callbacks.jsonl").splitlines()
                ]
                lookup = None
                if scope == "process":
                    source = read_csv(
                        z.read(
                            prefix
                            + "reproduction/inputs/process/"
                            + spec["case"]
                            + "_full.csv"
                        )
                    )
                    # Selected attempts are checked against their complete retained row.
                    lookup = [
                        {k: v for k, v in r.items() if k != "cost_source"}
                        for r in source
                    ]
                results.append(
                    (
                        job,
                        result,
                        events,
                        lookup,
                        str(path.relative_to(m.ROOT)) + "#" + member,
                    )
                )
    return baseline, grid_costs, results


def overlay(baseline, grid_costs, results):
    records = copy.deepcopy(baseline)
    index = {key(r): r for r in records}
    require(len(index) == len(records), "Duplicate baseline run")
    expected = {key(r) for r in baseline if r["method"] == "dsda"}
    actual = [key(j["spec"]) for j, _, _, _, _ in results]
    require(
        len(actual) == len(set(actual))
        and set(actual) == expected
        and len(actual) == 1190,
        "Missing, duplicate, or unexpected D-SDA pairing",
    )
    callbacks, pairs = [], []
    for job, result, events, lookup, provenance in sorted(
        results, key=lambda x: key(x[0]["spec"])
    ):
        s = job["spec"]
        row = index[key(s)]
        before = dict(row)
        require(
            result["error"] is None and result["category"] != "execution_failed",
            "Failed D-SDA run",
        )
        require(result["improvement_abs_tol"] == 1e-5, "Wrong improvement criterion")
        require(
            result["process_nlp_calls"] == 0
            and not result["blocked_solver_or_process_attempts"],
            "Unexpected solver invocation",
        )
        if s["scope"] == "grid":
            require(
                result["target_stop_rule"] == "adopted_analysis.hit",
                "Wrong Grid stopping predicate",
            )
        target = job["target"]
        require(
            [e["index"] for e in events] == list(range(1, result["evaluations"] + 1))
            and 3 <= len(events) <= s["budget"],
            "Incomplete callback sequence",
        )
        require(
            [e["point"] for e in events[:3]] == s["starts"],
            "Shared initial design changed",
        )
        costs, values, first = [], [], None
        for e in events:
            p = tuple(e["point"])
            require(
                len(p) == len(s["lower"])
                and all(lo <= x <= hi for x, lo, hi in zip(p, s["lower"], s["upper"])),
                "Point outside candidate domain",
            )
            if s["scope"] == "grid":
                source = grid_costs[s["case"], p]
                require(
                    e["accepted"]
                    and close(e["raw_objective"], source["csv_objective"]),
                    "Grid response mismatch",
                )
                cost = float(source["point_wall_s"])
            else:
                if e["source_row"] is None:
                    candidates = [
                        r for r in lookup if tuple(json.loads(r["point"])) == p
                    ]
                    require(
                        len(candidates) == 1
                        and not e["accepted"]
                        and e["evaluation_state"] == "logical_exclusion_unmeasured"
                        and candidates[0]["accepted"] == "False"
                        and candidates[0]["logical_allowed"] == "False",
                        "Unexplained missing callback source",
                    )
                    source = candidates[0]
                else:
                    source = dict(e["source_row"])
                    source.pop("csv_line", None)
                    require(
                        any(
                            all(
                                source.get(k, "") == r.get(k, "")
                                for k in source.keys() | r.keys()
                            )
                            for r in lookup
                        ),
                        "Process callback does not match an archived evaluation attempt",
                    )
                require(
                    (source["accepted"] == "True") == e["accepted"],
                    "Process acceptance mismatch",
                )
                require(
                    not e["accepted"] or close(e["raw_objective"], source["objective"]),
                    "Process response mismatch",
                )
                cost = float(source["total_wall_s"])
                require(
                    e["source_row"] is None or close(cost, e["selected_attempt_nlp_s"]),
                    "Process attempt/cost mismatch",
                )
            require(
                math.isfinite(cost) and cost > 0, "Missing or nonpositive point cost"
            )
            costs.append(cost)
            if e["accepted"]:
                values.append(e["raw_objective"])
                if first is None and hit(e["raw_objective"], target):
                    first = e["index"]
            callbacks.append(
                dict(
                    scope=s["scope"],
                    case=s["case"],
                    budget=s["budget"],
                    seed=s["seed"],
                    index=e["index"],
                    point=json.dumps(list(p)),
                    accepted=e["accepted"],
                    raw_objective=e["raw_objective"],
                    point_cost_s=cost,
                    record_source=provenance + "callbacks.jsonl",
                )
            )
        require(
            values and close(min(values), result["best_objective"]),
            "Observed incumbent mismatch",
        )
        success = hit(result["best_objective"], target)
        require(
            success == result["hit"] == (result["category"] == "target_reached")
            and first == result["first_hit"],
            "Target classification mismatch",
        )
        require(
            close(sum(e["lookup_wall_s"] for e in events), result["lookup_s"]),
            "Lookup timer mismatch",
        )
        search = result["search_s"] - result["lookup_s"]
        require(math.isfinite(search) and search >= 0, "Invalid retained search time")
        row.update(
            category=result["category"],
            best_objective=result["best_objective"],
            evaluations=len(events),
            search_s=search,
            lookup_s=result["lookup_s"],
            point_cost_s=math.fsum(costs),
            total_s=search + math.fsum(costs) + row["prep_s"],
            hit=success,
            first_hit=first,
            record_source=provenance + "result.json",
            lookup_accounting="measured lookup excluded; original same-attempt point costs charged on new path",
        )
        pairs.append(
            dict(
                scope=s["scope"],
                case=s["case"],
                budget=s["budget"],
                seed=s["seed"],
                old_hit=before["hit"],
                new_hit=success,
                old_callbacks=before["evaluations"],
                new_callbacks=len(events),
                old_completion_s=before["total_s"],
                new_completion_s=row["total_s"],
                old_first_hit=before["first_hit"],
                new_first_hit=first,
            )
        )
    for old, new in zip(baseline, records):
        require(old["method"] == "dsda" or old == new, "Unrelated method changed")
    return records, callbacks, pairs


def summarize(records, callbacks):
    groups = defaultdict(list)
    for row in records:
        groups[row["scope"], row["case"], row["budget"], row["method"]].append(row)
    require(
        all(sorted(r["seed"] for r in rr) == list(range(10)) for rr in groups.values()),
        "Incomplete seed group",
    )
    primary = [
        r for r in records if r["scope"] == "process" and r["method"] in m.PRIMARY
    ]
    validate_slots(
        primary,
        {
            ("process", c, b, s, method)
            for c, b in CONDITIONS
            for s in range(10)
            for method in m.PRIMARY
        },
        "Process cohort",
    )
    coverage = m.read(BASE / "tables/configuration_coverage.csv")
    index = {(r["case"], tuple(json.loads(r["coordinates"]))): r for r in coverage}
    for r in coverage:
        for method in m.PRIMARY:
            r[method] = 0 if method == "dsda" else int(r[method])
    for e in callbacks:
        if e["scope"] == "process":
            index[e["case"], tuple(json.loads(e["point"]))]["dsda"] += 1
    for r in coverage:
        r["primary_callbacks"] = sum(r[method] for method in m.PRIMARY)
    require(
        sum(r["primary_callbacks"] for r in coverage)
        == sum(r["evaluations"] for r in primary),
        "Coverage counts mismatch",
    )
    summary = dict(
        process_runs=len(primary),
        process_hits=sum(r["hit"] for r in primary),
        process_callbacks=sum(r["evaluations"] for r in primary),
        visited_configurations=sum(r["primary_callbacks"] > 0 for r in coverage),
        inventory=len(coverage),
        accepted=sum(r["accepted"] == "True" for r in coverage),
        grid_B100={
            method: m.summarize(
                [
                    r
                    for r in records
                    if r["scope"] == "grid"
                    and r["budget"] == 100
                    and r["method"] == method
                ]
            )
            for method in m.GRID
        },
        process_conditions={
            f"{c}_B{b}": {
                method: m.summarize(groups["process", c, b, method])
                for method in m.PRIMARY
            }
            for c, b in CONDITIONS
        },
    )
    return groups, coverage, summary


def paired_grid(groups, budgets=m.BUDGETS):
    rows = []
    cases = sorted({k[1] for k in groups if k[0] == "grid"})
    for b in budgets:
        for new, ref in [
            (m.GEN, m.UNI),
            ("bam", m.PRE),
            ("fmqa_sa", m.UNI),
            ("dsda", m.GEN),
        ]:
            vectors = []
            for c in cases:
                a = {r["seed"]: r["hit"] for r in groups["grid", c, b, new]}
                d = {r["seed"]: r["hit"] for r in groups["grid", c, b, ref]}
                vectors.append([int(a[s]) - int(d[s]) for s in range(10)])
            low, high = paired_interval(
                vectors, seed=20261020, replications=2000, clustered=True
            )
            rows.append(
                dict(
                    budget=b,
                    new=new,
                    reference=ref,
                    difference=st.mean(st.mean(v) for v in vectors),
                    low=low,
                    high=high,
                    functions=len(cases),
                    paired_seeds=10,
                )
            )
    return rows


def interval(h):
    from scipy.stats import beta

    lo = 0 if h == 0 else beta.ppf(0.025, h, 11 - h)
    hi = 1 if h == 10 else beta.ppf(0.975, h + 1, 10 - h)
    return f"{h} [{lo:.2f}, {hi:.2f}]"


def build(output):
    require(not output.exists(), "Output must be a new directory")
    baseline, costs, results = load_inputs()
    records, callbacks, pairs = overlay(baseline, costs, results)
    groups, coverage, summary = summarize(records, callbacks)
    tables = output / "tables"
    figures = output / "figures"
    tables.mkdir(parents=True)
    figures.mkdir()
    for name, rows in [
        ("run_records", records),
        ("dsda_callbacks", callbacks),
        ("paired_adoption", pairs),
        ("configuration_coverage", coverage),
        ("paired_grid", paired_grid(groups)),
    ]:
        csvwrite(tables / (name + ".csv"), rows)
    csvwrite(
        tables / "paired_process.csv",
        [m.process_pair(groups, c, b, m.GEN, "dsda") for c, b in CONDITIONS],
    )

    def tex(name, lines):
        (tables / (name + ".tex")).write_text("\n".join(lines) + "\n")

    tex(
        "grid_hits",
        [
            str(b)
            + " & "
            + " & ".join(
                f"{100 * sum(r['hit'] for r in records if r['scope'] == 'grid' and r['budget'] == b and r['method'] == method) / 210:.1f}"
                for method in m.GRID
            )
            + r" \\"
            for b in m.BUDGETS
        ],
    )
    tex(
        "grid_cost",
        [
            f"{m.LABEL[method]} & {v['hits']}/210 & {v['median']:.2f} & {v['point']:.2f} & {v['search']:.4f}"
            + r" \\"
            for method, v in summary["grid_B100"].items()
        ],
    )
    for kind in ("hits", "cost"):
        tex(
            "process_" + kind,
            [
                f"{m.pname(c)} & {b} & "
                + " & ".join(
                    f"{m.summarize(groups['process', c, b, method])['hits']}/10"
                    if kind == "hits"
                    else f"{m.summarize(groups['process', c, b, method])['median']:.2f}"
                    for method in m.PRIMARY
                )
                + r" \\"
                for c, b in CONDITIONS
            ],
        )
    tex(
        "grid_intervals_B100",
        [
            m.pname(c)
            + " & "
            + " & ".join(
                interval(sum(r["hit"] for r in groups["grid", c, 100, method]))
                for method in m.GRID
            )
            + r" \\"
            for c in sorted({r["case"] for r in records if r["scope"] == "grid"})
        ],
    )
    selected = [
        r
        for r in records
        if r["scope"] == "grid"
        and r["budget"] == 100
        and r["case"] not in ("xin_she_yang3", "bohachevsky2")
    ]
    summary["grid_excluding_two"] = {
        method: sum(r["hit"] for r in selected if r["method"] == method) / 190
        for method in m.GRID
    }
    summary["grid_zero_hits"] = {
        method: sum(
            not any(r["hit"] for r in rr)
            for (sc, c, b, meth), rr in groups.items()
            if sc == "grid" and b == 100 and meth == method
        )
        for method in m.GRID
    }
    m.dump(tables / "summary.json", clean(summary))
    grid_figures(records, groups, figures)
    process_figures(
        groups,
        figures,
        PANELS,
        [("column", 13), ("cstr_30", 43), ("small_batch", 10), ("dynamic", 50)],
    )
    lines = [
        "# D-SDA tolerance adoption",
        "",
        "This is a data-only publication analysis of completed experiments.",
        "No optimizer, NLP solver, model fitting, or server experiment is invoked.",
        "Only the 1,050 Grid and 140 Process D-SDA records replace the preceding Column publication cohort.",
        "Every other method record is preserved exactly.",
        "",
        "D-SDA accepts a move only for a strict absolute objective improvement greater than 1e-5.",
        "Grid target stopping uses the common success predicate on the best observed objective at the existing post-descent checkpoint, after the budget-exhaustion check.",
        "It does not interrupt a descent immediately at the first target observation.",
        "Process retains its single best accepted initial configuration and no target-based stopping.",
        "The objective-improvement threshold, target test, and primal-feasibility threshold have different meanings.",
        "",
        "Completion estimates are rebuilt from each new callback path, charging the unchanged same-attempt point cost for every callback, including repeats and rejected evaluations.",
        "Retained search time is the new measured search duration minus its recorded lookup time; unchanged preparation cost is added once.",
        "These are fixed-path reconstructed costs, not measured online optimizer-NLP runtimes or evidence of a cross-run wall-time speedup.",
        "The Grid and Process execution environments and original provider revisions remain in their separate immutable return archives.",
        "",
        "Pairing uses scope, case, budget, seed and method, with exactly seeds 0 through 9 in every group.",
        "Grid bootstrap samples intact functions in sorted function order; Process bootstrap samples paired seeds separately within each condition.",
        "The descriptive percentile intervals use seed 20261020 and 2,000 replicates and do not establish equivalence or general superiority.",
        "",
        "| Grid budget | D-SDA target hits / 210 | Callbacks |",
        "|---|---:|---:|",
    ]
    for b in m.BUDGETS:
        rr = [
            r
            for r in records
            if r["scope"] == "grid" and r["method"] == "dsda" and r["budget"] == b
        ]
        lines.append(
            f"| {b} | {sum(r['hit'] for r in rr)} | {sum(r['evaluations'] for r in rr)} |"
        )
    lines += [
        "",
        f"The adopted Process cohort retains {summary['process_hits']}/700 target hits with {summary['process_callbacks']:,} callbacks and {summary['visited_configurations']:,} distinct visited configuration keys.",
        "Process target hits and first-hit indices remain unchanged; CSTR remains 14/60 for D-SDA and 45/60 for RBFOpt.",
        "The separate target-stopping follow-up preserves the preceding improvement-run Grid successes; relative to the previously published cohort the improvement change reduces Grid D-SDA hits from 382 to 374.",
        "",
        "Reproduce in a fresh directory:",
        "",
        "```bash",
        "python -m review_comparison.dsda_publication --output /tmp/dsda-publication-replay",
        "python -m pytest tests/test_dsda_publication.py -q",
        "```",
        "",
    ]
    (output / "README.md").write_text("\n".join(lines))
    inputs = [
        BASE / "manifest.json",
        BASE / "tables/run_records.csv",
        BASE / "tables/configuration_coverage.csv",
        POINTS,
        m.ARCHIVE,
        GRID,
        PROCESS,
    ]
    sources = [Path(__file__), Path(m.__file__)] + [
        Path(__file__).with_name(n + ".py")
        for n in (
            "grid_figures",
            "process_figures",
            "column_publication",
            "cstr30_publication",
            "analysis",
        )
    ]
    execution = {}
    for scope, path in [("grid", GRID), ("process", PROCESS)]:
        with zipfile.ZipFile(path) as archive:
            meta = json.loads(archive.read(path.stem + "/execution_manifest.json"))
            execution[scope] = dict(
                archive=str(path.relative_to(m.ROOT)),
                server_revision=meta["repository_identity"]["head"],
                utc_started=meta["utc_started"],
                utc_finished=meta["utc_finished"],
                execution_manifest_member=path.stem + "/execution_manifest.json",
            )
    m.dump(
        output / "manifest.json",
        dict(
            baseline_revision=REVISION,
            execution_records=execution,
            no_new_experiments=True,
            execution_provenance="Immutable Grid and Process return archives; not replaced by this analysis revision",
            input_sha256={str(p.relative_to(m.ROOT)): m.sha(p) for p in inputs},
            source_sha256={str(p.relative_to(m.ROOT)): m.sha(p) for p in sources},
            bootstrap=dict(
                seed=20261020,
                replications=2000,
                grid_unit="function with all 10 paired seeds",
                process_unit="paired seed within one condition",
                order="sorted case, then seed 0 through 9",
            ),
            environment=dict(
                python=sys.version,
                platform=platform.platform(),
                matplotlib=__import__("matplotlib").__version__,
                scipy=__import__("scipy").__version__,
            ),
            reproduce="python -m review_comparison.dsda_publication --output /tmp/dsda-publication-replay",
            outputs_sha256={
                str(p.relative_to(output)): m.sha(p)
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
        ),
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/dsda-publication-mpl")
    print(json.dumps(build(args.output.resolve()), indent=2))
