"""Adopt the completed Column logical-domain/B13 runs without optimization."""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics as st
import sys
import tempfile
import zipfile

from . import manuscript as m
from .cstr30_publication import require, close, key, validate_slots, csvwrite
from .process_figures import figures

BASE = m.ROOT / "results/cstr30_publication_20261025"
COLUMN = m.ROOT / "results/column_logical_b13_analysis_20261025"
CONDITIONS = [(c, 13 if c == "column" else b) for c, b in m.CONDITIONS]
PANELS = [(c, 13 if c == "column" else b) for c, b in m.PANELS]
METHOD_MAP = {"rbfopt": m.GEN, **{method: method for method in m.PRIMARY}}
DOMAIN = {(i, j) for i in range(8, 16) for j in range(1, 9)}


def verified(directory, names):
    manifest = json.loads((directory / "manifest.json").read_text())
    for name in names:
        require(m.sha(directory / name) == manifest["outputs_sha256"][name],
                f"Input hash mismatch: {directory.name}/{name}")


def typed_records(rows):
    rows = deepcopy(rows)
    for r in rows:
        for name in ("budget", "seed", "evaluations"):
            r[name] = int(r[name])
        for name in ("search_s", "point_cost_s", "prep_s", "total_s"):
            r[name] = float(r[name])
        r["hit"] = r["hit"] == "True"
        r["first_hit"] = int(r["first_hit"]) if r["first_hit"] else None
    return rows


def overlay(records, new_runs, callbacks, lookup):
    """Replace all fifty Column records, validating paired seeds and raw costs."""
    replacements = [dict(scope="process", case="column", budget=int(r["budget"]),
                         seed=int(r["seed"]), method=METHOD_MAP[r["method"]]) for r in new_runs]
    expected = {("process", "column", 13, s, method) for s in range(10) for method in m.PRIMARY}
    validate_slots(replacements, expected, "Column")
    points = {tuple(json.loads(r["point"])): r for r in lookup}
    require(len(points) == len(lookup) == 64 and set(points) == DOMAIN,
            "Missing, duplicate or out-of-domain Column lookup coordinates")
    event_groups = defaultdict(list)
    for e in callbacks:
        event_groups[METHOD_MAP[e["method"]], int(e["seed"])].append(e)
    require(set(event_groups) == {(method, s) for method in m.PRIMARY for s in range(10)},
            "Unexpected or missing Column callback group")
    result = deepcopy(records)
    old = {key(r): r for r in result}
    old_slots = {("process", "column", 16, s, method) for method in m.PRIMARY for s in range(10)}
    validate_slots([r for r in records if key(r) in old_slots], old_slots, "baseline Column")
    initials = {}
    for raw, slot in zip(new_runs, replacements):
        method, seed = slot["method"], slot["seed"]
        row = old["process", "column", 16, seed, method]
        events = sorted(event_groups[method, seed], key=lambda e: int(e["index"]))
        require([int(e["index"]) for e in events] == list(range(1, len(events) + 1)) and
                len(events) == int(raw["callbacks"]) <= 13, "Incomplete Column callback sequence")
        starts = [json.loads(e["point"]) for e in events[:3]]
        require(len(starts) == 3 and len(set(map(tuple, starts))) == 3, "Invalid shared starts")
        require(seed not in initials or initials[seed] == starts, "Methods use different shared starts")
        initials[seed] = starts
        hits, costs, objectives = [], [], []
        target = float(raw["target"])
        require(close(target, 19346.124801006445), "Column target changed")
        for e in events:
            coordinate = tuple(json.loads(e["point"]))
            require(coordinate in points, "Column callback outside logical domain")
            source = points[coordinate]
            require(json.loads(e["source_row"]) == source, "Column callback uses another evaluation record")
            accepted = source["accepted"] == "True"
            require((e["accepted"] == "True") == accepted, "Column callback acceptance mismatch")
            cost = float(source["total_wall_s"])
            require(close(e["point_cost_s"], cost), "Column callback cost mismatch")
            costs.append(cost)
            if accepted:
                objective = float(source["objective"])
                require(close(e["raw_objective"], objective), "Column callback objective mismatch")
                objectives.append(objective)
                if abs(objective - target) <= 1e-5 * max(1, abs(target)):
                    hits.append(int(e["index"]))
        hit = raw["category"] == "target_reached"
        require(hit == (raw["target_hit"] == "True") == bool(hits), "Column target classification mismatch")
        require(raw["protocol_error"] == "False" and raw["missing_cost_points"] == "[]",
                "Column run has incomplete protocol or costs")
        require(close(min(objectives), raw["best_objective"]), "Column incumbent differs from callbacks")
        require(close(math.fsum(costs), raw["point_cost_s"]), "Column point-cost sum mismatch")
        require(close(raw["completion_s"], float(raw["retained_search_s"]) + math.fsum(costs)),
                "Column completion components do not sum")
        require((int(raw["first_hit"]) if raw["first_hit"] else None) == (hits[0] if hit else None),
                "Column first-hit mismatch")
        row.update(slot, category=raw["category"], best_objective=raw["best_objective"],
                   evaluations=len(events), search_s=float(raw["retained_search_s"]),
                   lookup_s=raw["lookup_s"], point_cost_s=math.fsum(costs), prep_s=0.,
                   total_s=float(raw["completion_s"]), hit=hit, first_hit=hits[0] if hit else None,
                   record_source=str((COLUMN / "replayed/runs.csv").relative_to(m.ROOT)) + "#" + raw["job_id"],
                   lookup_accounting="measured lookup excluded; unchanged same-attempt Column point costs")
    for before, after in zip(records, result):
        if key(before) not in old_slots:
            require(before == after, "Non-Column or historical solver record changed")
    return result


