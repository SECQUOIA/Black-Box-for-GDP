"""Audit Dantzig callback traces and publish separate, all-outcome NLP costs.

This reads completed archives only. No optimizer or solver is executed.
"""

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import stat
import statistics
import tempfile
import zipfile

from evaluation_trace import validate_events
from nlp_cost_analysis import METHOD_NAMES, target_hit
from overnight_benchmark.analysis import lookup_runs, point_costs, requested_points, timing_tables
from overnight_benchmark.common import ROOT, csv_file, jsonl, point_key, point_spec, read, save, sha
from overnight_benchmark.references import archived_fmqa, historical_costs
from overnight_benchmark.runner import plans, terminal_valid


ARCHIVE = ROOT / "results/archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip"
ARCHIVE_SHA = "c1c8939a96ed9fe945074e71c7aa7043f251e6e26024866e6f45a00ed8914be8"
OUTPUT = ROOT / "results/dfo_trace_nlp_20261002/analysis"
OUTCOMES = ("accepted", "preprocessing_infeasible", "solver_reported_infeasible", "other_rejected")


@contextmanager
def verified_snapshot(path, expected_sha):
    """Extract only after checking every archived byte and safe member names."""
    if sha(path) != expected_sha:
        raise ValueError("DFO archive checksum mismatch")
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="dfo-audit-") as tmp:
        members = archive.infolist()
        if len({m.filename for m in members}) != len(members):
            raise ValueError("Duplicate archive member")
        roots = set()
        for member in members:
            name = PurePosixPath(member.filename)
            if name.is_absolute() or ".." in name.parts or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Unsafe archive member")
            roots.add(name.parts[0])
        if len(roots) != 1:
            raise ValueError("Expected one archive root")
        prefix = roots.pop() + "/"
        inventory = {}
        for line in archive.read(prefix + "SHA256SUMS").decode().splitlines():
            digest, relative = line.split("  ", 1)
            if relative in inventory:
                raise ValueError("Duplicate checksum entry")
            inventory[relative] = digest
        actual = {m.filename[len(prefix):] for m in members if not m.is_dir()}
        if actual != set(inventory) | {"SHA256SUMS"}:
            raise ValueError("Incomplete archive checksum inventory")
        for relative, digest in inventory.items():
            data = archive.read(prefix + relative)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"Internal checksum mismatch: {relative}")
            destination = Path(tmp) / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        yield Path(tmp), {"archive": str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else str(path),
                         "sha256": expected_sha, "root": prefix[:-1], "verified_files": len(inventory)}


def outcome(record):
    if record["accepted"]:
        return "accepted"
    if record["status"] == "preprocessing_infeasible":
        return "preprocessing_infeasible"
    if record["termination"] == "infeasible":
        return "solver_reported_infeasible"
    return "other_rejected"


def compare_shipped_csv(path, rows):
    stream = io.StringIO()
    fields = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    rebuilt = list(csv.DictReader(io.StringIO(stream.getvalue())))
    with path.open(newline="") as handle:
        if rebuilt != list(csv.DictReader(handle)):
            raise ValueError(f"Shipped table differs from raw evidence: {path.name}")


