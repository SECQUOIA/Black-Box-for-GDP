"""Prepare and detach one Grid-only Dantzig run, or resume its sealed records."""

import argparse
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import platform
import subprocess
import sys

from prepare import prepare
from protocol import read, require, write
from runtime import THREADS, verify_repository

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def launch(resume=None):
    require(
        platform.system() == "Linux" and platform.node().startswith("dantzig"),
        "Use Dantzig Linux",
    )
    require(
        str(REPO) == "/local/scratch/a/lee4382/repository/RBFopt_Test",
        "Install in the permanent Dantzig repository",
    )
    require(
        Path(sys.executable).absolute() == REPO / ".venv-dantzig/bin/python",
        "Use the existing .venv-dantzig/bin/python",
    )
    identity = verify_repository(REPO)
    locks = []
    candidates = [
        HERE / ".execution.lock",
        REPO / "experiments/dsda_abs1e5/.execution.lock",
    ]
    for path in candidates:
        if not path.parent.exists():
            continue
        lock = path.open("a+")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "An existing D-SDA workflow is active; nothing terminated: " + str(path)
            ) from None
        locks.append(lock)
    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(os.getpid())
    preflight = dict(
        repository_identity=identity,
        repository_status=subprocess.check_output(
            ["git", "-C", str(REPO), "status", "--short"], text=True
        ),
        process_snapshot=subprocess.check_output(
            ["ps", "-e", "-o", "pid=,user=,psr=,pcpu=,comm="], text=True
        ),
        utc=datetime.now(timezone.utc).isoformat(),
        existing_workflow_locks_acquired=[
            str(p) for p in candidates if p.parent.exists()
        ],
        other_jobs_terminated=False,
    )
    if resume:
        out = Path(resume).resolve()
        require(
            out.is_relative_to(REPO / "results") and out.is_dir(),
            "Resume requires an existing result directory",
        )
        frozen = out / "reproduction"
        require((frozen / "run.py").is_file(), "No sealed reproduction directory")
        if out.with_suffix(".zip").exists():
            subprocess.run(
                [sys.executable, str(frozen / "verify.py"), "--results", str(out)],
                check=True,
            )
            print("ALREADY_COMPLETE", out.with_suffix(".zip"), flush=True)
            return
    else:
        name = read(HERE / "BASELINE.json")["archive_name"]
        archive = next(
            (
                p
                for p in [REPO / "results" / name, REPO / "results/archives" / name]
                if p.is_file()
            ),
            None,
        )
        require(archive is not None, "Missing second D-SDA return archive: " + name)
        frozen = prepare(REPO, archive)
        out = REPO / "results" / ("dsda_grid_target_stop_" + tag)
    log = REPO / "results" / ("dsda_grid_target_stop_launch_" + tag + ".log")
    preflight_path = (
        REPO / "results" / ("dsda_grid_target_stop_preflight_" + tag + ".json")
    )
    write(preflight_path, preflight)
    command = [
        sys.executable,
        "-u",
        str(frozen / "run.py"),
        "server",
        "--repo",
        str(REPO),
        "--output",
        str(out),
    ]
    if resume:
        command.append("--resume")
    with log.open("xb") as f:
        child = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={
                **os.environ,
                **THREADS,
                "PYTHONDONTWRITEBYTECODE": "1",
                "DSDA_GRID_PREFLIGHT": str(preflight_path),
            },
            pass_fds=tuple(lock.fileno() for lock in locks),
        )
    record = dict(
        pid=child.pid,
        command=command,
        results=str(out),
        log=str(log),
        expected_archive=str(out.with_suffix(".zip")),
        preflight=str(preflight_path),
        status="launched_completion_not_confirmed",
        expected_grid_jobs=1050,
        process_jobs=0,
        other_method_jobs=0,
    )
    write(REPO / "results" / ("dsda_grid_target_stop_launch_" + tag + ".json"), record)
    print("PID", child.pid, flush=True)
    print("LOG", log, flush=True)
    print("RESULTS", out, flush=True)
    print("EXPECTED_RETURN_ARCHIVE", out.with_suffix(".zip"), flush=True)
    print(
        "Grid tests and smoke precede the 1050-job run; inspect the log for actual CPU selection and completion.",
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resume", type=Path)
    launch(p.parse_args().resume)