def load_records():
    verified(BASE, ["tables/run_records.csv", "tables/configuration_coverage.csv", "tables/fmqa_fallback_runs.csv"])
    verified(COLUMN, ["replayed/runs.csv", "replayed/callback_ledger.csv"])
    manifest = json.loads((COLUMN / "manifest.json").read_text())
    archive = COLUMN / manifest["archive_path"]
    require(m.sha(archive) == manifest["archive_sha256"], "Column return archive changed")
    with zipfile.ZipFile(archive) as z:
        prefix = z.namelist()[0].split("/")[0] + "/"
        lookup_bytes = z.read(prefix + "reproduction/inputs/column_64.csv")
        import hashlib
        require(hashlib.sha256(lookup_bytes).hexdigest() == manifest["inputs"]["evaluation_table_sha256"],
                "Column evaluation table changed")
        lookup = list(csv.DictReader(io.StringIO(lookup_bytes.decode())))
    old = typed_records(m.read(BASE / "tables/run_records.csv"))
    runs = [r for r in m.read(COLUMN / "replayed/runs.csv") if r["condition"] == "64_B13"]
    callbacks = m.read(COLUMN / "replayed/callback_ledger.csv")
    records = overlay(old, runs, callbacks, lookup)
    groups = defaultdict(list)
    for row in records:
        groups[row["scope"], row["case"], row["budget"], row["method"]].append(row)
    primary = [r for r in records if r["scope"] == "process" and r["method"] in m.PRIMARY]
    validate_slots(primary, {("process", c, b, s, method) for c, b in CONDITIONS
                            for s in range(10) for method in m.PRIMARY}, "primary Process")
    return records, groups, primary, callbacks, lookup, archive, prefix


def coverage(callbacks, lookup, primary):
    points = {tuple(json.loads(r["point"])): r for r in lookup}
    result = []
    for row in m.read(BASE / "tables/configuration_coverage.csv"):
        coordinate = tuple(json.loads(row["coordinates"]))
        if row["case"] == "column" and coordinate not in points:
            require(row["accepted"] == "False", "Cannot drop an accepted Column configuration")
            continue
        for method in m.PRIMARY:
            row[method] = 0 if row["case"] == "column" else int(row[method])
        if row["case"] == "column":
            require(row["accepted"] == points[coordinate]["accepted"], "Column inventory acceptance changed")
        result.append(row)
    index = {(r["case"], tuple(json.loads(r["coordinates"]))): r for r in result}
    for event in callbacks:
        index["column", tuple(json.loads(event["point"]))][METHOD_MAP[event["method"]]] += 1
    for row in result:
        row["primary_callbacks"] = sum(row[method] for method in m.PRIMARY)
    for case, method in {(r["case"], r["method"]) for r in primary}:
        require(sum(r[method] for r in result if r["case"] == case) ==
                sum(r["evaluations"] for r in primary if r["case"] == case and r["method"] == method),
                "Coverage callback totals differ from primary runs")
    return result