def audit(directory):
    from fmqa_benchmark.protocol import problem
    run = read(directory / "run.json")
    if (run["development_only"] or run["runtime"]["host"] != "dantzig.ecn.purdue.edu"
            or run["lookup_plan"] != plans()):
        raise ValueError("Not the frozen original Dantzig experiment")
    for name, digest in run["source_files_sha256"].items():
        if sha(directory / "source" / name) != digest:
            raise ValueError(f"Archived source changed: {name}")
        # Require unchanged original algorithms, lookup data and model adapters.
        if name.startswith(("case_studies/", "case_study_data/")) or name in {
                "case_study_benchmark.py", "grid_dsda.py", "grid_rbfopt.py", "instrumentation.py",
                "evaluation_trace.py", "gdp_models/models.py", "fmqa_benchmark/protocol.py"}:
            if sha(ROOT / name) != digest:
                raise ValueError(f"Original benchmark input changed: {name}")
    point_plan = read(directory / "point_plan.json")
    collection = []
    for mode, plan in (("lookup", run["lookup_plan"]), ("points", point_plan)):
        if {p.name for p in (directory / mode).iterdir()} != {s["job_id"] for s in plan}:
            raise ValueError(f"Job set differs from plan: {mode}")
        for spec in plan:
            job = directory / mode / spec["job_id"]
            result = read(job / "result.json")
            if not terminal_valid(job) or result["spec"] != spec or result["status"] != "completed":
                raise ValueError(f"Incomplete or mismatched job: {spec['job_id']}")
            terminal_files = read(job / "terminal.json")["files_sha256"]
            if set(terminal_files) != {p.relative_to(job).as_posix() for p in job.rglob("*")
                                      if p.is_file() and p.name != "terminal.json"}:
                raise ValueError("Job inventory does not cover every artifact")
            if mode == "lookup":
                entries = jsonl(job / result["trace"]["path"])
                if (entries[0]["run_key"] != spec or entries[-1]["event"] != "run_complete"
                        or entries[-1]["result_record"] != result["result_record"]):
                    raise ValueError("Trace/result identity mismatch")
                events = [e for e in entries if e["event"] == "evaluation"]
                validate_events(events, result["result_record"])
                previous = 0.0
                oracle = problem(spec)["objective"]
                for event in events:
                    start, end = event["started_elapsed_s"], event["completed_elapsed_s"]
                    # The objective timer is nested inside the trace timer.
                    if start < previous or end < start or not 0 <= event["objective_wall_s"] <= end - start + 1e-9:
                        raise ValueError("Invalid callback clock")
                    value = oracle(event["point"])
                    if not math.isfinite(value):
                        # Original Column/Dynamic DSDA/RBFOpt use a finite
                        # penalty; BAM uses NaN. Neither denotes feasibility.
                        penalty = 1e6 if spec["case_name"] in {"column", "dynamic"} and spec["method"] != "bam" else None
                        if event["value"] != penalty:
                            raise ValueError("Original infeasible-point handling changed")
                    previous = end
                if not 0 < result["result_record"]["wall_time_s"] <= result["wall_time_s"] or previous > result["wall_time_s"]:
                    raise ValueError("Invalid DFO completion clock")
            else:
                record = result["record"]
                if point_key(record["case"], record["cstr_size"], record["point"]) != point_key(
                        spec["case_name"], spec["grid_size"], spec["point"]):
                    raise ValueError("Point measurement identity mismatch")
                if (record["solver"] != run["config"]["solver"] or record["initialization_requested"] != "auto"
                        or record["time_limit_s"] != run["config"]["nlp_seconds"]):
                    raise ValueError("Point solver policy mismatch")
                if record["solve_wall_s"] > 0 and not (job / "solver/gams_files.zip").exists():
                    raise ValueError("Missing new GAMS solver artifacts")
                collection.append({"job_id": spec["job_id"], "case": spec["case_name"],
                    "cstr_size": spec["grid_size"], "point": spec["point"],
                    "outcome": outcome(record), "point_evaluation_s": record["total_wall_s"],
                    "solver_invocation_s": record["solve_wall_s"],
                    "premeasurement_setup_s": result["premeasurement_setup_wall_s"],
                    "worker_wall_s": result["worker_wall_s"],
                    "source": f"points/{spec['job_id']}/result.json"})
    _, fmqa = archived_fmqa()
    historical, reuse = historical_costs(run["config"], run["runtime"])
    traces = lookup_runs(directory, run["lookup_plan"], fmqa)
    keys = requested_points(traces)
    if read(directory / "requested_points.json") != [point_spec(k) for k in keys]:
        raise ValueError("Requested point set differs from actual callbacks")
    if point_plan != [point_spec(k) for k in keys if k not in historical]:
        raise ValueError("Point plan is not exactly the missing visited coordinates")
    costs = {k: v for k, v in point_costs(directory, historical).items() if k in keys}
    if set(costs) != set(keys):
        raise ValueError("Missing visited-coordinate measurement")
    for item in costs.values():
        record = item["record"]
        if not math.isfinite(item["cost_s"]) or not 0 <= record["solve_wall_s"] <= item["cost_s"] or item["cost_s"] <= 0:
            raise ValueError("Invalid evaluation/solver time")
    rows, ledger = timing_tables(traces, costs)
    compare_shipped_csv(directory / "analysis/dfo_runs.csv", rows)
    compare_shipped_csv(directory / "analysis/evaluation_timings.csv", ledger)
    shipped = read(directory / "analysis/audit.json")
    expected = {"new_dfo_runs_planned": len(run["lookup_plan"]), "original_fmqa_traces_reused": len(fmqa),
                "dfo_jobs_finished": len(run["lookup_plan"]), "visited_coordinates": len(keys),
                "coordinates_with_nlp_measurement": len(costs), "missing_coordinate_measurements": 0,
                "reused_coordinate_measurements": sum(k in historical for k in keys), "point_reuse_audit": reuse}
    if shipped != expected or read(directory / "historical_reuse.json") != reuse:
        raise ValueError("Shipped coverage audit differs from raw evidence")
    return run, traces, costs, rows, ledger, collection, expected


