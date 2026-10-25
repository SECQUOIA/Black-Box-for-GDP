"""Sequential CPU-2-only Column follow-up with immutable attempts and locks."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile

from common import METHODS, THREADS, read, require, sha, verify_package, write
from analyze import generate, selected

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path(
    "/local/scratch/a/lee4382/repository/RBFopt_Test/results/column_logical_b13"
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def report_occupancy(occupancy, path):
    print(
        "CPU_CHECK="
        + ("passed" if occupancy["permitted_to_start"] else "blocked")
        + "; CPU=2; SMT="
        + ",".join(map(str, occupancy["siblings"])),
        flush=True,
    )
    for cpu in occupancy["siblings"]:
        loads = [
            interval[cpu]
            for interval in occupancy["busy_percent_by_interval"]
            if cpu in interval
        ]
        mean = occupancy.get("busy_percent_over_window", {}).get(cpu)
        print(
            f"CPU_LOAD cpu={cpu}; window_percent={mean}; maximum_interval_percent={max(loads, default=None)}",
            flush=True,
        )
    for reason in occupancy["blockers"]:
        print("CPU_BLOCK=" + reason, flush=True)
    services = {
        p["pid"]: p for p in occupancy.get("background_services_assessed_by_load", [])
    }
    for pid, process in sorted(services.items()):
        print(
            f"CPU_BACKGROUND pid={pid}; command={process['command']}; unrestricted system service; activity included in unchanged CPU load limits",
            flush=True,
        )
    tasks = {}
    for group in occupancy.get("process_samples", []):
        for process in group.values():
            identity = f"{process['pid']}/{process['tid']}"
            if any(identity in reason for reason in occupancy["blockers"]):
                tasks[identity] = process
    for identity, process in sorted(tasks.items()):
        print(
            f"CPU_TASK={identity}; last_cpu={process['last_cpu']}; allowed={process['allowed']}; command={process['command']}",
            flush=True,
        )
    print("CPU_OCCUPANCY_RECORD=" + str(path), flush=True)


@contextmanager
def locked(output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".column_cpu2.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "An existing Column controller or worker still holds the CPU-2 experiment lock"
            ) from None
        # Do not explicitly unlock: inherited worker descriptors must retain the
        # lock if a controller is interrupted while that worker remains alive.
        yield lock.fileno()


def command(job, directory, check=False):
    executable = Path(job["python"])
    require(
        executable.is_file() and os.access(executable, os.X_OK),
        "Recorded Python environment is unavailable: " + str(executable),
    )
    if (executable.parent.parent / "conda-meta").is_dir():
        conda = Path(job["config"]["conda"])
        require(conda.is_file(), "Recorded conda executable is unavailable")
        cmd = [
            str(conda),
            "run",
            "--no-capture-output",
            "--prefix",
            str(executable.parent.parent),
            "python",
        ]
    else:
        cmd = [str(executable)]
    require(shutil.which("taskset"), "Linux taskset is required; no unpinned fallback")
    cmd = [
        "taskset",
        "-c",
        "2",
        *cmd,
        str(ROOT / "worker.py"),
        "--job-id",
        job["spec"]["job_id"],
        "--directory",
        str(directory),
    ]
    if check:
        cmd.append("--check")
    return cmd


def process_identity(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return dict(pid=pid, start_ticks=int(fields[19]))


def alive(identity):
    try:
        return process_identity(identity["pid"]) == identity
    except (FileNotFoundError, ProcessLookupError):
        return False


def launch(job, directory, fd, check=False):
    directory.mkdir(parents=True)
    write(directory / "job.json", job)
    cmd = command(job, directory, check)
    env = {
        **os.environ,
        **THREADS,
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "MPLBACKEND": "Agg",
        "PYTHONPATH": str(ROOT),
    }
    timeout = 90 if check else job["hard_seconds"]
    start = time.monotonic()
    with (directory / "run.log").open("wb") as log:
        child = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(fd,),
        )
        process = dict(
            identity=process_identity(child.pid),
            command=cmd,
            started_utc=utc(),
            hard_seconds=timeout,
            requested_cpu=2,
        )
        write(directory / "process.json", process)
        watchdog = False
        try:
            code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            watchdog = True
            # Only this launcher's own worker process group is terminated.
            os.killpg(child.pid, signal.SIGTERM)
            try:
                code = child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                code = child.wait()
    process.update(
        returncode=code,
        watchdog_timeout=watchdog,
        finished_utc=utc(),
        worker_process_wall_s=time.monotonic() - start,
    )
    write(directory / "process.json", process)
    if check:
        require(
            code == 0 and (directory / "passed.json").exists(),
            "Environment preflight failed: " + str(directory / "run.log"),
        )
        return
    result_path = directory / "result.json"
    if not result_path.exists() or code or watchdog:
        previous = read(result_path) if result_path.exists() else None
        if previous:
            write(directory / "worker_result_before_controller_failure.json", previous)
        write(
            result_path,
            dict(
                status="execution_failed",
                error="worker watchdog"
                if watchdog
                else f"worker exit {code}; missing/invalid result",
                recorded_search_wall_s=previous.get("recorded_search_wall_s")
                if previous
                else None,
                process_nlp_calls=0,
                controller_failure=True,
            ),
        )
    write(
        directory / "terminal.json",
        dict(
            finished_utc=utc(),
            files_sha256={
                p.name: sha(p)
                for p in sorted(directory.iterdir())
                if p.is_file() and p.name != "terminal.json"
            },
        ),
    )


def execute(directory, plan, fd, resume_interrupted=False):
    for job in plan:
        job_id = job["spec"]["job_id"]
        if selected(directory, job_id):
            continue
        parent = directory / "jobs" / job_id
        old = sorted(parent.glob("attempt_*"))
        if old:
            for attempt in old:
                if (attempt / "process.json").exists():
                    require(
                        not alive(read(attempt / "process.json")["identity"]),
                        "Original worker is still alive; do not duplicate it",
                    )
            require(
                resume_interrupted,
                "Unsealed infrastructure attempt exists; preserve it and use --resume-interrupted explicitly",
            )
            write(
                parent / f"resume_{time.time_ns()}.json",
                dict(
                    reason="Controller/infrastructure interruption; previous unsealed attempts retained.",
                    previous_attempts=[p.name for p in old],
                    utc=utc(),
                ),
            )
        attempt = parent / f"attempt_{len(old) + 1:04d}"
        print("START " + job_id, flush=True)
        launch(job, attempt, fd)
        result = read(attempt / "result.json")
        count = sum(selected(directory, j["spec"]["job_id"]) is not None for j in plan)
        write(
            directory / "progress.json",
            dict(
                sealed=count,
                planned=50,
                last_job=job_id,
                last_status=result["status"],
                updated_utc=utc(),
            ),
        )
        print(f"DONE {job_id}: {result['status']}; {count}/50", flush=True)


def pack(directory):
    require(
        not active_workers(directory),
        "A worker is still active; result packaging is deferred",
    )
    archive = directory.parent / (directory.name + f"_snapshot_{time.time_ns()}.zip")
    temporary = archive.with_suffix(".zip.tmp")
    paths = [
        p
        for p in sorted(directory.rglob("*"))
        if p.is_file()
        and not p.is_symlink()
        and "__pycache__" not in p.parts
        and not p.name.endswith((".tmp", ".lock"))
    ]
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, directory.name + "/" + p.relative_to(directory).as_posix())
        z.writestr(
            directory.name + "/SHA256SUMS",
            "".join(
                f"{sha(p)}  {p.relative_to(directory).as_posix()}\n" for p in paths
            ),
        )
    with zipfile.ZipFile(temporary) as z:
        require(z.testzip() is None, "Result ZIP CRC failure")
    temporary.replace(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{sha(archive)}  {archive.name}\n")
    (directory.parent / "result_zip.txt").write_text(str(archive) + "\n")
    print("RESULT_ZIP=" + str(archive), flush=True)


def active_workers(directory):
    return [
        str(p)
        for p in directory.rglob("process.json")
        if "identity" in read(p) and alive(read(p)["identity"])
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("plan", "check", "run", "resume", "status", "analyze", "pack")
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--resume-interrupted", action="store_true")
    args = parser.parse_args()
    plan, _ = verify_package(ROOT)
    if args.mode == "plan":
        print((ROOT / "input_verification.json").read_text())
        return
    if args.mode in ("resume", "status", "analyze", "pack"):
        require(args.run_dir is not None, "--run-dir is required")
        directory = args.run_dir.resolve()
        require(
            read(directory / "run.json")["package_sha256"]
            == sha(ROOT / "manifest.json"),
            "Frozen execution package changed",
        )
    else:
        args.output_root.mkdir(parents=True, exist_ok=True)
        prefix = (
            "column_logical_b13_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + "_"
        )
        directory = Path(
            tempfile.mkdtemp(prefix=prefix, dir=args.output_root)
        ).resolve()
        write(
            directory / "run.json",
            dict(
                package_sha256=sha(ROOT / "manifest.json"),
                mode=args.mode,
                source_base_revision=read(ROOT / "manifest.json")[
                    "source_base_revision"
                ],
                created_utc=utc(),
                controller_pid=os.getpid(),
                command=sys.argv,
                cpu=2,
                planned_jobs=50,
                original_process_nlp_calls=0,
                status="preparing",
            ),
        )
        for name in [
            *read(ROOT / "manifest.json")["files_sha256"],
            "manifest.json",
            "SHA256SUMS",
        ]:
            target = directory / "reproduction" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
    print("RUN_DIR=" + str(directory), flush=True)
    if args.mode == "status":
        print(
            (directory / "progress.json").read_text()
            if (directory / "progress.json").exists()
            else (directory / "run.json").read_text()
        )
        return
    with locked(DEFAULT_OUTPUT) as fd:
        if args.mode in ("run", "resume", "check"):
            record = read(directory / "run.json")
            try:
                from cpu_guard import inspect

                print(
                    "CPU_CHECK=inspecting CPU 2 and SMT siblings for at least 12 seconds",
                    flush=True,
                )
                occupancy = inspect()
                occupancy_path = directory / f"cpu2_occupancy_{time.time_ns()}.json"
                write(occupancy_path, occupancy)
                report_occupancy(occupancy, occupancy_path)
                require(
                    occupancy["permitted_to_start"],
                    "CPU 2/SMT check blocked launch: "
                    + "; ".join(occupancy["blockers"])
                    + "; record="
                    + str(occupancy_path),
                )
                os.sched_setaffinity(0, {2})
                record.update(
                    status="preflight",
                    effective_cpus=sorted(os.sched_getaffinity(0)),
                    cpu_occupancy_confirmed_utc=utc(),
                )
                write(directory / "run.json", record)
                for method in METHODS:
                    job = next(j for j in plan if j["spec"]["method"] == method)
                    launch(
                        job,
                        directory / "preflight" / f"{method}_{time.time_ns()}",
                        fd,
                        check=True,
                    )
                record.update(
                    status="running" if args.mode != "check" else "checked",
                    preflight_passed_utc=utc(),
                )
                write(directory / "run.json", record)
                print("PREFLIGHT=passed; CPU=2; CONCURRENCY=1", flush=True)
                if args.mode != "check":
                    execute(directory, plan, fd, args.resume_interrupted)
                    record.update(status="finished", finished_utc=utc())
                    write(directory / "run.json", record)
            except BaseException as error:
                record.update(
                    status="blocked_or_interrupted",
                    error=f"{type(error).__name__}: {error}",
                    updated_utc=utc(),
                )
                write(directory / "run.json", record)
                raise
            finally:
                if active_workers(directory):
                    print(
                        "PACK_DEFERRED=own worker is still active; its inherited lock prevents duplicate launch",
                        flush=True,
                    )
                else:
                    try:
                        generate(
                            directory,
                            directory / f"analysis_{time.time_ns()}",
                            plots=True,
                        )
                    finally:
                        # Preserve raw results even if an analysis check rejects
                        # an unexpected callback or plotting is unavailable.
                        pack(directory)
        elif args.mode == "analyze":
            generate(directory, directory / f"analysis_{time.time_ns()}")
        elif args.mode == "pack":
            pack(directory)


if __name__ == "__main__":
    main()
