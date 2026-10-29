"""Adopt completed CSTR30 initialization records without running optimization."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from copy import deepcopy
import csv
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics as st
import sys
import tempfile
import zipfile

from . import manuscript as m

ROOT = m.ROOT
PENALTY = ROOT / "results/cstr_penalty_1e6_analysis_20261022"
INITIALIZATION = ROOT / "results/cstr30_initialization_analysis_20261025"
COVERAGE = ROOT / "results/review_process_coverage_20261021"
ARCHIVE = ROOT / "results/archives/cstr30_init_20261025_060540_98uz54ol.zip"
OLD_CSTR = ROOT / "results/archives/ipopt_dfo_cstr_20261015_174637_r1dzn5tk.zip"
OLD_NON_CSTR = ROOT / "results/archives/ipopt_dfo_non_cstr_20261015_172428_o671edu_.zip"
REVISION = "df060f6f6974f8deb8ac085ee908b9e99f666b36"
METHOD_MAP = {"rbfopt": m.GEN, **{s: s for s in m.PRIMARY if s != m.GEN}}
PROCESS_FIGURES = (
    "process_evaluation_profiles", "process_completion_profiles",
    "process_cost_breakdown", "process_completion_scatter",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-10)


def csvwrite(path, rows):
    """Write new publication tables with deterministic repository line endings."""
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def key(row):
    return tuple(row[k] for k in ("scope", "case", "budget", "seed", "method"))


def validate_slots(rows, expected, label):
    keys = [key(r) for r in rows]
    require(len(keys) == len(set(keys)), f"Duplicate {label} pairing key")
    require(set(keys) == expected, f"Missing or unexpected {label} pairing key")


def check_hashes(directory, manifest, field, names):
    hashes = json.loads((directory / manifest).read_text())[field]
    for name in names:
        require(m.sha(directory / name) == hashes[name], f"Input hash mismatch: {name}")


def input_paths():
    return [
        m.BASE / "manifest.json", m.BASE / "tables/completed_runs.csv", m.ARCHIVE,
        ROOT / "results/grid_gdp_dfo_20261011/runs.csv",
        ROOT / "results/process_ipopt_bam_v2_20261015/tables/run_results.csv",
        PENALTY / "manifest.json", PENALTY / "paired_runs.csv",
        PENALTY / "callback_paths.csv", COVERAGE / "manifest.json",
        COVERAGE / "configuration_coverage.csv", ARCHIVE,
        INITIALIZATION / "audit_manifest.json", INITIALIZATION / "artifact_checksums.json",
        INITIALIZATION / "returned/paired_runs.csv",
        INITIALIZATION / "returned/evaluations.csv",
        OLD_CSTR, OLD_NON_CSTR, ROOT / "results/archives/PROCESS_SHA256SUMS",
    ]


def load_records():
    """Keep historical providers intact and replace whole run records by key."""
    check_hashes(PENALTY, "manifest.json", "outputs_sha256", ("paired_runs.csv", "callback_paths.csv"))
    check_hashes(COVERAGE, "manifest.json", "outputs_sha256", ("configuration_coverage.csv",))
    init_manifest = json.loads((INITIALIZATION / "audit_manifest.json").read_text())
    require(m.sha(ARCHIVE) == init_manifest["archive_sha256"], "Initialization archive hash mismatch")
    checksums = json.loads((INITIALIZATION / "artifact_checksums.json").read_text())["files"]
    for name in ("returned/paired_runs.csv", "returned/evaluations.csv", "audit_manifest.json"):
        p = INITIALIZATION / name
        require(m.sha(p) == checksums[str(p.relative_to(ROOT))], f"Initialization input changed: {name}")
    original, _, _ = m.load()
    records = deepcopy(original)
    index = {key(r): r for r in records}
    expected = {
        ("process", c, b, s, method)
        for c, b in m.CONDITIONS if c.startswith("cstr_")
        for s in range(10) for method in ("dsda", m.GEN)
    }
    replacements = []
    for p in m.read(PENALTY / "paired_runs.csv"):
        k = ("process", p["case"], int(p["budget"]), int(p["seed"]), METHOD_MAP[p["method"]])
        require(k in expected, "Unexpected finite-penalty slot")
        row = deepcopy(index[k])
        require(row["category"] == p["baseline_category"] and
                row["evaluations"] == int(p["baseline_charged_evaluations"]) and
                close(row["best_objective"], p["baseline_best_accepted_objective"]),
                "Finite-penalty baseline differs from retained publication")
        row.update(
            category=p["category"], best_objective=float(p["best_accepted_objective"]),
            evaluations=int(p["charged_evaluations"]), search_s=float(p["retained_search_s"]),
            lookup_s=float(p["lookup_s"]), point_cost_s=float(p["point_cost_sum_s"]), prep_s=0.,
            record_source=str((PENALTY / "paired_runs.csv").relative_to(ROOT)) + "#" + p["job_id"],
            lookup_accounting="measured lookup excluded from search",
            total_s=float(p["estimated_completion_s"]), hit=p["category"] == "target_reached",
            first_hit=int(p["first_target_evaluation"]) if p["category"] == "target_reached" else None,
        )
        replacements.append(row)
    validate_slots(replacements, expected, "finite-penalty")
    for row in replacements:
        index[key(row)].update(row)
    finite_records = deepcopy(records)
    pairs = m.read(INITIALIZATION / "returned/paired_runs.csv")
    evaluations = m.read(INITIALIZATION / "returned/evaluations.csv")
    points = {tuple(json.loads(r["point"])): r for r in evaluations}
    require(len(evaluations) == len(points) == 900 and
            set(points) == {(i, j) for i in range(1, 31) for j in range(1, 31)},
            "Missing or duplicate CSTR30 evaluation coordinates")
    expected_init = {("process", "cstr_30", 43, s, method) for s in range(10) for method in m.PRIMARY}
    replacements, callback_rows = [], []
    with zipfile.ZipFile(ARCHIVE) as archive:
        prefix = ARCHIVE.stem + "/"
        for name in ("paired_runs.csv", "evaluations.csv"):
            require(archive.read(prefix + name) == (INITIALIZATION / "returned" / name).read_bytes(),
                    f"Archived and published initialization records differ: {name}")
        for p in pairs:
            k = ("process", p["case"], int(p["budget"]), int(p["seed"]), METHOD_MAP[p["method"]])
            require(k in expected_init, "Unexpected initialization slot")
            row = deepcopy(index[k])
            require(row["category"] == p["old_category"] and
                    row["evaluations"] == int(p["old_callbacks"]) and
                    close(row["best_objective"], p["old_best_objective"]) and
                    close(row["total_s"], p["old_completion_s"]),
                    f"Initialization baseline differs from finite-penalty cohort: {k}")
            events = [json.loads(line) for line in archive.read(
                prefix + "searches/" + p["job_id"] + "/callbacks.jsonl").decode().splitlines()]
            result = json.loads(archive.read(prefix + "searches/" + p["job_id"] + "/effective_result.json"))
            require(result.get("process_nlp_calls", 0) == 0, "Search unexpectedly called process NLP")
            require([e["index"] for e in events] == list(range(1, len(events) + 1)) and
                    len(events) == int(p["new_callbacks"]), "Incomplete initialization callback sequence")
            target = float(p["new_target"])
            require(target == float(p["old_target"]), "Reference target changed")
            hits, costs = [], []
            for event in events:
                point = tuple(event["point"])
                source = points[point]
                require(event["source_row"]["record_sha256"] == source["record_sha256"],
                        "Callback uses a different evaluation attempt")
                accepted = source["accepted"] == "True"
                require(event["accepted"] == accepted, "Callback acceptance differs from evaluation")
                require((event["raw_objective"] is None and not accepted) or
                        (accepted and close(event["raw_objective"], source["objective"])),
                        "Callback objective differs from evaluation")
                cost = float(source["total_wall_s"])
                require(close(event["selected_attempt_nlp_s"], cost), "Callback cost differs from evaluation")
                costs.append(cost)
                if accepted and abs(event["raw_objective"] - target) <= 1e-5 * max(1, abs(target)):
                    hits.append(event["index"])
                callback_rows.append(dict(case="cstr_30", method=METHOD_MAP[p["method"]],
                    budget=43, seed=int(p["seed"]), index=event["index"], point=json.dumps(point),
                    accepted=accepted, objective=event["raw_objective"], point_cost_s=cost,
                    evaluation_record_sha256=source["record_sha256"]))
            require(close(math.fsum(costs), p["new_point_cost_s"]), "New point-cost sum differs")
            hit = p["new_category"] == "target_reached"
            require(hit == (p["new_target_hit"] == "True") and bool(hits) == hit,
                    "First-hit and final-best target classification disagree")
            row.update(
                category=p["new_category"], best_objective=float(p["new_best_objective"]),
                evaluations=int(p["new_callbacks"]), search_s=float(p["new_retained_search_s"]),
                lookup_s=float(p["new_lookup_s"]), point_cost_s=float(p["new_point_cost_s"]), prep_s=0.,
                record_source=str(ARCHIVE.relative_to(ROOT)) + "#searches/" + p["job_id"],
                lookup_accounting="measured lookup excluded; same-attempt new evaluation costs",
                total_s=float(p["new_completion_s"]), hit=hit, first_hit=hits[0] if hit else None,
            )
            replacements.append(row)
    validate_slots(replacements, expected_init, "initialization")
    for row in replacements:
        index[key(row)].update(row)
    for old, new in zip(original, records):
        if key(old) not in expected | expected_init:
            require(old == new, f"Unrelated historical record changed: {key(old)}")
    for old, new in zip(finite_records, records):
        if key(old) not in expected_init:
            require(old == new, "Non-CSTR30 finite-penalty record changed")
    groups = defaultdict(list)
    for row in records:
        require(close(row["total_s"], row["search_s"] + row["point_cost_s"] + row["prep_s"]),
                "Completion components do not sum")
        groups[row["scope"], row["case"], row["budget"], row["method"]].append(row)
    primary = [r for r in records if r["scope"] == "process" and r["method"] in m.PRIMARY]
    validate_slots(primary, {("process", c, b, s, method) for c, b in m.CONDITIONS
                            for s in range(10) for method in m.PRIMARY}, "primary Process")
    return records, groups, primary, callback_rows, evaluations


def coverage(callbacks, evaluations, primary):
    rows = m.read(COVERAGE / "configuration_coverage.csv")
    index = {(r["case"], tuple(json.loads(r["coordinates"]))): r for r in rows}
    require(len(index) == len(rows) == 2455, "Duplicate or missing inventory keys")
    for row in rows:
        for method in m.PRIMARY:
            row[method] = int(row[method])
        if row["case"].startswith("cstr_"):
            row["dsda"] = row[m.GEN] = 0
    for event in m.read(PENALTY / "callback_paths.csv"):
        if event["policy"] == "1e6":
            index[event["case"], tuple(json.loads(event["point"]))][METHOD_MAP[event["method"]]] += 1
    for row in rows:
        if row["case"] == "cstr_30":
            for method in m.PRIMARY:
                row[method] = 0
    for event in callbacks:
        index[event["case"], tuple(json.loads(event["point"]))][event["method"]] += 1
    for evaluation in evaluations:
        row = index["cstr_30", tuple(json.loads(evaluation["point"]))]
        row.update(accepted=evaluation["accepted"], status=evaluation["status"])
    output = []
    for row in rows:
        output.append({k: row[k] for k in ("case", "model", "model_size", "coordinates", "accepted", "status")}
                      | {"primary_callbacks": sum(row[method] for method in m.PRIMARY)}
                      | {method: row[method] for method in m.PRIMARY})
    require(sum(r["primary_callbacks"] for r in output) == sum(r["evaluations"] for r in primary),
            "Coverage callbacks differ from run records")
    for case in {r["case"] for r in primary}:
        for method in m.PRIMARY:
            require(sum(r[method] for r in output if r["case"] == case) ==
                    sum(r["evaluations"] for r in primary if r["case"] == case and r["method"] == method),
                    f"Coverage method/case mismatch: {case}, {method}")
    return output


def condition_summary(groups):
    output = []
    for case, budget in m.CONDITIONS:
        for method in m.PRIMARY:
            rows = groups["process", case, budget, method]
            output.append(dict(case=case, budget=budget, method=method, runs=len(rows),
                hits=sum(r["hit"] for r in rows), rate=st.mean(r["hit"] for r in rows),
                execution_failures=sum(r["category"] == "execution_failed" for r in rows),
                callbacks=sum(r["evaluations"] for r in rows),
                mean_completion_s=st.mean(r["total_s"] for r in rows),
                median_completion_s=st.median(r["total_s"] for r in rows),
                mean_search_s=st.mean(r["search_s"] for r in rows),
                mean_point_cost_s=st.mean(r["point_cost_s"] for r in rows),
                mean_preparation_s=st.mean(r["prep_s"] for r in rows)))
    return output


def fmqa_fallback(primary):
    """Count retained proposal sources, replacing only the ten CSTR30 traces."""
    hashes = {name: digest for digest, name in
              (line.split() for line in (ROOT / "results/archives/PROCESS_SHA256SUMS").read_text().splitlines())}
    for archive in (OLD_CSTR, OLD_NON_CSTR):
        require(m.sha(archive) == hashes[str(archive.relative_to(ROOT))], "FMQA proposal archive changed")
    output = []
    with ExitStack() as stack:
        archives = {path: stack.enter_context(zipfile.ZipFile(path))
                    for path in (ARCHIVE, OLD_CSTR, OLD_NON_CSTR)}
        for row in sorted(primary, key=key):
            if row["method"] != "fmqa_sa":
                continue
            path = ARCHIVE if row["case"] == "cstr_30" else OLD_CSTR if row["case"].startswith("cstr_") else OLD_NON_CSTR
            job = f"{row['case']}_B{row['budget']}_seed{row['seed']}_fmqa_sa"
            member = f"{path.stem}/{'searches' if path == ARCHIVE else 'jobs'}/{job}/proposals.jsonl"
            proposals = [json.loads(line) for line in archives[path].read(member).decode().splitlines()]
            require(len(proposals) == row["evaluations"] - 3 and
                    [e["iteration"] for e in proposals] == list(range(1, len(proposals) + 1)),
                    "FMQA proposal count differs from post-initial callbacks")
            sources = Counter(e["source"] for e in proposals)
            require(set(sources) <= {"simulated_annealing", "uniform_unseen_fallback"}, "Unknown FMQA proposal source")
            output.append(dict(case=row["case"], budget=row["budget"], seed=row["seed"],
                proposals=len(proposals), fallback=sources["uniform_unseen_fallback"],
                simulated_annealing=sources["simulated_annealing"],
                archive=str(path.relative_to(ROOT)), member=member))
    return output


def build(output):
    require(not output.exists(), "Use a new output directory")
    records, groups, primary, callbacks, evaluations = load_records()
    cover = coverage(callbacks, evaluations, primary)
    conditions = condition_summary(groups)
    fallback = fmqa_fallback(primary)
    pairs = [m.process_pair(groups, case, budget, new, ref) for new, ref in
             [(m.GEN, "dsda"), ("fmqa_sa", m.UNI)] for case, budget in m.CONDITIONS]
    output.mkdir(parents=True)
    tables, figures = output / "tables", output / "figures"
    tables.mkdir()
    figures.mkdir()
    csvwrite(tables / "run_records.csv", records)
    csvwrite(tables / "primary_process_runs.csv", sorted(primary, key=key))
    csvwrite(tables / "cstr30_callbacks.csv", callbacks)
    csvwrite(tables / "condition_summary.csv", conditions)
    csvwrite(tables / "paired_process.csv", pairs)
    csvwrite(tables / "configuration_coverage.csv", cover)
    csvwrite(tables / "fmqa_fallback_runs.csv", fallback)
    fallback_summary = [dict(scope=scope, runs=len(rows), proposals=sum(r["proposals"] for r in rows),
                             fallback=sum(r["fallback"] for r in rows),
                             fraction=sum(r["fallback"] for r in rows) / sum(r["proposals"] for r in rows))
                        for scope, rows in [("all_process", fallback),
                            ("cstr", [r for r in fallback if r["case"].startswith("cstr_")]),
                            ("cstr_30", [r for r in fallback if r["case"] == "cstr_30"])]]
    csvwrite(tables / "fmqa_fallback_summary.csv", fallback_summary)
    case_coverage = [dict(case=c, inventory=len(rr), accepted=sum(r["accepted"] == "True" for r in rr),
                        visited=sum(r["primary_callbacks"] > 0 for r in rr),
                        callbacks=sum(r["primary_callbacks"] for r in rr))
                     for c in sorted({r["case"] for r in cover})
                     for rr in [[r for r in cover if r["case"] == c]]]
    csvwrite(tables / "case_coverage.csv", case_coverage)
    # Reuse frozen publication styles without editing or republishing historical contrasts.
    with tempfile.TemporaryDirectory(prefix="cstr30-publication-") as temp:
        temporary = Path(temp)
        (temporary / "tables").mkdir()
        (temporary / "figures").mkdir()
        m.tables(records, groups, temporary / "tables")
        for name in ("process_hits.tex", "process_cost.tex", "process_intervals.tex"):
            shutil.copyfile(temporary / "tables" / name, tables / name)
        m.figures(records, groups, temporary / "figures")
        for name in PROCESS_FIGURES:
            for ext in ("pdf", "png"):
                shutil.copyfile(temporary / "figures" / f"{name}.{ext}", figures / f"{name}.{ext}")
        values = json.loads((temporary / "figures/figure_values.json").read_text())
        m.dump(figures / "figure_values.json", [r for r in values if r["scope"] == "process"])
    summary = dict(primary_runs=len(primary), outcomes=dict(Counter(r["category"] for r in primary)),
        primary_callbacks=sum(r["evaluations"] for r in primary),
        visited_configurations=sum(r["primary_callbacks"] > 0 for r in cover),
        accepted_inventory=sum(r["accepted"] == "True" for r in cover),
        cstr_hits={method: sum(r["hit"] for r in primary if r["case"].startswith("cstr_") and
                             r["method"] == method) for method in m.PRIMARY},
        process_hits={method: sum(r["hit"] for r in primary if r["method"] == method) for method in m.PRIMARY},
        cstr30={r["method"]: r for r in conditions if r["case"] == "cstr_30"})
    m.dump(tables / "summary.json", summary)
    lines = [
        "# CSTR30 initialization adoption for publication", "",
        "This follow-up analysis uses completed records and runs no optimizer or NLP solver.",
        "The original 8,190-record analysis is retained, with 120 finite-penalty CSTR D-SDA/RBFOpt records overlaid before replacing all 50 CSTR30 records.",
        "The primary Process comparison contains 700 runs over 14 conditions and ten paired seeds per method.",
        "Relative to the finite-penalty primary cohort, the other 650 Process runs are unchanged.",
        "All Grid runs and historical solver-option contrasts retain their original records.",
        "CSTR30 uses the mass-balance/zero-recycle initializer, the existing reference target, and each new evaluation attempt's own objective, acceptance and measured cost.",
        "The archive retains the one GAMS execution error at [27,10], which none of the 50 new searches visited.", "",
        "| Method | CSTR30 hits / 10 | All CSTR hits / 60 | CSTR30 median completion (s) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for method in m.PRIMARY:
        row = summary["cstr30"][method]
        lines.append(f"| {m.LABEL[method]} | {row['hits']} | {summary['cstr_hits'][method]} | {row['median_completion_s']:.2f} |")
    lines += ["",
        f"The primary cohort visits {summary['visited_configurations']:,} distinct model/size/coordinate keys using {summary['primary_callbacks']:,} charged callbacks.",
        f"The complete Process inventory contains {summary['accepted_inventory']:,} accepted configurations, including {sum(r['accepted'] == 'True' for r in evaluations)} of the 900 CSTR30 coordinates.",
        "Completion cost is measured lookup-search time minus measured lookup time plus the new recorded evaluation cost for every callback, including repeats and rejected points.",
        "CSTR30 timing includes its recorded initialization and artifact-retention work, while other cases retain their existing measurement conventions.",
        "These conditional recorded-path estimates do not isolate the causal timing effect of initialization or establish a pure IPOPT slowdown.",
        "Per-condition success intervals use the existing exact binomial convention, and paired differences use 2,000 percentile bootstrap replications with seed 20261020 over paired seeds within each condition.",
        "The paired intervals are descriptive, can degenerate with ten seeds, and are neither equivalence tests nor multiplicity-adjusted superiority claims.",
        "Dynamic budgets and CSTR sizes remain separate conditions, with the all-CSTR success sum used only as a descriptive aggregate.",
        "The four Process figures retain the existing publication colors, labels and panel layout.",
        "Historical solver-versus-genetic comparisons are neither regenerated nor relabeled as comparisons against this adopted initialization.", "",
        "The FMQA-SA fallback tables count the archived proposal sources for all 140 Process runs, replacing only the ten CSTR30 traces.",
        "These counts describe candidate provenance and do not isolate the causal contribution of model fitting or annealing.", "",
        "Reproduce in a new directory from the repository root:", "", "```bash",
        "python -m review_comparison.cstr30_publication --output /tmp/cstr30-publication-new",
        "python -m pytest tests/test_cstr30_publication.py -q", "```", "",
        "Input, source and output hashes, retained execution revisions and the generation environment are recorded in manifest.json.",
    ]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    audit = json.loads((INITIALIZATION / "audit_manifest.json").read_text())
    m.dump(output / "manifest.json", dict(
        baseline_revision=REVISION, no_new_optimization_or_nlp_runs=True,
        overlay_order=["120 finite-penalty CSTR D-SDA/RBFOpt records", "50 CSTR30 initialization records"],
        unchanged_grid_records=7350, primary_process_runs=len(primary),
        historical_execution_provider_revision="38d917ef75ef6767c2a9f238d88be19bf0b89160",
        cstr30_execution_source_revision=audit["execution_source_revision"],
        cstr30_baseline_revision=audit["baseline_revision"],
        input_sha256={str(p.relative_to(ROOT)): m.sha(p) for p in input_paths()},
        source_sha256={str(p.relative_to(ROOT)): m.sha(p) for p in
                       [Path(__file__), ROOT / "review_comparison/manuscript.py", ROOT / "review_comparison/analysis.py"]},
        bootstrap=dict(seed=20261020, replications=2000, unit="paired seeds within each condition", ordering="seed 0 through 9"),
        environment=dict(python=sys.version, platform=platform.platform(), matplotlib=__import__("matplotlib").__version__),
        reproduce="python -m review_comparison.cstr30_publication --output /tmp/cstr30-publication-new",
        outputs_sha256={str(p.relative_to(output)): m.sha(p) for p in sorted(output.rglob("*")) if p.is_file()},
    ))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "cstr30-publication-mpl"))
    print(json.dumps(build(args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