def attach_costs(traces, costs, rows, ledger):
    """One separately measured original attempt per callback, irrespective of outcome."""
    from fmqa_benchmark.protocol import problem
    oracles = {t["spec"]["job_id"]: problem(t["spec"])["objective"] for t in traces}
    by_job = defaultdict(list)
    for event in ledger:
        key = point_key(event["case"], event["cstr_size"], event["point"])
        item = costs[key]
        event["nlp_outcome"] = outcome(item["record"])
        event["nlp_measurement_source_sha256"] = item["source_sha256"]
        raw = oracles[event["job_id"]](event["point"])
        event["lookup_feasible"] = math.isfinite(raw)
        event["lookup_objective"] = raw if math.isfinite(raw) else None
        event["lookup_nlp_acceptance_disagrees"] = event["lookup_feasible"] != event["nlp_accepted"]
        event["accepted_objective_matches_lookup"] = (target_hit(event["nlp_objective"], event["lookup_objective"])
            if event["lookup_feasible"] and event["nlp_accepted"] else None)
        by_job[event["job_id"]].append(event)
    trace_map = {t["spec"]["job_id"]: t for t in traces}
    for row in rows:
        events = by_job[row["job_id"]]
        row["method_label"] = METHOD_NAMES[row["method"]]
        row["target_value"] = trace_map[row["job_id"]]["target"]
        row["lookup_target_hit"] = target_hit(row["recorded_best_value"], row["target_value"])
        row["repeated_callbacks"] = sum(e["repeated_coordinate"] for e in events)
        row["nlp_cost_kind"] = "separately_measured_fixed_path_estimate_each_callback"
        row["attached_nlp_evaluation_s"] = math.fsum(e["nlp_evaluation_wall_s"] for e in events)
        row["attached_nlp_solver_s"] = math.fsum(e["nlp_solve_wall_s"] for e in events)
        for label in OUTCOMES:
            group = [e for e in events if e["nlp_outcome"] == label]
            row[f"{label}_callbacks"] = len(group)
            row[f"attached_{label}_s"] = math.fsum(e["nlp_evaluation_wall_s"] for e in group)
        row["attached_unaccepted_s"] = math.fsum(row[f"attached_{k}_s"] for k in OUTCOMES[1:])
        row["lookup_nlp_acceptance_disagreements"] = sum(e["lookup_nlp_acceptance_disagrees"] for e in events)
    return rows, ledger


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["case"], row["cstr_size"], row["budget"], row["method"]].append(row)
    summary = []
    for (case, size, budget, method), group in sorted(groups.items(), key=lambda x: repr(x[0])):
        result = {"case": case, "cstr_size": size, "budget": budget, "method": method,
                  "method_label": METHOD_NAMES[method], "runs": len(group),
                  "target_hits": sum(r["lookup_target_hit"] for r in group),
                  "callbacks": sum(r["completed_evaluations"] for r in group),
                  "missing_nlp_measurements": sum(r["callbacks_missing_nlp_measurement"] for r in group)}
        for field in ("dfo_wall_time_s", "attached_nlp_evaluation_s", "attached_nlp_solver_s",
                      "attached_unaccepted_s", *(f"attached_{k}_s" for k in OUTCOMES)):
            result["mean_" + field] = statistics.mean(r[field] for r in group)
        summary.append(result)
    return summary


