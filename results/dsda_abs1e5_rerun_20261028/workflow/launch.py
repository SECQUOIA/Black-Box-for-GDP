"""Prepare, select a currently idle physical core, and detach one new run."""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import prepare
import run
import select_dsda_cpu


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def launch():
    if platform.system() != "Linux" or not platform.node().startswith("dantzig"):
        raise RuntimeError("Launch must run on Dantzig Linux")
    if str(REPO.resolve()) != "/local/scratch/a/lee4382/repository/RBFopt_Test":
        raise RuntimeError(
            "Install this workflow in the Dantzig RBFopt_Test repository"
        )
    run.verify_repository(REPO)
    expected = REPO / ".venv-dantzig/bin/python"
    if Path(sys.executable).absolute() != expected:
        raise RuntimeError("Use the existing .venv-dantzig/bin/python")
    lock = (HERE / ".execution.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError(
            "This repository workflow already has an active run; no second run was started"
        ) from None
    prepared = prepare.prepare()
    selection = select_dsda_cpu.select(preferred=-1)
    if selection["selected_cpu"] is None or not selection.get(
        "physical_core_observed_idle"
    ):
        report = prepared / "CPU_SELECTION_NOT_READY.json"
        report.write_text(json.dumps(selection, indent=2) + "\n")
        raise RuntimeError(
            "No fully idle physical core observed; no full experiment started; "
            + str(report)
        )
    selected = selection["selected_cpu"]
    os.sched_setaffinity(0, {selected})
    if sorted(os.sched_getaffinity(0)) != [selected]:
        raise RuntimeError("Could not pin the selected CPU")
    selection["effective_cpus"] = [selected]
    selection_file = prepared / "CPU_SELECTION.json"
    selection_file.write_text(json.dumps(selection, indent=2) + "\n")
    seal_file = prepared / "SHA256SUMS.json"
    seal = json.loads(seal_file.read_text())
    seal["CPU_SELECTION.json"] = hashlib.sha256(selection_file.read_bytes()).hexdigest()
    seal_file.write_text(json.dumps(seal, indent=2) + "\n")
    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(os.getpid())
    output = REPO / "results" / ("dsda_abs1e5_rerun_" + tag)
    log = REPO / "results" / ("dsda_abs1e5_launch_" + tag + ".log")
    command = [
        sys.executable,
        "-u",
        str(prepared / "run.py"),
        "server",
        "--repo",
        str(REPO),
        "--output",
        str(output),
    ]
    environment = {
        **os.environ,
        **select_dsda_cpu.THREADS,
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DSDA_CPU_SELECTION_RECORD": str(selection_file),
        "DSDA_SELECTED_CPU": str(selected),
    }
    with log.open("xb") as stream:
        child = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=environment,
            pass_fds=(lock.fileno(),),
        )
    record = dict(
        pid=child.pid,
        command=command,
        input_directory=str(prepared),
        result_directory=str(output),
        log=str(log),
        expected_return_archive=str(output.with_suffix(".zip")),
        selected_cpu=selected,
        smt_siblings=selection["smt_siblings"],
        physical_core_observed_idle=True,
        exclusive_reservation=False,
        status="launched_completion_not_yet_confirmed",
    )
    lock.seek(0)
    lock.truncate()
    lock.write(json.dumps(record) + "\n")
    lock.flush()
    # The detached server process retains this descriptor and holds the lock.
    lock.close()
    (REPO / "results" / ("dsda_abs1e5_launch_" + tag + ".json")).write_text(
        json.dumps(record, indent=2) + "\n"
    )
    print("LAUNCHED PID", child.pid, flush=True)
    print(
        "CPU",
        selected,
        "SMT",
        selection["smt_siblings"],
        "PHYSICAL_CORE_IDLE True",
        flush=True,
    )
    print("LOG", log, flush=True)
    print("RESULTS", output, flush=True)
    print("EXPECTED_RETURN_ARCHIVE", output.with_suffix(".zip"), flush=True)
    print(
        "Execution continues after this SSH session closes; completion must be checked in the log.",
        flush=True,
    )
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    launch()
