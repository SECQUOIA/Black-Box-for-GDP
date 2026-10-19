"""Recover the single October 14 validator failure without rerunning 139 jobs.

The original ZIP is embedded unchanged in the new result. Copied jobs retain
their exact bytes and old source provenance. Only the failed job is remeasured.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

import process_dsda_fairness as runner

PARENT_SHA256 = "3669558ab1b0197d0cf2b6ad4ff0df7c8b4f9b1a92a15747bff8909e6f5ef397"
RETRY_JOB = "cstr_15_B22_seed9_dsda"
ALLOWED_SOURCE_CHANGES = {
    "process_dsda_fairness.py",
    "process_dsda_fairness_analysis.py",
    "tests/test_process_dsda_fairness.py",
    "tests/test_process_dsda_fairness_analysis.py",
    "docs/process_dsda_fairness_dantzig.txt",
    "docs/process_dsda_fairness_report.txt",
}
NEW_SOURCES = {"process_dsda_fairness_recovery.py"}
# This obsolete progress report is retained inside the frozen archives. Its
# removal from new bundles must not relax checks on executable/model sources.
RETIRED_DOCUMENTS = {"docs/process_dsda_fairness_report.txt"}


def parent_inventory(archive):
    """Verify the exact received archive, its paths, and its complete manifest."""
    archive = Path(archive)
    if runner.sha(archive) != PARENT_SHA256:
        raise ValueError("Expected the verified pudvsttz result ZIP; parent hash differs")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Duplicate archive member")
        paths = [PurePosixPath(n) for n in names]
        if any(p.is_absolute() or ".." in p.parts for p in paths):
            raise ValueError("Unsafe archive path")
        roots = {p.parts[0] for p in paths}
        if len(roots) != 1:
            raise ValueError("Expected one parent run")
        prefix = roots.pop() + "/"
        manifest = dict(
            (rel, digest)
            for digest, rel in (
                line.split(None, 1)
                for line in z.read(prefix + "SHA256SUMS").decode().splitlines()
            )
        )
        if set(names) != {prefix + n for n in manifest} | {prefix + "SHA256SUMS"}:
            raise ValueError("Parent manifest is incomplete")
        for name, digest in manifest.items():
            if hashlib.sha256(z.read(prefix + name)).hexdigest() != digest:
                raise ValueError("Parent checksum mismatch: " + name)
        run = json.loads(z.read(prefix + "run.json"))
        if run["development_only"] or run["smoke_only"] or len(run["plan"]) != 140:
            raise ValueError("Parent is not the full Dantzig measurement")
        completed = []
        errors = []
        for spec in run["plan"]:
            result = json.loads(z.read(prefix + "jobs/" + spec["job_id"] + "/result.json"))
            if result["spec"] != spec:
                raise ValueError("Parent spec mismatch")
            if result["status"] == "completed":
                completed.append(spec["job_id"])
            else:
                errors.append((spec["job_id"], result.get("exception")))
        if len(completed) != 139 or errors != [(RETRY_JOB, "Final best disagrees with callbacks")]:
            raise ValueError("Unexpected parent outcomes")
        old = run["source_files_sha256"]
        if any(manifest["source/" + name] != digest for name, digest in old.items()):
            raise ValueError("Parent source manifest mismatch")
    return prefix, manifest, run, completed


def check_sources(old, current):
    removed = set(old) - set(current)
    if removed - RETIRED_DOCUMENTS or set(current) - set(old) != NEW_SOURCES:
        raise ValueError("Unexpected recovery source inventory")
    changed = removed | {name for name in old.keys() & current.keys() if old[name] != current[name]}
    if changed - ALLOWED_SOURCE_CHANGES:
        raise ValueError("Recovery changed search/model inputs: " + str(sorted(changed)))
    return sorted(changed)


def check_runtime(current, parent, development):
    if development:
        return
    if current["development_only"] or any(
        current[key] != parent[key]
        for key in ("host", "executable", "versions", "thread_environment")
    ):
        raise ValueError("Use the same host, Python environment, versions and threads as parent")
    if current["affinity"]["effective_cpus"] != parent["affinity"]["effective_cpus"]:
        raise ValueError("Use the original CPU (7)")


def verify_recovery(directory):
    """Verify every copied byte and the retry's path against original evidence."""
    directory = Path(directory)
    run = runner.read(directory / "run.json")
    provenance = run["recovery"]
    prefix, inventory, parent, completed = parent_inventory(directory / "parent_result.zip")
    if (provenance["parent_zip_sha256"] != PARENT_SHA256
            or provenance["preserved_job_ids"] != completed
            or provenance["remeasured_job_ids"] != [RETRY_JOB]
            or run["plan"] != parent["plan"]):
        raise ValueError("Recovery selection/provenance differs")
    changed = check_sources(parent["source_files_sha256"], run["source_files_sha256"])
    if provenance["changed_source_files"] != changed:
        raise ValueError("Recovery source provenance differs")
    check_runtime(run["runtime"], parent["runtime"], run["development_only"])
    for ident in completed:
        job = directory / "jobs" / ident
        actual = {
            str(p.relative_to(directory)): runner.sha(p)
            for p in job.rglob("*") if p.is_file()
        }
        expected = {n: s for n, s in inventory.items() if n.startswith("jobs/" + ident + "/")}
        if actual != expected:
            raise ValueError("Preserved job was changed: " + ident)
    job = directory / "jobs" / RETRY_JOB
    if (job / "terminal.json").exists() and runner.valid_job(job)["status"] == "completed":
        with zipfile.ZipFile(directory / "parent_result.zip") as z:
            trace = next(n for n in inventory if n.startswith("jobs/" + RETRY_JOB + "/lookup.traces/"))
            original = [json.loads(line) for line in z.read(prefix + trace).splitlines()]
        def signature(rows):
            return [
                (e["point"], e["value"], e["value_kind"])
                for e in rows if e.get("event") == "evaluation"
            ]
        if signature(original) != signature(runner.read(job / "callbacks.json")):
            raise ValueError("Retry differs from original measured callback path")
    return {"preserved_jobs": len(completed), "remeasured_jobs": [RETRY_JOB]}