def figures(output, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = ("#527d9b", "#e1ad50", "#c95b4b", "#8c73ad")
    for name, selected in (("runtime_and_nlp_costs", [("column", None, 16), ("cstr", 30, 43),
                            ("small_batch", None, 10), ("dynamic", None, 50)]),
                           ("cstr_sizes", [("cstr", size, None) for size in (5, 10, 15, 20, 25, 30)])):
        fig, axes = plt.subplots(len(selected), 2, figsize=(12, 2.8 * len(selected)), squeeze=False)
        for pair, (case, size, budget) in zip(axes, selected):
            group = [s for s in summary if s["case"] == case and s["cstr_size"] == size
                     and (budget is None or s["budget"] == budget)]
            group = [next(s for s in group if s["method"] == method) for method in METHOD_NAMES]
            x = range(4)
            labels = [s["method_label"] for s in group]
            title = f"CSTR {size}" if case == "cstr" else case.replace("_", " ").title()
            title += f", B={group[0]['budget']}"
            left, right = pair
            times = [s["mean_dfo_wall_time_s"] for s in group]
            left.bar(x, times, color="#527d9b")
            left.set_yscale("log")
            left.set_ylim(min(times) / 3, max(times) * 4)
            for i, value in enumerate(times):
                left.annotate(f"{value:.4g}", (i, value), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=9)
            base = [0.] * 4
            for label, color in zip(OUTCOMES, colors):
                values = [s[f"mean_attached_{label}_s"] for s in group]
                right.bar(x, values, bottom=base, color=color, label=label.replace("_", " "))
                base = [a + b for a, b in zip(base, values)]
            right.set_ylim(0, max(base) * 1.2)
            for i, value in enumerate(base):
                right.annotate(f"{value:.2f}", (i, value), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=9)
            for ax in pair:
                ax.set(xticks=x, xticklabels=labels, title=title)
                ax.grid(axis="y", alpha=.15)
                ax.set_axisbelow(True)
            left.set_ylabel("Mean DFO runtime (s, log scale)", fontsize=10)
            right.set_ylabel("Mean attached NLP cost (s)", fontsize=10)
        fig.suptitle("Dantzig: measured DFO time and separately measured NLP costs", fontsize=15, y=.995)
        handles, labels = axes[0, 1].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .968), ncol=4, fontsize=9)
        fig.text(.5, .008, "All runs included. Right: per-callback cost estimates, including unaccepted outcomes; no online NLP timing claim.\n"
                 "DSDA/RBFOpt/BAM: Oct 2; FMQA: Sep 25. Dynamic preparation and measurement setup reported separately.",
                 ha="center", fontsize=9)
        fig.tight_layout(rect=(0, .043, 1, .94))
        for extension in ("png", "pdf"):
            fig.savefig(output / f"{name}.{extension}", dpi=180, metadata={"CreationDate": None} if extension == "pdf" else None)
        plt.close(fig)


