"""Verify and import the single-job Dantzig return without running optimizers."""

# ruff: noqa: E402 -- support direct execution from the repository root
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.import_process_dsda_fairness import extract_verified, verify_reused_costs
from process_dsda_fairness import read, save, sha, valid_job
from process_dsda_fairness_analysis import analyze
from process_dsda_fairness_recovery import (
    PARENT_SHA256, RETRY_JOB, parent_inventory, verify_recovery,
)

RECOVERY_SHA256 = "7201a5d49d216a9c1eea64ecf649ec4c185dd9c1dafcc41c70117edf600e51b3"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def csv_rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def build(archive, output):
    archive, output = Path(archive).resolve(), Path(output).resolve()
    require(sha(archive) == RECOVERY_SHA256, "Unexpected recovery archive SHA256")
    archive_ref = "results/archives/" + archive.name
    with tempfile.TemporaryDirectory(prefix="dsda_recovery_import_") as temp:
        directory, member_count = extract_verified(archive, temp)
        preservation = verify_recovery(directory)
        run = read(directory / "run.json")
        require(not run["development_only"] and not run["smoke_only"], "Not a full server return")
        require(run["runtime"]["host"] == "dantzig.ecn.purdue.edu", "Not measured on Dantzig")
        require(run["runtime"]["affinity"]["effective_cpus"] == [7], "CPU differs")
        require(preservation == {"preserved_jobs": 139, "remeasured_jobs": [RETRY_JOB]},
                "Unexpected recovery selection")
        parent_prefix, inventory, _, preserved_ids = parent_inventory(directory / "parent_result.zip")
        preserved_files = {
            name: digest for name, digest in inventory.items()
            if name.startswith("jobs/") and name.split("/")[1] in preserved_ids
        }
        # Match the supplied v5 source package, not the unrelated server checkout HEAD.
        package = ROOT / "results/runners/process_dsda_fairness_20261014_v5.zip"
        with zipfile.ZipFile(package) as z:
            for name, digest in run["source_files_sha256"].items():
                require(hashlib.sha256(z.read("process_dsda_fairness/" + name)).hexdigest() == digest,
                        "Executed source differs from supplied v5: " + name)
        job = directory / "jobs" / RETRY_JOB
        result = valid_job(job)
        events = read(job / "callbacks.json")
        require(result["status"] == "completed" and len(events) == 22
                and result["target_hit"] is False, "Recovered outcome differs")
        with zipfile.ZipFile(directory / "parent_result.zip") as z:
            trace = next(n for n in inventory if n.startswith("jobs/" + RETRY_JOB + "/lookup.traces/"))
            original = [json.loads(line) for line in z.read(parent_prefix + trace).splitlines()]
        original = [e for e in original if e.get("event") == "evaluation"]
        def signature(rows):
            return [(e["point"], e["value"], e["value_kind"]) for e in rows]

        require(signature(events) == signature(original), "Original 22-callback path differs")

        analysis = Path(temp) / "analysis"
        summary = analyze(directory, analysis)
        require(summary["completed_runs"] == 140 and summary["callbacks"] == 2611
                and not summary["errors"] and summary["dantzig_matrix_complete"]
                and summary["timing_reconstruction_complete"]
                and summary["missing_callback_costs"] == 0 and summary["new_nlp_solves"] == 0,
                "Incomplete recovered matrix")
        selection = read(analysis / "candidate_selection.json")
        ref = read(directory / "source/benchmark_protocols/process_dsda_fairness_reference.json")
        others = [r for r in selection if r["method"] != "dsda"]
        require(len(others) == 420 and others == [r for r in ref["selected_runs"] if r["method"] != "dsda"],
                "Non-DSDA records changed")
        other_sha = hashlib.sha256(json.dumps(others, sort_keys=True).encode()).hexdigest()
        require(other_sha == ref["non_dsda_sha256"], "Non-DSDA checksum differs")

        # Independently generated values must equal the returned server tables.
        server_selection = read(directory / "analysis/candidate_selection.json")
        remote_root = next(r["source"] for r in server_selection if r["method"] == "dsda").split("/jobs/")[0]
        portable_root = archive_ref + "!/" + directory.name

        def portable(text):
            return text.replace(str(directory), portable_root).replace(remote_root, portable_root)

        compared = []
        for path in sorted(analysis.iterdir()):
            if path.suffix == ".csv" or path.name == "candidate_selection.json":
                require(portable(path.read_text()) == portable((directory / "analysis" / path.name).read_text()),
                        "Independent analysis differs: " + path.name)
                path.write_text(portable(path.read_text()))
                compared.append(path.name)
        reused = verify_reused_costs(csv_rows(analysis / "callbacks_and_costs.csv"))
        require(len(reused) == 4, "Unexpected reused-cost inventory")
        prior_rows = csv_rows(ROOT / "results/process_dsda_fairness_20261014/analysis/runs.csv")
        current_rows = {r["job_id"]: r for r in csv_rows(analysis / "runs.csv")}
        require(len(prior_rows) == 139, "Unexpected prior imported row count")
        for prior in prior_rows:
            current = current_rows[prior["job_id"]]
            require({k: v for k, v in prior.items() if k != "source"}
                    == {k: v for k, v in current.items() if k != "source"},
                    "Preserved derived values changed: " + prior["job_id"])
        cstr15 = [r for r in selection if r["case"] == "cstr"
                  and r["cstr_size"] == "15" and r["method"] == "dsda"]
        require(len(cstr15) == 10 and {r["seed"] for r in cstr15} == set(range(10)),
                "CSTR15 does not contain all ten seeds")
        hits = sum(r["lookup_target_hit"] for r in cstr15)
        require(hits == 2, "CSTR15 target outcomes changed")
        median = statistics.median(r["estimated_total_s"] for r in cstr15)
        repeats = math.ceil(math.log(0.01) / math.log1p(-hits / 10))
        group = next(r for r in csv_rows(analysis / "dsda_summary.csv")
                     if r["case"] == "cstr" and r["cstr_size"] == "15")
        require(float(group["median_completion_s"]) == median
                and float(group["tts99_s"]) == repeats * median, "CSTR15 summary differs")
        retry_row = next(r for r in cstr15 if r["job_id"] == RETRY_JOB)
        metrics = {
            "job_id": RETRY_JOB, "callbacks": 22, "original_callback_signature_matches": True,
            "target_hit": False, "method_wall_s": result["result_record"]["wall_time_s"],
            "lookup_callback_wall_s": retry_row["recorded_lookup_s"],
            "search_overhead_s": retry_row["search_overhead_s"],
            "measured_point_cost_sum_s": retry_row["known_point_cost_sum_s"],
            "estimated_completion_s": retry_row["estimated_total_s"],
            "cstr15_runs": 10, "cstr15_target_hits": hits, "cstr15_hit_rate": hits / 10,
            "cstr15_median_completion_s": median, "cstr15_runs_99": repeats,
            "cstr15_tts99_s": repeats * median,
            "timing_definition": summary["timing_definition"],
        }
        audit = {
            "archive": archive_ref, "archive_sha256": sha(archive),
            "parent_archive_sha256": PARENT_SHA256, "verified_archive_members": member_count,
            "verified_source_files": len(run["source_files_sha256"]),
            "recovery_package": str(package.relative_to(ROOT)), "recovery_package_sha256": sha(package),
            "executed_sources_match_v5_package": True,
            "preservation": {**preservation, "byte_identical_files": len(preserved_files),
                             "unchanged_derived_dsda_rows": len(prior_rows),
                             "non_dsda_rows": len(others), "non_dsda_sha256": other_sha},
            "independently_matched_server_tables": compared,
            "total_target_hits": sum(r["lookup_target_hit"] for r in selection if r["method"] == "dsda"),
            "summary": summary, "recovered_job_and_cstr15": metrics,
            "local_optimizer_runs": 0, "local_timings_used": False, "script_sha256": sha(__file__),
            "source_policy": run["recovery"]["source_policy"],
        }
        output.mkdir(parents=True, exist_ok=True)
        shutil.copytree(analysis, output / "analysis", dirs_exist_ok=True)
        for name, data in (("audit.json", audit), ("runtime.json", run["runtime"]),
                           ("recovered_job_and_cstr15.json", metrics),
                           ("reused_infeasible_costs.json", reused),
                           ("preserved_job_files_sha256.json", preserved_files)):
            save(output / name, data)
        save(output / "recovered_callback_signature.json", [
            {"evaluation_index": i, "point": e["point"], "value": e["value"], "value_kind": e["value_kind"]}
            for i, e in enumerate(events, 1)
        ])
    target = ROOT / archive_ref
    require(not target.exists() or sha(target) == RECOVERY_SHA256, "Archive destination differs")
    if archive != target:
        shutil.copyfile(archive, target)
    target.with_suffix(".zip.sha256").write_text(RECOVERY_SHA256 + "  " + target.name + "\n")
    print(json.dumps({"preservation": audit["preservation"], "metrics": metrics}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results/process_dsda_recovery_20261014")
    args = parser.parse_args()
    build(args.archive, args.output)
