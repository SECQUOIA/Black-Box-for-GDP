"""Verify and archive the returned Dantzig DSDA matrix; never launch a solver."""

# ruff: noqa: E402 -- support direct execution from the repository root
import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from process_dsda_fairness import read, save, sha, diagnostic, valid_job
from process_dsda_fairness_analysis import analyze, write_csv
from process_dsda_fairness_recovery import PARENT_SHA256, RETRY_JOB


def extract_verified(archive, destination):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any(
            PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names
        ):
            raise ValueError("Invalid ZIP paths")
        manifests = [n for n in names if n.count("/") == 1 and n.endswith("/SHA256SUMS")]
        if len(manifests) != 1 or z.testzip() is not None:
            raise ValueError("Invalid archive or checksum inventory")
        prefix = manifests[0].removesuffix("SHA256SUMS")
        inventory = {rel: digest for digest, rel in
                     (line.split(None, 1) for line in z.read(manifests[0]).decode().splitlines())}
        if set(names) != {prefix + n for n in inventory} | {manifests[0]}:
            raise ValueError("Archive inventory differs")
        for name, digest in inventory.items():
            if hashlib.sha256(z.read(prefix + name)).hexdigest() != digest:
                raise ValueError("Archive member hash differs: " + name)
        z.extractall(destination)
    return Path(destination) / prefix.rstrip("/"), len(inventory)


def verify_reused_costs(ledger):
    archives = [ROOT / "results/archives" / n for n in (
        "dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip",
        "fmqa_qhd_points_20261012_234651_f39la8cf.zip",
    )]
    evidence = []
    for row in ledger:
        if row["point_cost_policy"] != "same_coordinate_logical_rejection_reuse":
            continue
        found = []
        for path in archives:
            with zipfile.ZipFile(path) as z:
                member = row["point_source"]
                if member not in z.namelist():
                    member = path.stem + "/" + member
                if member not in z.namelist():
                    continue
                raw = z.read(member)
                if hashlib.sha256(raw).hexdigest() != row["point_source_sha256"]:
                    raise ValueError("Reused point source hash differs")
                result = json.loads(raw)["record"]
                if (result["case"] != "cstr" or result["point"] != json.loads(row["point"])
                        or str(result["cstr_size"]) != row["point_cost_cstr_size"]
                        or result["total_wall_s"] != float(row["point_evaluation_s"])
                        or result["status"] != "preprocessing_infeasible"
                        or result["solve_wall_s"] != 0):
                    raise ValueError("Reused rejection does not match original measurement")
                found.append({"archive": str(path.relative_to(ROOT)), "archive_sha256": sha(path),
                              "member": member, "member_sha256": hashlib.sha256(raw).hexdigest(),
                              "record": result})
        if len(found) != 1:
            raise ValueError("Reused cost lacks a unique original measurement")
        evidence.append({"job_id": row["job_id"], "evaluation_index": int(row["evaluation_index"]),
                         "requested_cstr_size": int(row["cstr_size"]), "point": json.loads(row["point"]),
                         "measured_cstr_size": int(row["point_cost_cstr_size"]), **found[0]})
    return evidence


def build(archive, output):
    archive, output = Path(archive).resolve(), Path(output).resolve()
    if sha(archive) != PARENT_SHA256:
        raise ValueError("This importer expects the original verified pudvsttz return")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dsda_return_import_") as temp:
        directory, count = extract_verified(archive, temp)
        run = read(directory / "run.json")
        if (run["development_only"] or run["runtime"]["host"] != "dantzig.ecn.purdue.edu"
                or run["runtime"]["affinity"]["effective_cpus"] != [7]):
            raise ValueError("Unexpected measurement runtime")
        summary = analyze(directory, output / "analysis")
        # Separate deterministic checks; no replay wall time enters the data.
        replayed = 0
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            for spec in run["plan"]:
                job = directory / "jobs" / spec["job_id"]
                if valid_job(job)["status"] == "completed":
                    diagnostic(spec, read(job / "callbacks.json"))
                    replayed += 1
        archive_ref = "results/archives/" + archive.name
        for file in (output / "analysis").glob("*.csv"):
            with file.open() as f:
                reader = csv.DictReader(f)
                fields, rows = reader.fieldnames, list(reader)
            for row in rows:
                for key, value in row.items():
                    if value is not None:
                        row[key] = value.replace(str(directory), archive_ref + "!/" + directory.name)
            write_csv(file, rows, fields)
        with (output / "analysis/callbacks_and_costs.csv").open() as f:
            reused = verify_reused_costs(list(csv.DictReader(f)))
        if (summary["completed_runs"] != 139 or summary["callbacks"] != 2589
                or summary["missing_unique_points"] != 0 or len(reused) != 4
                or summary["errors"][0]["job_id"] != RETRY_JOB):
            raise ValueError("Unexpected imported matrix/cost inventory")
        save(output / "reused_infeasible_costs.json", reused)
        save(output / "audit.json", {
            "archive": archive_ref, "archive_sha256": sha(archive),
            "verified_archive_members": count, "verified_source_files": len(run["source_files_sha256"]),
            "independently_replayed_completed_jobs": replayed, "summary": summary,
            "cost_policy_authorization": "User requested reuse of existing same-coordinate CSTR infeasible measurements; prefer CSTR30",
            "cstr30_fallback": "(13,15) uses existing CSTR20 total_wall_s=0.6212939228862524; explicitly labelled",
            "script_sha256": sha(__file__), "official_results_modified": False,
        })
        save(output / "runtime.json", run["runtime"])
    target = ROOT / "results/archives" / archive.name
    if target.exists() and sha(target) != sha(archive):
        raise ValueError("Refusing to overwrite another archive")
    if target != archive:
        shutil.copyfile(archive, target)
    target.with_suffix(".zip.sha256").write_text(sha(target) + "  " + target.name + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results/process_dsda_fairness_20261014")
    args = parser.parse_args()
    build(args.archive, args.output)
