"""Audit saved full-GDP results without running an optimizer or NLP solver."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path

from fmqa_benchmark.protocol import problem, reference_plan
from gdp_models.comparison import (
    DESCEND, build_template, pyo, update_boolean_vars_from_binary, validate_original,
)
from nlp_cost_analysis import baseline_comparison, read_json, sha, write_csv, write_json


ROOT = Path(__file__).resolve().parent
METHODS = ("ric", "gloa", "bigm", "hull")
INSTANCES = tuple(f"cstr_{n}" for n in (5, 10, 15, 20, 25, 30)) + ("column", "dynamic", "small_batch")


def audit(directory, output):
    directory, output = Path(directory), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    run = read_json(directory / "run.json")
    summary = read_json(directory / "summary.json")
    checksums = (directory / "SHA256SUMS").read_text().splitlines()
    for line in checksums:
        digest, name = line.split("  ", 1)
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha(path) != digest:
            raise ValueError(f"Invalid source checksum: {name}")
    jobs = {(r["instance_id"], r["method"]): r for r in summary["results"]}
    expected = {(i, m) for i in INSTANCES for m in METHODS}
    assert len(summary["results"]) == len(jobs) == 36 and set(jobs) == expected
    assert summary["complete"] and not summary["pending_jobs"]
    assert all(v == "1" for v in run["thread_environment"].values())

    rechecks, calls = [], []
    for instance in INSTANCES:
        example = jobs[instance, "ric"]
        template = build_template(example["case"], cstr_size=example["cstr_size"] or 30)
        assert template.metadata["source"] == run["runtime"]["templates"][instance]["source"]
        for method in METHODS:
            row = jobs[instance, method]
            job = directory / "jobs" / instance / method
            assert read_json(job / "result.json") == row
            assert row["threads"] == 1 and row["time_limit_s"] == run["config"]["time_limit"]
            assert row["status"] != "running"
            if row["has_feasible_solution"]:
                solution = read_json(job / "solution.json")
                model = template.model.clone()
                logic = list(model.component_data_objects(pyo.LogicalConstraint, active=True, descend_into=DESCEND))
                pyo.TransformationFactory("core.logical_to_linear").apply_to(model)
                for constraint in logic:
                    constraint.activate()
                for var in model.component_data_objects(pyo.Var, descend_into=DESCEND):
                    if not var.fixed:
                        var.set_value(None)
                for name, value in solution["variables"].items():
                    var = model.find_component(name)
                    assert var is not None, name
                    var.set_value(value, skip_validation=True)
                update_boolean_vars_from_binary(model, integer_tolerance=1e-5)
                checked = validate_original(model)
                assert checked["has_feasible_solution"], (instance, method, checked)
                assert math.isclose(checked["candidate_objective"], row["objective"], rel_tol=1e-12, abs_tol=1e-9)
                assert math.isclose(solution["objective"], row["objective"], rel_tol=1e-12, abs_tol=1e-9)
                rechecks.append({"instance_id": instance, "method": method, **checked})
            call_path = job / "solver_calls.jsonl"
            entries = [json.loads(line) for line in call_path.read_text().splitlines()] if call_path.exists() else []
            assert len(entries) == row.get("solver_calls", len(entries))
            assert all(c.get("threads") == 1 for c in entries)
            if method in {"ric", "gloa"}:
                nlp = [c for c in entries if c["solver"] == "ipopt"]
                calls.append({"instance_id": instance, "method": method, "nlp_calls": len(nlp),
                              "terminations": dict(Counter(c.get("termination", c.get("status")) for c in nlp))})

    traces = [{"spec": {"case_name": s["case_name"], "grid_size": s["grid_size"]},
               "target": problem(s)["target"]} for s in reference_plan()]
    records = baseline_comparison(directory, output, traces)
    for row in records:
        row["relative_objective_gap"] = max(0, (row["objective"] - row["target_value"]) /
                                           max(1, abs(row["target_value"])))
    write_csv(output / "comparison.csv", records)
    conflicts = [{k: row[k] for k in ("instance_id", "method", "reported_lower_bound",
                 "best_saved_feasible_objective", "solver_reported_global_optimality_certified")}
                 for row in records if row["bound_conflict_with_saved_solution"]]
    affinity = run["cpu_affinity"]
    fmqa_affinities = {}
    for dataset in ("case", "grid"):
        fm = read_json(ROOT / "results/fmqa_20260925" / dataset / "run.json")
        info = fm["runtime"]["cpu_affinity"]
        assert fm["runtime"]["host"] == run["host"]
        assert affinity["effective_cpus"] != info["effective_cpus"]
        assert (affinity["physical_package_id"], affinity["core_id"]) != (info["physical_package_id"], info["core_id"])
        fmqa_affinities[dataset] = info
    audit_data = {
        "source_directory": str(directory), "source_summary_sha256": sha(directory / "summary.json"),
        "source_run_sha256": sha(directory / "run.json"), "verified_internal_checksums": len(checksums),
        "completed_jobs": len(jobs), "saved_solutions_independently_rechecked": len(rechecks),
        "termination_counts": dict(Counter(r["termination"] for r in jobs.values())),
        "target_hits": sum(r["target_hit"] for r in records),
        "target_hits_by_method": {m: sum(r["target_hit"] for r in records if r["method"] == m) for m in METHODS},
        "max_rechecked_primal_violation": max(r["max_primal_violation"] for r in rechecks),
        "cpu_affinity": affinity, "fmqa_affinities": fmqa_affinities,
        "distinct_physical_cores_from_fmqa": True, "single_thread_settings_verified": True,
        "bound_conflicts": conflicts, "gdpopt_nlp_statuses": calls,
        "global_certificate_policy": "Raw flags retained; cross-method conflicts exclude a certificate from derived outputs. Remaining flags are solver reports, not independent proofs.",
        "audit_source_sha256": sha(__file__), "local_validation": "Saved vectors loaded into original GDP models; no solver run",
    }
    write_json(output / "audit.json", audit_data)
    write_json(output / "solution_rechecks.json", rechecks)
    report(output, records, audit_data, run)
    print(json.dumps({k: v for k, v in audit_data.items() if k in {
        "completed_jobs", "saved_solutions_independently_rechecked", "termination_counts",
        "target_hits_by_method", "max_rechecked_primal_violation", "bound_conflicts"}}, indent=2))


def report(output, records, audit_data, run):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    jobs = {(r["instance_id"], r["method"]): r for r in records}
    names = ("RIC + IPOPT", "GLOA + IPOPT", "Big-M + BARON", "Hull + BARON")
    lines = ["# Full GDP comparison — September 25 CPU 2 rerun", "",
             "All 36 jobs completed and all 36 saved solutions pass a fresh original-GDP feasibility check. "
             "Twenty-seven report `optimal`; nine return at the solver time limit with feasible incumbents. "
             "An `optimal` termination string alone is not a global-optimality guarantee.", "",
             "GDP ran on CPU 2 (physical core 2, sibling 50); FMQA Grid used CPU 0 and FMQA cases CPU 4. "
             "The recorded physical cores are distinct, with one-thread settings. CPU affinity is not an exclusive reservation; background server load was not recorded.", "",
             "Each cell is **objective / completion seconds including one shared template preparation**. "
             "TL = solver time limit; † = reported bound conflicts with another saved feasible solution. "
             "Worker launch, preflight and final packaging are excluded. Lower objectives are better.", "",
             "| Model | " + " | ".join(names) + " |", "|---|---:|---:|---:|---:|"]
    table = []
    for instance in INSTANCES:
        cells = []
        for method in METHODS:
            row = jobs[instance, method]
            suffix = " TL" if row["termination"] == "maxTimeLimit" else ""
            if row["bound_conflict_with_saved_solution"]:
                suffix += " †"
            cells.append(f"{row['objective']:.8g} / {row['measured_total_with_preparation_s']:.2f}s{suffix}")
        table.append(cells)
        lines.append(f"| {instance} | " + " | ".join(cells) + " |")
    lines += ["", "## Findings", "",
              "- CSTR30 Big-M reaches the lookup target (2.769569795) and returns its solution at the 30-minute cap. "
              "Hull returns 2.809386231, about 1.44% above the target, despite an `optimal` flag. "
              "Its reported lower bound exceeds the independently checked Big-M feasible objective; the claimed global certificate is excluded from derived tables.",
              "- Column: RIC matches the target at about 82.21 s. The Big-M lower bound still conflicts with this better feasible solution.",
              "- Dynamic: RIC matches the target at about 104.00 s. GLOA, Big-M and Hull retain gaps of about 7.01%, 2.07% and 86.51%.",
              "- Small Batch: all four methods match the target. Big-M/Hull complete in about 0.55/0.57 s including preparation.",
              "- CSTR5–25 GDPopt still returns approximately 9.894737. Recorded IPOPT subproblem failures persist with separate CPUs; "
              "they are not evidence that the corresponding original GDP configurations are mathematically infeasible. "
              "Initialization and local NLP convergence remain unresolved factors.",
              "- CSTR10 Hull also has a numerical bound conflict: its objective differs from the better Big-M solution by about 1.81e-5 relatively. "
              "Both pass the recorded 1e-5 primal-feasibility threshold; this is a tolerance-sensitive comparison.", "",
              "## Target attainment", "",
              "Target hits across nine models: " + ", ".join(f"{name}: {audit_data['target_hits_by_method'][m]}/9" for m, name in zip(METHODS, names)) + ". "
              "These are nine different GDP instances, not repeated stochastic success probabilities. "
              "Success uses the existing lookup target and absolute error <= 1e-5 × max(1, |target|).", "",
              "## Current outputs", "",
              "- `comparison.csv`: all 36 objectives, target hits, completion times and bound flags.",
              "- `audit.json`: CPU topology, checksums, NLP statuses and bound conflicts.",
              "- `solution_rechecks.json`: independent evaluations of all saved vectors.",
              "- `gdp_objectives_and_times.png`: slide-ready table (generated locally).", "",
              "Reproduce without solving:", "",
              "```bash", "python gdp_comparison_analysis.py", "```", ""]
    (output / "README.md").write_text("\n".join(lines))
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.axis("off")
    artist = ax.table(cellText=[[c.replace(" / ", "\n") for c in row] for row in table],
                      rowLabels=INSTANCES, colLabels=names, cellLoc="center", rowLoc="center",
                      bbox=[.12, .10, .87, .80])
    artist.auto_set_font_size(False)
    artist.set_fontsize(10)
    for (r, c), cell in artist.get_celld().items():
        cell.set_edgecolor("#d6dce3")
        if r == 0:
            cell.set_facecolor("#203a53")
            cell.get_text().set_color("white")
        elif c == -1:
            cell.set_facecolor("#eef2f6")
        elif jobs[INSTANCES[r - 1], METHODS[c]]["bound_conflict_with_saved_solution"]:
            cell.set_facecolor("#fde5e2")
        elif jobs[INSTANCES[r - 1], METHODS[c]]["termination"] == "maxTimeLimit":
            cell.set_facecolor("#fff2d7")
    fig.suptitle("Full GDP benchmark: objective and completion time", fontsize=17)
    fig.text(.5, .925, "36 completed jobs; 36 independently checked feasible solutions; GDP CPU 2, FMQA CPUs 0 and 4", ha="center", fontsize=11)
    fig.text(.5, .055, "Completion includes template preparation. TL: solver time limit. †: bound conflicts with a better saved feasible solution.", ha="center", fontsize=10)
    fig.text(.5, .02, "Recorded execution times; no global optimality claim from termination text alone.", ha="center", fontsize=10)
    for ext in ("png", "pdf"):
        fig.savefig(output / f"gdp_objectives_and_times.{ext}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results/gdp_comparison_20260925/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "results/gdp_comparison_20260925/analysis")
    args = parser.parse_args()
    audit(args.results, args.output)