def report(output, manifest, summary, outcome_rows):
    lines = ["# Dantzig DFO traces and all-outcome NLP costs — October 2, 2026", "",
        "The original DSDA, RBFOpt and BAM lookup searches completed 139 runs each on Dantzig (417 new runs). "
        "The 139 original September 25 Dantzig FMQA traces are reused. The search objectives, seeds, starts and budgets are unchanged; "
        "separately measured NLP results were never fed back to a search.", "",
        f"**Verified: {manifest['runs']} runs, {manifest['callbacks']:,} ordered callbacks, {manifest['visited_coordinates']:,} distinct model/size/coordinate keys, "
        "and zero missing point measurements.** All archive entries, source snapshots, job inventories, trace identities, "
        "initial designs, objective values, event clocks and recorded result histories passed the audit. "
        "The shipped run and callback CSVs were independently rebuilt and matched exactly.", "",
        "## Read these results", "",
        "- [Run results](dfo_runs.csv): actual DFO clocks, final solutions, target attainment and separate attached NLP cost sums.",
        "- [Ordered callback ledger](evaluation_timings.csv): every visited coordinate, DFO timestamps, point duration, outcome and source checksum.",
        "- [Unique point measurements](point_timings.csv): one original attempt per exact model/size/coordinate.",
        "- [Comparison by model and budget](comparison_summary.csv) and [outcome totals](point_outcome_summary.csv).",
        "- [Main comparison figure](runtime_and_nlp_costs.png) ([PDF](runtime_and_nlp_costs.pdf)); [all six CSTR sizes](cstr_sizes.png) ([PDF](cstr_sizes.pdf)).",
        "- [Audit and provenance](manifest.json), [Dynamic preparations](dynamic_preparations.json), "
        "and [new measurement collection overhead](measurement_collection.csv).", "",
        "## What the NLP clock includes", "",
        "The point timer (`nlp_evaluation_wall_s`) includes point-specific model setup, preprocessing, the solver invocation when required, "
        "and validation. `nlp_solve_wall_s` is already inside that duration and is never added twice. "
        "Preprocessing can reject an integer configuration before an NLP solver is called: its solver time is zero, "
        "but its actual evaluation time is positive and is included. Solver-reported infeasibility is an IPOPT outcome, not a global infeasibility proof.", "",
        "There are 1,076 compatible historical original measurements from September 22 and 703 new October 2 measurements. "
        "All 703 new points were rejected during preprocessing; none required a new solver invocation. "
        "The historical measurements include 592 solver-reported infeasible points and three other rejected attempts. "
        "Those three returned feasible candidates but solver warning/termination status failed the original acceptance policy; "
        "they are not relabelled infeasible. Successful retries with changed initialization do not replace the original attempt.", "",
        "| Point outcome | Unique coordinates | Total measured evaluation seconds | Minimum seconds | Maximum seconds |",
        "|---|---:|---:|---:|---:|"]
    for row in outcome_rows:
        lines.append(f"| {row['outcome'].replace('_', ' ')} | {row['coordinates']} | {row['total_evaluation_s']:.6f} | {row['min_evaluation_s']:.6f} | {row['max_evaluation_s']:.6f} |")
    lines += ["", "These totals count each distinct measured coordinate once. Run-level attached sums count every actual callback, "
        "including repeats, against its separate point measurement. They are fixed-path cost estimates, not 12,778 independent NLP solves. "
        "The 384 repeated callbacks remain visible. Missing times are never zero-filled.", "",
        "DFO runtime and attached NLP costs are reported in separate columns and panels. No measured combined runtime or estimated first-hit clock is asserted. "
        "October 2 DFO reruns are not substituted into the original September 10/16 records. "
        "The FMQA and reused NLP measurements come from the dates shown above; this is not a simultaneous four-method experiment.", "",
        "`dfo_wall_time_s` retains each original method's timer; `trace_runner_wall_s` preserves the outer traced runner clock. "
        "Tracing overhead inside the method's timer remains in its measured runtime. Neither clock includes the separately collected point NLP costs. "
        "The October 2 jobs recorded affinity to CPU 6 (sibling 54), with one-thread settings; affinity does not reserve an otherwise idle server.", "",
        "Dynamic template/discretization preparation is recorded separately because it is shared across point evaluations. "
        "The historical Dynamic preparation is 0.109006311 seconds. New worker preparation samples are retained individually; "
        "they are not charged at every callback. Premeasurement warmup/model checks and worker/process overhead are also kept in "
        "`measurement_collection.csv`, outside the point timer. They are collection costs, not hidden additions to DFO runtime.", "",
        "NLP acceptance/objective differences from the frozen lookup are flagged in the callback ledger. These observations do not "
        "change the recorded DFO solution or its target attainment. The full GDPopt RIC/GLOA/LOA and Big-M/Hull results remain "
        "[separate](../../gdp_comparison_current/analysis/README.md); no direct online speed comparison is inferred.", "",
        f"The audit found {manifest['lookup_nlp_acceptance_disagreement_coordinates']} distinct CSTR coordinates "
        f"({manifest['lookup_nlp_acceptance_disagreements']:,} callbacks) where the lookup is feasible but the original IPOPT attempt "
        "was not accepted. Among accepted attempts, "
        f"{manifest['accepted_objective_mismatch_coordinates']} CSTR coordinates ({manifest['accepted_objective_mismatches']} callbacks) "
        "differ from the lookup objective beyond the benchmark tolerance `1e-5 * max(1, abs(lookup))`. "
        "The cost coverage audit therefore does not certify reproduction of every lookup objective by IPOPT. "
        "These measured attempts remain in the timing totals, with their actual outcomes.", "",
        "## Comparison", "",
        "All runs, including target failures, enter the means. Seconds are rounded here; CSVs retain full precision. "
        "Unaccepted NLP cost includes preprocessing rejection, solver-reported infeasibility and other rejected attempts.", "",
        "| Model | Budget | Method | Target hits / runs | Mean DFO s | Mean attached NLP s | Of which unaccepted s |",
        "|---|---:|---|---:|---:|---:|---:|"]
    for row in summary:
        label = f"CSTR {row['cstr_size']}" if row["case"] == "cstr" else row["case"].replace("_", " ").title()
        lines.append(f"| {label} | {row['budget']} | {row['method_label']} | {row['target_hits']} / {row['runs']} | "
                     f"{row['mean_dfo_wall_time_s']:.6f} | {row['mean_attached_nlp_evaluation_s']:.6f} | {row['mean_attached_unaccepted_s']:.6f} |")
    lines += ["", "## Provenance and reproduction", "",
        "The original [result ZIP](../../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip) is retained byte-for-byte "
        "with its [SHA256 sidecar](../../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip.sha256). "
        "Paths in the ledger are archive member paths; `source_kind` identifies historical versus new measurements. "
        "The manifest identifies the two historical evidence archives. Immutable archived instructions/source snapshots are preserved "
        "in their original language for checksum integrity; all current reports, figures and instructions are in English.", "",
        "```bash", "python dfo_trace_analysis.py --output results/dfo_trace_nlp_20261002/analysis", "```", "",
        "This command only reads saved evidence and rebuilds the English reports. It executes no DFO, GDP or NLP solver."]
    (output / "README.md").write_text("\n".join(lines) + "\n")


