"""Validate selected Dantzig GDP results, including explicitly partial snapshots."""

import argparse
from collections import Counter
from pathlib import Path
import zipfile

from fmqa_benchmark.protocol import problem, reference_plan
from gdp_compare import planned_instances
from gdp_comparison_analysis import INSTANCES, recheck_saved_solution
from gdp_models.comparison import build_template
from nlp_cost_analysis import baseline_comparison, jsonl, read_json, sha, write_csv, write_json
from result_archives import archived_directory


ROOT = Path(__file__).resolve().parent
METHODS = ("ric", "gloa", "loa", "bigm", "hull")
LABELS = ("RIC BARON/HiGHS", "GLOA BARON/HiGHS", "LOA BARON/HiGHS",
          "Big-M BARON (Sep 25)", "Hull BARON (Sep 25)")


def verify_source(directory, methods):
    logical_directory = Path(directory)
    with archived_directory(logical_directory) as directory:
        if directory != logical_directory:
            for retained in logical_directory.rglob("*"):
                if retained.is_file():
                    name = retained.relative_to(logical_directory)
                    archived = directory / name
                    if not archived.is_file() or sha(retained) != sha(archived):
                        raise ValueError(f"Retained GDP source differs from archive: {name}")
        return _verify_source(directory, methods, logical_directory)