def fallback_runs(archive, prefix):
    rows = [r for r in m.read(BASE / "tables/fmqa_fallback_runs.csv") if r["case"] != "column"]
    for r in rows:
        for field in ("budget", "seed", "proposals", "fallback", "simulated_annealing"):
            r[field] = int(r[field])
    with zipfile.ZipFile(archive) as z:
        for seed in range(10):
            member = prefix + f"jobs/column_logical_B13_seed{seed}_fmqa_sa/attempt_0001/proposals.jsonl"
            proposals = [json.loads(line) for line in z.read(member).decode().splitlines()]
            require([r["iteration"] for r in proposals] == list(range(1, 11)), "Incomplete Column FMQA proposals")
            counts = Counter(r["source"] for r in proposals)
            require(set(counts) <= {"uniform_unseen_fallback", "simulated_annealing"}, "Unknown proposal source")
            rows.append(dict(case="column", budget=13, seed=seed, proposals=len(proposals),
                             fallback=counts["uniform_unseen_fallback"], simulated_annealing=counts["simulated_annealing"],
                             archive=str(archive.relative_to(m.ROOT)), member=member))
    return sorted(rows, key=lambda r: (r["case"], r["budget"], r["seed"]))


def build(output):
    require(not output.exists(), "Use a new output directory")
    records, groups, primary, callbacks, lookup, archive, prefix = load_records()
    cover = coverage(callbacks, lookup, primary)
    fallback = fallback_runs(archive, prefix)
    output.mkdir(parents=True)
    tables, figdir = output / "tables", output / "figures"
    tables.mkdir()
    figdir.mkdir()
    csvwrite(tables / "run_records.csv", records)
    csvwrite(tables / "primary_process_runs.csv", sorted(primary, key=key))
    csvwrite(tables / "configuration_coverage.csv", cover)
    csvwrite(tables / "column_callbacks.csv", callbacks)
    csvwrite(tables / "fmqa_fallback_runs.csv", fallback)
    condition_rows = []
    for case, budget in CONDITIONS:
        for method in m.PRIMARY:
            rows = groups["process", case, budget, method]
            condition_rows.append(dict(case=case, budget=budget, method=method, runs=len(rows),
                hits=sum(r["hit"] for r in rows), execution_failures=sum(r["category"] == "execution_failed" for r in rows),
                callbacks=sum(r["evaluations"] for r in rows), median_completion_s=st.median(r["total_s"] for r in rows),
                median_search_s=st.median(r["search_s"] for r in rows), median_point_cost_s=st.median(r["point_cost_s"] for r in rows)))
    csvwrite(tables / "condition_summary.csv", condition_rows)
    pairs = [m.process_pair(groups, c, b, new, ref) for new, ref in
             [(m.GEN, "dsda"), ("fmqa_sa", m.UNI)] for c, b in CONDITIONS]
    csvwrite(tables / "paired_process.csv", pairs)
    for kind in ("hits", "cost"):
        lines = []
        for c, b in CONDITIONS:
            cells = [f"{sum(r['hit'] for r in groups['process', c, b, method])}/10" if kind == "hits" else
                     f"{st.median(r['total_s'] for r in groups['process', c, b, method]):.2f}" for method in m.PRIMARY]
            lines.append(f"{m.pname(c)} & {b} & " + " & ".join(cells) + r" \\")
        (tables / f"process_{kind}.tex").write_text("\n".join(lines) + "\n")
    fallback_summary = []
    for family in ("cstr", "column", "dynamic", "small_batch", "all_process"):
        rows = [r for r in fallback if family == "all_process" or
                (r["case"].startswith("cstr_") if family == "cstr" else r["case"] == family)]
        proposals, count = sum(r["proposals"] for r in rows), sum(r["fallback"] for r in rows)
        fallback_summary.append(dict(family=family, runs=len(rows), proposals=proposals, fallback=count, fraction=count/proposals))
    csvwrite(tables / "fmqa_fallback_summary.csv", fallback_summary)
    case_coverage = [dict(case=c, inventory=len(rows), accepted=sum(r["accepted"] == "True" for r in rows),
                         visited=sum(r["primary_callbacks"] > 0 for r in rows), callbacks=sum(r["primary_callbacks"] for r in rows))
                     for c in sorted({r["case"] for r in cover}) for rows in [[r for r in cover if r["case"] == c]]]
    csvwrite(tables / "case_coverage.csv", case_coverage)
    figures(groups, figdir, PANELS, [("column", 13), ("cstr_30", 43), ("small_batch", 10), ("dynamic", 50)])
    summary = dict(primary_runs=len(primary), outcomes=dict(Counter(r["category"] for r in primary)),
                   primary_callbacks=sum(r["evaluations"] for r in primary), inventory=len(cover),
                   visited_configurations=sum(r["primary_callbacks"] > 0 for r in cover),
                   accepted_inventory=sum(r["accepted"] == "True" for r in cover),
                   process_hits={method: sum(r["hit"] for r in primary if r["method"] == method) for method in m.PRIMARY},
                   column={r["method"]: r for r in condition_rows if r["case"] == "column"})
    m.dump(tables / "summary.json", summary)
    lines = ["# Column logical-domain/B13 adoption for publication", "",
             "This analysis replaces all fifty primary Column runs with the completed 64-configuration/B13 follow-up.",
             "The other 650 primary Process runs, every Grid run, and historical solver-option results are unchanged.",
             "The original experimental archives, targets, acceptance records and execution revisions are preserved.",
             "The Column candidate rectangle is exactly the original model's logical domain; algebraic feasibility remains determined by the retained evaluation records.",
             "All methods share three ordered initial configurations and retain ten seeds in their denominator.",
             "The new domain, budget and regenerated initial designs differ together from the historical cohort, so their separate effects are not identified.", "",
             "| Method | Column hits / 10 | Median reconstructed completion (s) |", "| --- | ---: | ---: |"]
    for method in m.PRIMARY:
        row = summary["column"][method]
        lines.append(f"| {m.LABEL[method]} | {row['hits']} | {row['median_completion_s']:.2f} |")
    lines += ["", "Seed 6 includes the reference target as its third shared initial point, accounting for the only BAM and uniform successes.",
              "RBFOpt does not improve target-hit frequency over D-SDA on this condition; a one-seed difference does not establish a general ranking.",
              "RBFOpt's larger reconstructed cost is associated with expensive unaccepted configurations, while its median search overhead decreases relative to the historical run.",
              "Completion costs combine measured search overhead and unchanged same-attempt point costs charged on every callback, including repeats and unsuccessful evaluations.",
              "They are not measured online optimizer-NLP runtimes.",
              f"The adopted 700-run cohort has {summary['primary_callbacks']:,} callbacks and {summary['visited_configurations']:,} distinct visited configuration keys.",
              f"Its candidate inventory contains {summary['inventory']:,} configurations, including {summary['accepted_inventory']:,} accepted responses.",
              "Paired percentile intervals resample ten paired seeds within each condition with seed 20261020 and 2,000 replications.",
              "They are descriptive, can degenerate, and are not equivalence tests or multiplicity-adjusted evidence of superiority.",
              "The FMQA-SA proposal counts replace the ten Column traces and retain every other recorded proposal source.",
              "This analysis runs no optimizer, fitting, annealing or NLP solver.", "", "Reproduce in a new directory:", "", "```bash",
              "python -m review_comparison.column_publication --output /tmp/column-publication-new",
              "python -m pytest tests/test_column_publication.py -q", "```", ""]
    (output / "README.md").write_text("\n".join(lines))
    paths = [BASE / "manifest.json", COLUMN / "manifest.json", archive]
    paths += [BASE / name for name in ("tables/run_records.csv", "tables/configuration_coverage.csv", "tables/fmqa_fallback_runs.csv")]
    paths += [COLUMN / name for name in ("replayed/runs.csv", "replayed/callback_ledger.csv")]
    m.dump(output / "manifest.json", dict(baseline_revision="647019991f16d931c3f9f1905b35de885bc0bcd0", no_new_optimizer_or_nlp_calls=True,
        column_execution_revision=json.loads((COLUMN / "manifest.json").read_text())["source_base_revision"],
        preceding_publication_manifest=str((BASE / "manifest.json").relative_to(m.ROOT)),
        input_sha256={str(p.relative_to(m.ROOT)): m.sha(p) for p in paths},
        source_sha256={str(p.relative_to(m.ROOT)): m.sha(p) for p in
                      [Path(__file__), Path(__file__).with_name("process_figures.py"), Path(m.__file__), Path(__file__).with_name("analysis.py"), Path(__file__).with_name("cstr30_publication.py")]},
        bootstrap=dict(seed=20261020, replications=2000, unit="paired seeds within each condition", order="seed 0 through 9"),
        environment=dict(python=sys.version, platform=platform.platform(), matplotlib=__import__("matplotlib").__version__),
        reproduce="python -m review_comparison.column_publication --output /tmp/column-publication-new",
        outputs_sha256={str(p.relative_to(output)): m.sha(p) for p in sorted(output.rglob("*")) if p.is_file()}))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "column-publication-mpl"))
    print(json.dumps(build(args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