def recover(parent_zip, output_root, cpu, development=False):
    if parent_zip is None:
        raise ValueError("recover requires --parent-zip")
    parent_zip = Path(parent_zip).resolve()
    prefix, inventory, parent, completed = parent_inventory(parent_zip)
    reference = runner.read(runner.ROOT / runner.REFERENCE)
    if runner.verify_plan(reference) != parent["plan"]:
        raise ValueError("Frozen full plan differs from parent")
    current = runner.hashes()
    changed = check_sources(parent["source_files_sha256"], current)
    if (runner.ROOT / "bundle.json").exists() and runner.read(runner.ROOT / "bundle.json")["source_files_sha256"] != current:
        raise ValueError("Recovery bundle content changed")
    runtime = runner.runtime(cpu, development)
    check_runtime(runtime, parent["runtime"], development)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="process_dsda_recovered_20261014_", dir=output_root)).resolve()
    print("RUN_DIR=" + str(directory), flush=True)
    try:
        shutil.copyfile(parent_zip, directory / "parent_result.zip")
        with zipfile.ZipFile(parent_zip) as z:
            for name in inventory:
                parts = PurePosixPath(name).parts
                if len(parts) >= 3 and parts[0] == "jobs" and parts[1] in completed:
                    dest = directory / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(z.read(prefix + name))
        run = {
            **parent,
            "created_utc": runner.now(),
            "development_only": development,
            "runtime": runtime,
            "source_files_sha256": current,
            "build_metadata": runner.read(runner.ROOT / "bundle.json")
                if (runner.ROOT / "bundle.json").exists() else runner.git_state(runner.ROOT),
            "recovery": {
                "parent_zip_sha256": PARENT_SHA256,
                "parent_run_name": prefix.rstrip("/"),
                "preserved_job_ids": completed,
                "remeasured_job_ids": [RETRY_JOB],
                "changed_source_files": changed,
                "source_policy": "Preserved jobs use parent_result.zip/source and parent runtime; only retry uses current source/runtime",
                "reason": "Exact-equality validator ignored unchanged DSDA improvement tolerance; original method clock was not retained",
            },
        }
        runner.save(directory / "run.json", run)
        runner.save(output_root / "latest_run.json", {"run_dir": str(directory)})
        for name in current:
            dest = directory / "source" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(runner.ROOT / name, dest)
        verify_recovery(directory)
    except BaseException as error:
        runner.save(directory / "preflight_error.json", {"error": str(error)})
        runner.pack(directory)
        raise
    print("PRESERVED_JOBS=139 NEW_MEASURED_JOBS=1 NEW_NLP_SOLVES=0", flush=True)
    runner.execute(directory)