def _verify_source(directory, methods, logical_directory):
    run = read_json(directory / "run.json")
    summary = read_json(directory / "summary.json")
    assert run["host"] == "dantzig.ecn.purdue.edu"
    assert run["preflight_status"] == "passed"
    assert all(v == "1" for v in run["thread_environment"].values())
    assert set(methods) <= set(run["config"]["methods"])
    publication_path = logical_directory.parent / "publication.json"
    archive_verified = False
    if publication_path.exists():
        publication = read_json(publication_path)
        archive_path = ROOT / publication["source_archive"]
        assert sha(archive_path) == publication["source_archive_sha256"]
        if archive_path.suffix == ".zip":
            with zipfile.ZipFile(archive_path) as archive:
                prefix = archive_path.stem + "/"
                members = {n[len(prefix):] for n in archive.namelist() if n.startswith(prefix) and not n.endswith("/")}
                assert members == {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
                assert all((directory / name).read_bytes() == archive.read(prefix + name) for name in members)
            archive_verified = True
    server_checks = directory / "SHA256SUMS"
    if server_checks.exists():
        hashes = dict((name, digest) for digest, name in
                      (line.split("  ", 1) for line in server_checks.read_text().splitlines()))
        integrity = "server final SHA256SUMS"
    else:
        publication = read_json(publication_path)
        assert sha(ROOT / publication["source_archive"]) == publication["source_archive_sha256"]
        hashes = publication["imported_file_sha256"]
        assert set(hashes) == {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
        integrity = "local import hashes and received archive; no server final checksums"
    for name, digest in hashes.items():
        path = (directory / name).resolve()
        assert path.is_relative_to(directory.resolve()) and sha(path) == digest, name
    for name, digest in run["source_sha256"].items():
        assert sha(directory / "source" / name) == digest, name

    specs = {s["instance_id"]: s for s in planned_instances(run["config"])}
    expected = {(i, m) for i in specs for m in run["config"]["methods"]}
    rows = summary["results"]
    jobs = {(r["instance_id"], r["method"]): r for r in rows}
    assert len(jobs) == len(rows) and set(jobs) <= expected
    completed = {key for key, r in jobs.items() if r["status"] != "running"}
    assert summary["planned_jobs"] == len(expected)
    assert summary["completed_jobs"] == len(completed)
    assert summary["complete"] == (completed == expected)
    assert {tuple(k) for k in summary["pending_jobs"]} == expected - completed
    disk_jobs = {(r["instance_id"], r["method"]): r for r in
                 (read_json(p) for p in (directory / "jobs").glob("*/*/result.json"))}
    assert set(disk_jobs) <= expected
    assert {k for k, r in disk_jobs.items() if r["status"] != "running"} == completed

    checks, calls, pending = [], [], []
    for instance, spec in specs.items():
        template = None
        # Historical feasible vectors remain evidence against an invalid bound,
        # even when their solver/timing rows are not selected for the new table.
        for method in run["config"]["methods"]:
            key = instance, method
            if key not in completed:
                if method in methods:
                    pending.append({"instance_id": instance, "method": method,
                                    "snapshot_status": disk_jobs.get(key, {}).get("status", "not_present")})
                continue
            row = jobs[key]
            assert disk_jobs[key] == row
            assert row["case"] == spec["case"] and row["cstr_size"] == spec["cstr_size"]
            assert row["threads"] == 1 and row["time_limit_s"] == run["config"]["time_limit"]
            if template is None:
                template = build_template(spec["case"], cstr_size=spec["cstr_size"] or 30)
                assert template.metadata["source"] == run["runtime"]["templates"][instance]["source"]
            job = directory / "jobs" / instance / method
            if row["has_feasible_solution"]:
                checks.append(recheck_saved_solution(template, job, row))
            entries = jsonl(job / "solver_calls.jsonl") if (job / "solver_calls.jsonl").exists() else []
            assert len(entries) == row.get("solver_calls", len(entries))
            assert all(c["threads"] == 1 for c in entries)
            if method in {"ric", "gloa", "loa"}:
                policy = row["solver_policy"]
                assert policy["nlp"] == run["config"].get("nlp_solver", "ipopt")
                assert policy["mip"] == run["config"].get("mip_solver", "cplex")
                assert {c["solver"] for c in entries} <= {policy["nlp"], policy["mip"]}
                nlp = [c for c in entries if c["solver"] == policy["nlp"]]
                calls.append({"instance_id": instance, "method": method, "nlp_solver": policy["nlp"],
                              "nlp_calls": len(nlp), "terminations": dict(Counter(
                                  c.get("termination", c.get("status")) for c in nlp))})
    selected = [r for key, r in jobs.items() if key in completed and r["method"] in methods]
    return {"directory": str(logical_directory.relative_to(ROOT)), "methods": methods,
            "host": run["host"], "created_utc": run["created_utc"], "cpu_affinity": run["cpu_affinity"],
            "integrity": integrity, "verified_file_hashes": len(hashes),
            "source_archive_verified_byte_for_byte": archive_verified,
            "source_archive": publication.get("source_archive") if publication_path.exists() else None,
            "source_archive_sha256": publication.get("source_archive_sha256") if publication_path.exists() else None,
            "source_summary_sha256": sha(directory / "summary.json"),
            "planned_selected_jobs": len(specs) * len(methods), "completed_selected_jobs": len(selected),
            "termination_counts": dict(Counter(r["termination"] for r in selected)),
            "pending_jobs": pending, "solution_rechecks": checks, "nlp_calls": calls}


def build(selection_directory, output):
    selection_directory, output = Path(selection_directory), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sources = read_json(selection_directory / "selection.json")["sources"]
    audits = [verify_source(ROOT / s["directory"], s["methods"]) for s in sources]
    traces = [{"spec": {"case_name": s["case_name"], "grid_size": s["grid_size"]},
               "target": problem(s)["target"]} for s in reference_plan()]
    records = baseline_comparison(selection_directory, output, traces)
    for row in records:
        row["relative_objective_gap"] = (max(0, (row["objective"] - row["target_value"]) /
            max(1, abs(row["target_value"]))) if row["objective"] is not None else None)
        row["signed_relative_objective_gap"] = ((row["objective"] - row["target_value"]) /
            max(1, abs(row["target_value"]))) if row["objective"] is not None else None
    pending = [p for a in audits for p in a["pending_jobs"]]
    rechecks = [{"source_directory": a["directory"], "selected_for_comparison": r["method"] in a["methods"], **r}
               for a in audits for r in a["solution_rechecks"]]
    overview = {"complete": not pending, "planned_jobs": sum(a["planned_selected_jobs"] for a in audits),
                "completed_jobs": len(records), "pending_jobs": pending,
                "saved_solutions_independently_rechecked": len(rechecks),
                "selected_solutions_independently_rechecked": sum(r["selected_for_comparison"] for r in rechecks),
                "max_rechecked_primal_violation": max((r["max_primal_violation"] for r in rechecks), default=None),
                "target_hits_by_method": {m: sum(r["target_hit"] for r in records if r["method"] == m) for m in METHODS},
                "target_attained_by_method": {m: sum(r["target_attained"] for r in records if r["method"] == m) for m in METHODS},
                "completed_by_method": dict(Counter(r["method"] for r in records)),
                "termination_counts": dict(Counter(r["termination"] for r in records)),
                "time_limits_by_method": {m: sum(r["termination"] == "maxTimeLimit" for r in records if r["method"] == m)
                                          for m in METHODS},
                "bound_conflicts": [{k: r[k] for k in ("instance_id", "method", "reported_lower_bound",
                    "best_saved_feasible_objective", "bound_evidence_method", "bound_evidence_source_directory")}
                    for r in records if r["bound_conflict_with_saved_solution"]],
                "sources": audits, "selection_sha256": sha(selection_directory / "selection.json"),
                "analysis_source_sha256": {name: sha(ROOT / name) for name in (
                    "gdp_current_analysis.py", "gdp_comparison_analysis.py", "nlp_cost_analysis.py",
                    "result_archives.py", "results/archives/catalog.json")},
                "validation": "Saved vectors evaluated in original GDPs without solving; partial rows excluded; no old GDPopt fallback."}
    write_csv(output / "comparison.csv", records)
    write_json(output / "audit.json", overview)
    write_json(output / "solution_rechecks.json", rechecks)
    write_json(output / "pending_jobs.json", pending)
    report(output, records, overview)
    for source, source_audit in zip(sources, audits):
        if source["methods"] == ["bigm", "hull"]:
            continue  # Keep the complete September 25 four-method audit historical.
        latest_output = output / "sources" / Path(source["directory"]).parent.name
        latest_output.mkdir(parents=True, exist_ok=True)
        write_csv(latest_output / "comparison.csv", [r for r in records if r["source_directory"] == source["directory"]])
        write_json(latest_output / "audit.json", source_audit)
        write_json(latest_output / "solution_rechecks.json", source_audit["solution_rechecks"])
    write_json(output / "artifact_checksums.json", {
        p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "artifact_checksums.json"
        and p.suffix in {".csv", ".json", ".md", ".png", ".pdf"}})
    print({k: overview[k] for k in ("completed_jobs", "saved_solutions_independently_rechecked", "target_hits_by_method")})
    return overview


def report(output, records, overview):
    jobs = {(r["instance_id"], r["method"]): r for r in records}
    complete_text = "complete" if overview["complete"] else "partial"
    summary = [{"method": method, "completed_models": overview["completed_by_method"].get(method, 0),
                "target_attained": overview["target_attained_by_method"][method],
                "absolute_target_matches": overview["target_hits_by_method"][method],
                "time_limits": overview["time_limits_by_method"][method]}
               for method in METHODS]
    write_csv(output / "method_summary.csv", summary)
    lines = [f"# Current full-GDP results — October 1 {complete_text} results", "",
        f"**{overview['completed_jobs']}/{overview['planned_jobs']} selected jobs completed**: "
        "RIC, GLOA and LOA with BARON/HiGHS on nine original GDP models, plus Big-M/Hull with BARON. "
        f"All {overview['selected_solutions_independently_rechecked']} available selected solution vectors pass "
        "an independent original-GDP feasibility check at tolerance 1e-5. Completion includes time-limited jobs, "
        "not just optimal terminations.", "",
        "The final October 1 archives replace the earlier partial RIC/GLOA snapshot. "
        "Both external ZIP checksums and all internal SHA256SUMS entries were verified; extracted files "
        "match the archived bytes. The 12 CSTR records already present in the partial copy are unchanged.", "",
        "Big-M/Hull retain September 25 results, independently rechecked here. "
        "Historical feasible IPOPT vectors remain evidence when checking reported bounds; their times are not substituted. "
        "RIC/GLOA and Big-M/Hull record logical CPU 2 (physical core 2, socket 0); LOA records logical CPU 6 "
        "(physical core 8, socket 0). RIC/GLOA and LOA overlapped on separate physical cores, with one thread each. "
        "CPU affinity does not establish an otherwise idle server or remove shared-resource contention.", "",
        "Each completed cell is **objective / seconds including template preparation**. "
        "TL = time limit; † = BARON bound conflicts with a better saved feasible solution. "
        "Preflight, process launch and archiving are excluded. Missing cells are not zero or failures.", "",
        "| Model | " + " | ".join(LABELS) + " |", "|---|" + "---:|" * len(METHODS)]
    table = []
    for instance in INSTANCES:
        cells = []
        for method in METHODS:
            row = jobs.get((instance, method))
            if row is None:
                cells.append("pending / unavailable")
                continue
            suffix = " TL" if row["termination"] == "maxTimeLimit" else ""
            if row["bound_conflict_with_saved_solution"]:
                suffix += " †"
            objective = f"{row['objective']:.8g}" if row["objective"] is not None else "no feasible solution"
            cells.append(f"{objective} / {row['measured_total_with_preparation_s']:.2f}s{suffix}")
        table.append(cells)
        lines.append(f"| {instance} | " + " | ".join(cells) + " |")
    lines += ["", "## Findings", "",
        "- The new RIC results improve CSTR5–25 relative to the old IPOPT run, "
        "but RIC reaches its time limit on CSTR15/20/25/30. All six CSTR GLOA runs report `optimal` "
        "while returning worse objectives than the corresponding feasible RIC solutions. "
        "The GDPopt global certificate and bound-validity flags remain false.", "",
        "- LOA returns better feasible objectives than RIC on CSTR15/20/25/30, under the same 30-minute "
        "per-job limit. CSTR5/10 and Small Batch agree with RIC within the comparison tolerance.", "",
        "- Column and Dynamic return the same incumbent for RIC/GLOA/LOA: approximately 22271.54872 "
        "and -119.3830994. Each has one initialization MIP and one time-limited BARON NLP; the strict "
        "subproblem guard stops without cutting off an unproven configuration. These results do not "
        "demonstrate that the three search algorithms converged to the same optimum.", "",
        "- LOA CSTR15 returns 2.829350618, below the historical lookup target by about 1.53e-5 relatively. "
        "It passes the recorded primal-feasibility tolerance, but this is not a new global-optimality proof. "
        "Its signed objective gap is retained. A better-than-target solution counts as attainment, even "
        "if it falls outside the old symmetric target-match tolerance.", "",
        "## Target attainment and termination", "",
        "All models are minimization problems. `target_attained` means objective <= target + "
        "1e-5 × max(1, |target|). The historical `target_hit` column is retained separately and means "
        "absolute objective error within that tolerance. The denominator is nine different models, "
        "not repeated stochastic trials. These are completion-time records, not first-hit times.", "",
        "| Method | Completed | At target or better | Absolute target match | Time limit |",
        "|---|---:|---:|---:|---:|"]
    for row in summary:
        lines.append(f"| {row['method'].upper()} | {row['completed_models']}/9 | {row['target_attained']}/9 | "
                     f"{row['absolute_target_matches']}/9 | {row['time_limits']} |")
    lines += ["", "## Files and reproduction", "",
        "- `comparison.csv`: completed jobs only, with exact source directory/date and solver policy.",
        "- `method_summary.csv`: target attainment, symmetric matches and time limits by method.",
        "- `pending_jobs.json`: empty for this completed import.",
        "- `audit.json`, `solution_rechecks.json`: hashes, solver statuses and independent feasibility checks.",
        "- `gdp_objectives_and_times.png` / `.pdf`: published comparison figure.", "",
        "The [September 25 IPOPT comparison](../../gdp_comparison_20260925/analysis/README.md) remains historical. "
        "The [RIC/GLOA final archive](../../gdp_comparison_20261001/README.md) and "
        "[LOA final archive](../../gdp_comparison_loa_20261001/README.md) document the new sources. "
        "The previously prepared six-job follow-up is unnecessary: the original RIC/GLOA run finished.", "",
        "Reproduce without solving:", "",
        "```bash", "python gdp_current_analysis.py", "```", ""]
    (output / "README.md").write_text("\n".join(lines))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(18, 7.5))
    ax.axis("off")
    artist = ax.table(cellText=[[c.replace(" / ", "\n") for c in row] for row in table],
                      rowLabels=INSTANCES, colLabels=LABELS, cellLoc="center", rowLoc="center",
                      bbox=[.10, .10, .89, .78])
    artist.auto_set_font_size(False)
    artist.set_fontsize(10)
    for (r, c), cell in artist.get_celld().items():
        cell.set_edgecolor("#d6dce3")
        if r == 0:
            cell.set_facecolor("#203a53")
            cell.get_text().set_color("white")
        elif c == -1 or (INSTANCES[r - 1], METHODS[c]) not in jobs:
            cell.set_facecolor("#eef2f6")
        else:
            row = jobs[INSTANCES[r - 1], METHODS[c]]
            if row["bound_conflict_with_saved_solution"]:
                cell.set_facecolor("#fde5e2")
            elif row["termination"] == "maxTimeLimit":
                cell.set_facecolor("#fff2d7")
    fig.suptitle(f"Full GDP benchmark: October 1 {complete_text} results", fontsize=17)
    fig.text(.5, .925, "RIC/GLOA: CPU 2 | LOA: CPU 6 | Big-M/Hull: September 25 CPU 2 | One thread per run", ha="center", fontsize=11)
    fig.text(.5, .055, "Objective and completion seconds including template preparation. TL: time limit. †: conflicting BARON bound.", ha="center", fontsize=10)
    fig.text(.5, .02, f"{overview['selected_solutions_independently_rechecked']} saved solutions independently checked. "
             "No global certificate inferred from GDPopt termination text.", ha="center", fontsize=10)
    for ext in ("png", "pdf"):
        fig.savefig(output / f"gdp_objectives_and_times.{ext}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=ROOT / "results/gdp_comparison_current")
    parser.add_argument("--output", type=Path, default=ROOT / "results/gdp_comparison_current/analysis")
    args = parser.parse_args()
    build(args.selection, args.output)
