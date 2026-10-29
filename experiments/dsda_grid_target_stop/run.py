"""Grid-only validation, smoke, and resumable sequential Dantzig execution."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

from protocol import analyze, audit_one, read, require, sha, verify_inputs, write
from runtime import THREADS, verify_repository

ROOT = Path(__file__).resolve().parent
os.environ.update(THREADS)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def execute_child(root, job, directory, cpu=None):
    command = [
        sys.executable,
        str(root / "worker.py"),
        "--job",
        job["spec"]["job_id"],
        "--output",
        str(directory),
    ]
    started = time.perf_counter()
    code = subprocess.run(command, env={**os.environ, **THREADS}).returncode
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "process.json",
        dict(
            command=command,
            returncode=code,
            watchdog_seconds=None,
            watchdog_timeout=False,
            wall_s=time.perf_counter() - started,
            cpu=cpu,
        ),
    )
    require(code == 0, "Grid worker failed: " + job["spec"]["job_id"])
    return audit_one(root, job, directory, cpu)


def validate_completed(root, job, directory):
    marker = directory / "COMPLETE.json"
    require(marker.exists(), "No validated completion marker")
    saved = read(marker)
    require(
        saved["input_seal"] == sha(root / "SHA256SUMS.json"),
        "Completed run belongs to another input snapshot",
    )
    for name, h in saved["files"].items():
        require(sha(directory / name) == h, "Completed run file changed: " + name)
    p = read(directory / "process.json")
    require(
        p["returncode"] == 0 and p["watchdog_seconds"] is None,
        "Completed worker was not successful",
    )
    return audit_one(root, job, directory, p["cpu"])


def mark_complete(root, job, directory):
    p = read(directory / "process.json")
    audit_one(root, job, directory, p["cpu"])
    require(p["returncode"] == 0, "Cannot seal failed worker")
    write(
        directory / "COMPLETE.json",
        dict(
            input_seal=sha(root / "SHA256SUMS.json"),
            files={
                n: sha(directory / n)
                for n in (
                    "result.json",
                    "callbacks.jsonl",
                    "search.log",
                    "process.json",
                )
            },
        ),
    )


def smoke(root, out, cpu=None):
    jobs = verify_inputs(root)
    chosen = [
        next(
            j
            for j in jobs
            if j["spec"]["case"] == c
            and j["spec"]["budget"] == b
            and j["spec"]["seed"] == s
        )
        for c, b, s in [("ackley", 10, 0), ("csendes", 100, 3), ("easom", 100, 5)]
    ]
    records = []
    for job in chosen:
        records.append(execute_child(root, job, out / job["spec"]["job_id"], cpu))
    write(
        out / "smoke_summary.json",
        dict(
            grid_jobs=len(records),
            process_jobs=0,
            other_method_jobs=0,
            solver_calls=0,
            records=records,
        ),
    )
    return records


def server(root, repo, out, resume=False):
    jobs = verify_inputs(root)
    require(
        platform.system() == "Linux" and platform.node().startswith("dantzig"),
        "Full execution requires Dantzig Linux",
    )
    require(
        str(repo) == "/local/scratch/a/lee4382/repository/RBFopt_Test",
        "Wrong server repository",
    )
    require(
        Path(sys.executable).absolute() == repo / ".venv-dantzig/bin/python",
        "Use existing Dantzig Python",
    )
    versions = {n: importlib.metadata.version(n) for n in ("numpy", "scipy", "pandas")}
    require(
        platform.python_version() == "3.11.16"
        and versions == dict(numpy="2.4.6", scipy="1.17.1", pandas="2.3.3"),
        "Historical Python environment differs",
    )
    identity = verify_repository(repo)
    require(
        out.is_relative_to(repo / "results") and out != repo / "results",
        "Output must be under repository/results",
    )
    require(
        resume == out.exists(),
        "Choose a new output, or explicitly resume an existing one",
    )
    if out.with_suffix(".zip").exists():
        verification = analyze(out / "reproduction", out, save=False)
        require(
            verification["status"] == "PASS",
            "Existing final archive has invalid results",
        )
        print("ALREADY_COMPLETE", out.with_suffix(".zip"), flush=True)
        return
    if not resume:
        out.mkdir(parents=True)
        shutil.copytree(
            root, out / "reproduction", ignore=shutil.ignore_patterns("__pycache__")
        )
        root = out / "reproduction"
        write(
            out / "execution_manifest.json",
            dict(
                experiment="Grid target stopping aligned to common success",
                utc_started=datetime.now(timezone.utc).isoformat(),
                baseline=read(root / "BASELINE.json"),
                input_seal=sha(root / "SHA256SUMS.json"),
                repository=str(repo),
                repository_identity=identity,
                server_worktree_status=subprocess.check_output(
                    ["git", "-C", str(repo), "status", "--short"], text=True
                ),
                python=platform.python_version(),
                versions=versions,
                threads=THREADS,
                expected=1050,
                process_jobs=0,
                other_method_jobs=0,
                sessions=[],
            ),
        )
    manifest = read(out / "execution_manifest.json")
    require(
        manifest["input_seal"] == sha(root / "SHA256SUMS.json"),
        "Resume source/input differs",
    )
    session_id = len(manifest["sessions"]) + 1
    session_dir = out / "sessions" / str(session_id)
    session_dir.mkdir(parents=True)
    preflight_path = os.environ.get("DSDA_GRID_PREFLIGHT")
    if preflight_path:
        shutil.copy2(preflight_path, session_dir / "launch_preflight.json")
    session = dict(
        command=sys.argv,
        started=datetime.now(timezone.utc).isoformat(),
        executed=0,
        reused=0,
        smoke_jobs=0,
        error=None,
    )
    manifest["sessions"].append(session)
    write(out / "execution_manifest.json", manifest)
    try:
        with (session_dir / "tests.log").open("x") as log:
            subprocess.run(
                [sys.executable, str(root / "test_experiment.py")],
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**os.environ, **THREADS},
            )
        from select_dsda_cpu import select

        selection = select(preferred=-1)
        require(
            selection["selected_cpu"] is not None
            and selection.get("physical_core_observed_idle"),
            "No idle physical core observed; no Grid search started",
        )
        cpu = selection["selected_cpu"]
        os.sched_setaffinity(0, {cpu})
        require(
            sorted(os.sched_getaffinity(0)) == [cpu],
            "CPU affinity could not be applied",
        )
        selection["effective_cpus"] = [cpu]
        session["cpu_allocation"] = selection
        write(session_dir / "cpu_allocation.json", selection)
        write(out / "execution_manifest.json", manifest)
        print(
            "CPU",
            cpu,
            "SMT",
            selection["smt_siblings"],
            "PHYSICAL_CORE_OBSERVED_IDLE True; exclusive_reservation=False",
            flush=True,
        )
        smoke(root, session_dir / "smoke", cpu)
        session["smoke_jobs"] = 3
        for index, job in enumerate(jobs, 1):
            directory = out / "runs" / job["spec"]["job_id"]
            if (directory / "COMPLETE.json").exists():
                validate_completed(root, job, directory)
                session["reused"] += 1
                continue
            if directory.exists():
                # Recover a completed, auditable child without running it again.
                if (directory / "result.json").exists() and (
                    directory / "process.json"
                ).exists():
                    try:
                        p = read(directory / "process.json")
                        require(p["returncode"] == 0, "Incomplete child")
                        audit_one(root, job, directory, p["cpu"])
                    except Exception:
                        pass
                    else:
                        mark_complete(root, job, directory)
                        session["reused"] += 1
                        continue
                if (directory / "result.json").exists() and read(
                    directory / "result.json"
                ).get("status") == "completed":
                    raise RuntimeError(
                        "Completed result lacks valid process evidence; preserved without rerunning: "
                        + str(directory)
                    )
                saved = (
                    out
                    / "incomplete_attempts"
                    / f"{job['spec']['job_id']}_session{session_id}"
                )
                saved.parent.mkdir(parents=True, exist_ok=True)
                directory.rename(saved)
            session["executed"] += 1
            execute_child(root, job, directory, cpu)
            mark_complete(root, job, directory)
            if index % 25 == 0:
                print("VERIFIED", index, "/ 1050", flush=True)
    except Exception as exc:
        import traceback

        session["error"] = str(exc)
        (session_dir / "error.txt").write_text(traceback.format_exc())
        print("STOPPED", session["error"], flush=True)
    session["finished"] = datetime.now(timezone.utc).isoformat()
    verification = analyze(root, out)
    manifest.update(
        utc_finished=session["finished"],
        verification=verification,
        additional_nlp_calls=0,
        additional_solver_calls=0,
    )
    write(out / "execution_manifest.json", manifest)
    write(
        out / "OUTPUT_SHA256SUMS.json",
        {
            str(p.relative_to(out)): sha(p)
            for p in sorted(out.rglob("*"))
            if p.is_file()
            and p.name != "OUTPUT_SHA256SUMS.json"
            and "__pycache__" not in p.parts
        },
    )
    archive = (
        out.with_suffix(".zip")
        if verification["status"] == "PASS"
        else out.parent / (out.name + f"_incomplete_session{session_id}.zip")
    )
    with ZipFile(archive, "x", ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                z.write(p, str(Path(out.name) / p.relative_to(out)))
    print("RETURN_ARCHIVE", archive, flush=True)
    print("SHA256", sha(archive), flush=True)
    print(json.dumps(verification, indent=2), flush=True)
    require(
        verification["status"] == "PASS",
        "Incomplete experiment; inspect error and resume the same output",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["verify", "smoke", "server"])
    p.add_argument("--output", type=Path)
    p.add_argument("--repo", type=Path)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    if a.mode == "verify":
        print("VALID_GRID_ONLY_JOBS", len(verify_inputs(ROOT)))
    elif a.mode == "smoke":
        require(
            a.output is not None and not a.output.exists(),
            "Smoke needs a new output directory",
        )
        smoke(ROOT, a.output)
    else:
        require(
            a.repo is not None and a.output is not None,
            "Server mode requires repository and output paths",
        )
        server(ROOT, a.repo.resolve(), a.output.resolve(), a.resume)