def build(archive=ARCHIVE, output=OUTPUT, expected_sha=ARCHIVE_SHA):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with verified_snapshot(Path(archive), expected_sha) as (directory, source):
        run, traces, costs, rows, ledger, collection, coverage = audit(directory)
        rows, ledger = attach_costs(traces, costs, rows, ledger)
        summary = summarize(rows)
        point_rows = []
        for key, item in sorted(costs.items(), key=lambda x: repr(x[0])):
            record = item["record"]
            point_rows.append({"case": key[0], "cstr_size": key[1], "point": list(key[2]),
                "outcome": outcome(record), "nlp_evaluation_wall_s": item["cost_s"],
                "nlp_solve_wall_s": record["solve_wall_s"],
                **{k: record.get(k) for k in ("status", "termination", "accepted", "objective", "candidate_objective",
                    "max_primal_violation", "gams_model_status", "gams_solve_status", "message")},
                **{k: item[k] for k in ("source", "source_kind", "source_sha256")}})
        outcome_rows = []
        for label in OUTCOMES:
            values = [r["nlp_evaluation_wall_s"] for r in point_rows if r["outcome"] == label]
            if values:
                outcome_rows.append({"outcome": label, "coordinates": len(values),
                    "callbacks": sum(e["nlp_outcome"] == label for e in ledger),
                    "total_evaluation_s": math.fsum(values), "min_evaluation_s": min(values), "max_evaluation_s": max(values)})
        preparations = read(directory / "analysis/dynamic_preparations.json")
        manifest = {"analysis_kind": "dantzig_dfo_and_separate_all_outcome_point_costs", **coverage,
            "runs": len(rows), "runs_per_method": dict(Counter(r["method"] for r in rows)),
            "callbacks": len(ledger), "repeated_callbacks": sum(e["repeated_coordinate"] for e in ledger),
            "new_point_measurements": len(collection), "new_point_solver_invocations": sum(r["solver_invocation_s"] > 0 for r in collection),
            "new_measurement_setup_total_s": math.fsum(r["premeasurement_setup_s"] for r in collection),
            "lookup_nlp_acceptance_disagreements": sum(e["lookup_nlp_acceptance_disagrees"] for e in ledger),
            "accepted_objective_mismatches": sum(e["accepted_objective_matches_lookup"] is False for e in ledger),
            "lookup_nlp_acceptance_disagreement_coordinates": len({point_key(e["case"], e["cstr_size"], e["point"])
                for e in ledger if e["lookup_nlp_acceptance_disagrees"]}),
            "accepted_objective_mismatch_coordinates": len({point_key(e["case"], e["cstr_size"], e["point"])
                for e in ledger if e["accepted_objective_matches_lookup"] is False}),
            "point_outcomes": outcome_rows, "source": source, "runtime": run["runtime"],
            "reference_archives": read(ROOT / "overnight_benchmark/reference_archives.json"),
            "cost_policy": "Every actual callback linked to one compatible original point attempt, including all unaccepted outcomes; repeated calls reuse the same measurement.",
            "combined_online_runtime_measured": False, "mac_trace_runs_used": 0,
            "analysis_source_sha256": {name: sha(ROOT / name) for name in ("dfo_trace_analysis.py",
                "overnight_benchmark/analysis.py", "overnight_benchmark/common.py", "overnight_benchmark/references.py",
                "overnight_benchmark/runner.py", "evaluation_trace.py", "fmqa_benchmark/protocol.py", "nlp_cost_analysis.py")}}
    for name, data in (("dfo_runs.csv", rows), ("evaluation_timings.csv", ledger), ("point_timings.csv", point_rows),
                       ("comparison_summary.csv", summary), ("point_outcome_summary.csv", outcome_rows),
                       ("measurement_collection.csv", collection)):
        csv_file(output / name, data)
    save(output / "dynamic_preparations.json", preparations)
    save(output / "manifest.json", manifest)
    figures(output, summary)
    report(output, manifest, summary, outcome_rows)
    save(output / "artifact_checksums.json", {p.name: sha(p) for p in sorted(output.iterdir())
                                              if p.is_file() and p.name != "artifact_checksums.json"})
    print(json.dumps({k: manifest[k] for k in ("runs", "callbacks", "visited_coordinates", "missing_coordinate_measurements",
        "new_point_measurements", "new_point_solver_invocations", "lookup_nlp_acceptance_disagreements", "accepted_objective_mismatches")}, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--sha256", default=ARCHIVE_SHA)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.archive, args.output, args.sha256)


if __name__ == "__main__":
    main()
