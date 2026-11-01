#!/usr/bin/env python3
"""Server-only launch supervision; never changes experiment code or environments."""

import argparse
from contextlib import contextmanager
import ctypes
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
import zipfile

from verify import (
    audit_a,
    audit_b,
    audit_b_summary,
    read,
    require,
    sha,
    write,
    zip_check,
)

ROOT = Path(__file__).resolve().parent
REPO = Path("/local/scratch/a/lee4382/repository/RBFopt_Test")
STATE = ROOT / "state"
COORD = REPO.parent / ".pr56_57_coordination"
PIN = {
    "A": "c186408728c6f95ac33a5465edd53035d85c5620",
    "B": "5580a7eacdc8b4098ba5c239822de2300e667a1c",
}
BRANCH = {
    "A": "review/manuscript-revision-20261030",
    "B": "feature/catalytic-distillation-pilot",
}
NAME = {"A": "dsda_no_revisit", "B": "catdist_live"}
SCRIPT = {
    "A": "experiments/dsda_no_revisit/run_dantzig.sh",
    "B": "experiments/catalytic_distillation_live/run_dantzig.sh",
}
THREADS = {
    k: "1"
    for k in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "GOTO_NUM_THREADS",
        "NUMEXPR_MAX_THREADS",
    )
}
THREADS.update(
    OMP_DYNAMIC="FALSE",
    MKL_DYNAMIC="FALSE",
    PYTHONUNBUFFERED="1",
    PYTHONNOUSERSITE="1",
    CUDA_VISIBLE_DEVICES="",
    MPLBACKEND="Agg",
    PYTHONDONTWRITEBYTECODE="1",
)
ENV = {**os.environ, **THREADS, "GIT_TERMINAL_PROMPT": "0"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def stamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def saved(which):
    path = STATE / (which + ".json")
    return read(path) if path.exists() else {"task": which, "state": "not_started"}


def update(which, **values):
    data = {**saved(which), **values, "updated_utc": now()}
    write(STATE / (which + ".json"), data)
    print(which, data["state"], flush=True)
    return data


def capture(command, cwd=None, env=None, timeout=600):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env or ENV,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    require(
        result.returncode == 0,
        f"Command failed ({result.returncode}): {command[0]}\n{result.stderr[-3000:]}",
    )
    return result.stdout.strip()


def git(*args, cwd=REPO):
    return capture(["git", *args], cwd=cwd)


def identity(pid):
    try:
        text = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return None if text[0] == "Z" else text[19]
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def alive(data):
    return bool(
        data.get("pid")
        and data.get("start_ticks")
        and identity(data["pid"]) == data["start_ticks"]
    )


def host_guard():
    require(
        platform.system() == "Linux"
        and platform.node().split(".")[0].lower() == "dantzig",
        "Experiments may run only on Dantzig; local execution is prohibited",
    )
    require(
        REPO.is_dir() and (REPO / ".git").exists(),
        "Existing Dantzig repository not found",
    )
    manifest = read(ROOT / "PACKAGE_SHA256.json")
    for name, digest in manifest.items():
        require(sha(ROOT / name) == digest, f"Package changed: {name}")


def cpu_ranges(text):
    values = []
    for part in text.replace(" ", ",").split(","):
        if not part:
            continue
        lo, _, hi = part.partition("-")
        values.extend(range(int(lo), int(hi or lo) + 1))
    require(len(values) == len(set(values)), "Duplicate CPU identifiers")
    return values


def sample():
    result = {}
    for line in Path("/proc/stat").read_text().splitlines():
        fields = line.split()
        if re.fullmatch(r"cpu\d+", fields[0]):
            numbers = list(map(int, fields[1:9]))
            result[int(fields[0][3:])] = (sum(numbers), numbers[3] + numbers[4])
    return result


def topology(cpu):
    path = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
    return dict(
        cpu=cpu,
        socket=int((path / "physical_package_id").read_text()),
        core=int((path / "core_id").read_text()),
        siblings=cpu_ranges((path / "thread_siblings_list").read_text().strip()),
    )


def free_cores():
    before = sample()
    time.sleep(5)
    after = sample()
    idle = {
        c: (after[c][1] - before[c][1]) / max(1, after[c][0] - before[c][0])
        for c in before.keys() & after.keys()
    }
    cores = {}
    for cpu in sorted(os.sched_getaffinity(0)):
        row = topology(cpu)
        cores.setdefault((row["socket"], row["core"]), row)
    return [
        r for r in cores.values() if all(idle.get(c, 0) >= 0.95 for c in r["siblings"])
    ], idle


def choose_cpus(count, explicit=None, reserved=()):
    free, idle = free_cores()
    reserved = set(reserved)
    free = [r for r in free if (r["socket"], r["core"]) not in reserved]
    if explicit is not None:
        cpus = cpu_ranges(explicit)
        require(len(cpus) <= count, "Requested CPU count exceeds the worker limit")
        require(
            cpus and set(cpus) <= os.sched_getaffinity(0),
            "Requested CPUs are not in the allowed affinity",
        )
        chosen = [topology(c) for c in cpus]
        require(
            len({(r["socket"], r["core"]) for r in chosen}) == len(chosen),
            "SMT siblings cannot be separate workers",
        )
        require(
            not ({(r["socket"], r["core"]) for r in chosen} & reserved),
            "Requested physical core is held by another experiment package",
        )
        require(
            all(all(idle.get(c, 0) >= 0.95 for c in r["siblings"]) for r in chosen),
            "Requested physical core is currently busy",
        )
        return chosen
    require(free, "No idle physical core observed; retry later")
    return sorted(free, key=lambda r: r["cpu"])[-min(count, len(free)) :]


@contextmanager
def coordination(name):
    COORD.mkdir(exist_ok=True)
    with (COORD / (name + ".lock")).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def allocations():
    path = COORD / "cpus.json"
    data = read(path) if path.exists() else {}
    return {
        key: entry
        for key, entry in data.items()
        if any(alive(holder) for holder in entry["holders"])
    }


def allocation_key(which):
    return str(ROOT.resolve()) + ":" + which


def acquire_cpus(which, count, explicit=None):
    with coordination("cpus"):
        data = allocations()
        key = allocation_key(which)
        previous = data.pop(key, None)
        require(
            not previous
            or not any(
                alive(h) and h["pid"] != os.getpid() for h in previous["holders"]
            ),
            "A previous child process still holds this package's CPUs",
        )
        reserved = {
            (row["socket"], row["core"])
            for entry in data.values()
            for row in entry["cores"]
        }
        cores = choose_cpus(count, explicit, reserved)
        data[key] = dict(
            cores=cores,
            holders=[dict(pid=os.getpid(), start_ticks=identity(os.getpid()))],
            reserved_utc=now(),
        )
        write(COORD / "cpus.json", data)
        return cores


def hold_process(which, pid):
    with coordination("cpus"):
        data = allocations()
        key = allocation_key(which)
        require(key in data, "CPU allocation disappeared")
        data[key]["holders"].append(dict(pid=pid, start_ticks=identity(pid)))
        write(COORD / "cpus.json", data)


def release_cpus(which):
    with coordination("cpus"):
        data = allocations()
        key = allocation_key(which)
        if key in data and not any(
            alive(h) and h["pid"] != os.getpid() for h in data[key]["holders"]
        ):
            del data[key]
        write(COORD / "cpus.json", data)


def inventory():
    STATE.mkdir(exist_ok=True)
    found = []
    for directory in [REPO, *REPO.parents]:
        path = directory / "AGENTS.md"
        if path.is_file():
            found.append(dict(path=str(path), sha256=sha(path)))
    for name in git("ls-files").splitlines():
        if Path(name).name == "AGENTS.md":
            path = REPO / name
            found.append(dict(path=str(path), sha256=sha(path)))
    data = dict(
        host=platform.node(),
        recorded_utc=now(),
        branch=git("branch", "--show-current"),
        head=git("rev-parse", "HEAD"),
        status=git("status", "--porcelain"),
        worktrees=git("worktree", "list", "--porcelain"),
        remotes=[
            dict(
                name=n,
                url=re.sub(
                    r"(https?://)[^/@]+@", r"\1[redacted]@", git("remote", "get-url", n)
                ),
            )
            for n in git("remote").splitlines()
        ],
        processes=capture(
            ["ps", "-u", str(os.getuid()), "-o", "pid,ppid,comm,pcpu,psr"]
        ),
        allowed_cpus=sorted(os.sched_getaffinity(0)),
        scheduler={
            k: os.environ[k]
            for k in ("SLURM_JOB_ID", "SLURM_CPUS_ON_NODE", "PBS_JOBID")
            if k in os.environ
        },
        agents=found,
        existing_result_directories=sorted(
            p.name for p in (REPO / "results").iterdir() if p.is_dir()
        )
        if (REPO / "results").is_dir()
        else [],
    )
    write(STATE / ("inventory_" + stamp() + ".json"), data)
    require(
        not found,
        "AGENTS.md exists and needs human review before unattended execution: "
        + ", ".join(r["path"] for r in found),
    )
    return data


def prepare(which):
    with coordination("git_prepare"):
        return prepare_locked(which)


def prepare_locked(which):
    prior = saved(which)
    if prior.get("worktree"):
        worktree = Path(prior["worktree"])
        require(
            git("rev-parse", "HEAD", cwd=worktree) == PIN[which],
            "Existing execution worktree changed revision",
        )
        require(
            not git("status", "--porcelain", "--untracked-files=no", cwd=worktree),
            "Tracked execution source changed",
        )
        return worktree
    inventory()
    source = ROOT / "source.git"
    require(source.is_dir(), "Bundled offline source repository is missing")
    require(
        not git("remote", cwd=source), "Offline source must not have a network remote"
    )
    provenance = read(ROOT / "SOURCE_MANIFEST.json")
    require(provenance["revision"] == PIN[which], "Source manifest revision differs")
    update(
        which,
        state="verifying_offline_source",
        expected_revision=PIN[which],
        source_repository=str(source),
        branch_verified_at_packaging=provenance.get("remote_verification"),
    )
    actual = git("rev-parse", "refs/heads/pinned", cwd=source)
    if actual != PIN[which]:
        update(
            which,
            state="revision_mismatch",
            actual_revision=actual,
        )
        raise RuntimeError(
            f"{which} offline source HEAD differs: {actual}; no experiment started"
        )
    git("fsck", "--full", "--no-reflogs", cwd=source)
    agents = [
        n
        for n in git("ls-tree", "-r", "--name-only", actual, cwd=source).splitlines()
        if Path(n).name == "AGENTS.md"
    ]
    require(not agents, f"New revision includes AGENTS.md requiring review: {agents}")
    worktree = REPO.parent / NAME[which]
    if worktree.exists():
        worktree = REPO.parent / (NAME[which] + "_" + stamp())
    require(not worktree.exists(), "New worktree name already exists")
    git("worktree", "add", "--detach", str(worktree), actual, cwd=source)
    worktree = worktree.resolve()
    require(
        git("rev-parse", "HEAD", cwd=worktree) == PIN[which],
        "Worktree revision differs",
    )
    require(not git("status", "--porcelain", cwd=worktree), "New worktree is not clean")
    update(
        which,
        state="prepared",
        worktree=str(worktree),
        revision=actual,
        created_utc=now(),
    )
    return worktree


def environment(python, packages):
    require(
        Path(python).is_file() and os.access(python, os.X_OK),
        f"Required interpreter absent: {python}",
    )
    code = "import sys,platform,importlib.metadata as m,json; print(json.dumps({'executable':sys.executable,'python':platform.python_version(),'packages':{p:m.version(p) for p in sys.argv[1:]}}))"
    return json.loads(capture([str(python), "-c", code, *packages]))


def foreground(command, cwd, env, log, cpu=None, timeout=None, allocation=None):
    log = Path(log)
    require(not log.exists(), f"Log already exists: {log}")
    with log.open("w") as stream:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            preexec_fn=(lambda: os.sched_setaffinity(0, {cpu}))
            if cpu is not None
            else None,
        )
        record = dict(
            command=command,
            cwd=str(cwd),
            pid=process.pid,
            start_ticks=identity(process.pid),
            started_utc=now(),
            log=str(log),
        )
        if allocation:
            hold_process(allocation, process.pid)
        write(log.with_suffix(".execution.json"), record)
        try:
            result = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            result = process.wait()
            record["timed_out"] = True
    record.update(exit_code=result, finished_utc=now())
    write(log.with_suffix(".execution.json"), record)
    return record


def unchanged(worktree, which):
    require(
        git("rev-parse", "HEAD", cwd=worktree) == PIN[which], "Execution HEAD changed"
    )
    require(
        not git("status", "--porcelain", "--untracked-files=no", cwd=worktree),
        "Tracked source changed during execution",
    )


def no_secret_files(paths):
    markers = [
        b"-----BEGIN PRIVATE KEY-----",
        b"-----BEGIN OPENSSH PRIVATE KEY-----",
        b"ghp_",
        b"github_pat_",
    ]
    license_path = Path("/local/scratch/a/lee4382/bamlice.txt")
    if license_path.is_file():
        license_bytes = license_path.read_bytes().strip()
        if len(license_bytes) >= 24:
            markers.append(license_bytes)
    for path in paths:
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    require(
                        not re.search(
                            r"(?i)(?:^|/)(?:bamlice|gamslice|id_rsa|id_ed25519)(?:\.|$)",
                            member.filename,
                        ),
                        "Credential/license filename found in archive; publication blocked",
                    )
                    if not member.is_dir() and member.file_size < 20_000_000:
                        data = archive.read(member)
                        require(
                            not any(mark in data for mark in markers),
                            "Credential/license content found in archive; publication blocked",
                        )
        else:
            require(
                not any(mark in path.read_bytes() for mark in markers),
                "Credential/license content found in log; publication blocked",
            )


def pack_return(which, destination, status_only=False):
    archive = ROOT / ("RETURN_" + which + ("_STATUS" if status_only else "") + ".zip")
    require(not archive.exists(), f"Return already exists; kept unchanged: {archive}")
    temporary = archive.with_suffix(".building")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as out:
        for path in sorted(Path(destination).rglob("*")):
            if path.is_file():
                out.write(
                    path, str(Path(destination).name / path.relative_to(destination))
                )
    temporary.rename(archive)
    details = zip_check(archive)
    archive.with_suffix(".zip.sha256").write_text(
        details["sha256"] + "  " + archive.name + "\n"
    )
    print("RETURN_ARCHIVE=" + str(archive), flush=True)
    update(which, return_archive=str(archive), return_sha256=details["sha256"])


def readme_a(destination, execution, audit, manifest, archive):
    lines = [
        "# Dantzig D-SDA without re-evaluation",
        "",
        f"Execution revision: `{PIN['A']}`.",
        f"Host: `{manifest['host']}`; CPU: `{manifest['cpu']}`.",
        f"Started: `{execution['started_utc']}`; finished: `{execution['finished_utc']}` (UTC).",
        f"Python: `{manifest['python']}`; packages: `{json.dumps(manifest['versions'], sort_keys=True)}`.",
        "All numerical libraries used one thread.",
        "The experiment used stored configuration responses and performed no new GDP or NLP solves.",
        "All 1,470 planned jobs passed the original checks and the wrapper audit, with no missing or duplicate results.",
        "",
        "| Cohort | Target hits | Published target hits |",
        "| --- | ---: | ---: |",
    ]
    for key, hits in audit["hits"].items():
        prior = audit["published_hits"].get(
            key, 74 if key in ("ranked", "ranked_random") else None
        )
        lines.append(
            f"| {key} | {hits}/{210 if key.startswith('grid') else 140} | {prior} |"
        )
    lines += [
        "",
        "The published primary Process baseline used a single descent with 74/140 hits; both previous restart diagnostics also had 74/140 hits.",
        "The checks preserve no repeats, historical replay, the distinct published prefix, non-worsening objectives, retained historical hits, and matching first descents.",
        f"Original return: `evidence/{archive['name']}` ({archive['bytes']} bytes).",
        f"SHA256: `{archive['sha256']}`; ZIP CRC validation passed.",
        "",
        "Reproduce on Dantzig from the pinned worktree:",
        "",
        "```bash",
        f"export DSDA_PYTHON={REPO}/.venv-dantzig/bin/python",
        "bash experiments/dsda_no_revisit/run_dantzig.sh",
        "```",
        "",
        "The original ZIP, checksum, log, and summary files are preserved without modification.",
        "No manuscript, model, optimizer, or previous result was changed.",
    ]
    (destination / "README.md").write_text("\n".join(lines) + "\n")


def run_a():
    if saved("A")["state"] == "validated":
        return
    worktree = prepare("A")
    expected_destination = (
        worktree
        / "results"
        / ("dsda_no_revisit_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d"))
    )
    require(
        not expected_destination.exists(),
        "The unchanged A launcher would overwrite an existing dated result directory; execution refused",
    )
    require(
        not saved("A").get("execution_started"),
        "A was already launched; inspect its preserved records before any new attempt",
    )
    python = REPO / ".venv-dantzig/bin/python"
    versions = environment(python, ["numpy", "pandas", "scipy"])
    cpus = acquire_cpus("A", 1)
    output = REPO.parent / ("dsda_no_revisit_output_" + stamp())
    log = STATE / ("A_launcher_" + stamp() + ".log")
    env = {
        **ENV,
        "DSDA_PYTHON": str(python),
        "DSDA_CPU": str(cpus[0]["cpu"]),
        "DSDA_OUTPUT": str(output),
    }
    update(
        "A",
        state="running",
        execution_started=True,
        started_utc=now(),
        output=str(output),
        cpus=cpus,
        environment=versions,
        log=str(log),
    )
    execution = foreground(["bash", SCRIPT["A"]], worktree, env, log, allocation="A")
    update("A", state="checking", execution=execution)
    require(
        execution["exit_code"] == 0,
        "A launcher failed; original output and logs are preserved",
    )
    unchanged(worktree, "A")
    with zipfile.ZipFile(
        worktree / "results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip"
    ) as sealed:
        names = [
            n for n in sealed.namelist() if n.endswith("/reproduction/inputs/jobs.json")
        ]
        require(len(names) == 1, "Cannot identify sealed A jobs")
        expected_jobs = json.loads(sealed.read(names[0]))
    audit = audit_a(output, PIN["A"], expected_jobs)
    archive = zip_check(Path(str(output) + ".zip"))
    matches = re.findall(r"^PACKAGED (.+)$", log.read_text(), re.M)
    require(len(matches) == 1, "A packaging destination not identified")
    destination = Path(matches[0])
    require(
        destination.parent == worktree / "results"
        and destination.name.startswith("dsda_no_revisit_"),
        "Unexpected A package destination",
    )
    require(
        sha(destination / "evidence" / archive["name"]) == archive["sha256"],
        "Packaged A ZIP differs",
    )
    require(
        not (destination / "README.md").exists(),
        "A README already exists; do not overwrite",
    )
    no_secret_files(
        [destination / "evidence" / archive["name"], Path(str(output) + ".log")]
    )
    write(destination / "wrapper_validation.json", audit)
    write(
        destination / "wrapper_execution.json",
        {**execution, "cpus": cpus, "environment": versions, "revision": PIN["A"]},
    )
    readme_a(destination, execution, audit, read(output / "manifest.json"), archive)
    update(
        "A",
        state="validated",
        validation=audit,
        result_directory=str(destination),
        archive=archive,
    )
    pack_return("A", destination)


def find_gams():
    value = os.environ.get("GAMS_EXE") or shutil.which("gams")
    if not value:
        candidates = set()
        for base in (
            Path("/opt/gams"),
            Path("/usr/local/gams"),
            Path.home() / "gams",
            Path("/local/scratch/a/lee4382"),
        ):
            if base.is_dir():
                for pattern in ("gams", "*/gams", "gams*/*/gams", "gams*/gams"):
                    candidates.update(
                        p.resolve()
                        for p in base.glob(pattern)
                        if p.is_file() and os.access(p, os.X_OK)
                    )
        require(
            len(candidates) == 1,
            "GAMS_EXE is not set and a unique installed GAMS executable could not be identified; export its absolute path and retry RUN_B.sh",
        )
        value = str(candidates.pop())
    path = Path(value).resolve()
    require(path.is_file() and os.access(path, os.X_OK), "GAMS_EXE is not executable")
    return path


def b_environment():
    paths = dict(
        DFO_PYTHON=str(REPO / ".venv-dantzig-nlp-overnight/bin/python"),
        FMQA_PYTHON=str(REPO / ".venv-dantzig-fmqa-qhd/bin/python"),
        MIDFO_PYTHON=str(REPO / ".venv-mi-dfo/bin/python"),
        COIN_BIN=str(REPO / ".venv-dantzig/bin"),
        BAM_LICENSE_FILE="/local/scratch/a/lee4382/bamlice.txt",
    )
    versions = {
        key: environment(paths[key], packages)
        for key, packages in [
            ("DFO_PYTHON", ["numpy", "pandas", "rbfopt", "bam-solver", "pytest"]),
            ("FMQA_PYTHON", ["numpy", "torch", "dimod", "dwave-samplers", "pytest"]),
            (
                "MIDFO_PYTHON",
                ["numpy", "scipy", "pandas", "PyNomadBBO", "soogo", "pytest"],
            ),
        ]
    }
    require(
        Path(paths["BAM_LICENSE_FILE"]).is_file()
        and Path(paths["BAM_LICENSE_FILE"]).stat().st_size > 0,
        "BAM license is missing; it will not be installed or changed",
    )
    for name in ("bonmin", "ipopt"):
        require(
            os.access(Path(paths["COIN_BIN"]) / name, os.X_OK), name + " is missing"
        )
    paths["GAMS_EXE"] = str(find_gams())
    return {**ENV, **paths}, versions


def gams_probe(worktree, env, directory):
    # Separate preflight only: the known accepted pilot configuration, unchanged model/init.
    gams = env["GAMS_EXE"]
    banner = subprocess.run(
        [gams], cwd=directory, env=env, capture_output=True, text=True, timeout=30
    )
    match = re.search(
        r"\bGAMS(?:\s+Release[: ]*)?\s+(\d+\.\d+(?:\.\d+)?)",
        banner.stdout + "\n" + banner.stderr,
        re.I,
    )
    require(
        match and int(match[1].split(".")[0]) >= 54,
        "GAMS 54+ could not be verified; no live campaign started",
    )
    model = worktree / "gdp_models/catalytic_distillation"
    command = [
        gams,
        str(model / "solve_configuration.gms"),
        *[
            f"--{k}={v}"
            for k, v in zip(("f1", "c1", "c2", "c3", "f2", "b"), (7, 8, 11, 16, 16, 20))
        ],
        "--solver=conopt",
        "--model=" + str(model / "distillation_model_corrected.gms"),
        "--init=" + str(model / "init"),
        "--out=probe_result.txt",
        "curDir=" + str(directory),
        "lo=0",
        "threads=1",
    ]
    execution = foreground(
        command,
        directory,
        env,
        directory / "probe_private.log",
        cpu=0,
        timeout=300,
        allocation="B",
    )
    require(
        execution["exit_code"] == 0 and (directory / "probe_result.txt").is_file(),
        "GAMS-CONOPT corrected-model preflight failed; private log preserved",
    )
    values = dict(
        re.findall(r"(\w+)=(\S+)", (directory / "probe_result.txt").read_text())
    )
    require(
        values.get("solvestat") == "1" and values.get("modelstat") in ("1", "2"),
        "CONOPT did not normally complete an accepted corrected-model preflight solve",
    )
    text = "\n".join(p.read_text(errors="replace") for p in directory.glob("*.lst"))
    conopt = re.search(
        r"\bCONOPT(?:\s*4)?\s+version\s*:?\s*(\d+\.\d+[\w.]*)", text, re.I
    ) or re.search(r"\bCONOPT\s+(\d+\.\d+[\w.]*)", text, re.I)
    require(
        conopt,
        "CONOPT version could not be established from the preserved listing; no campaign started",
    )
    return dict(
        gams_version=match[1],
        conopt_version=conopt[1],
        gams_executable=gams,
        gams_sha256=sha(gams),
        modelstat=values["modelstat"],
        solvestat=values["solvestat"],
        objective=float(values["zobj"]),
        preflight_only=True,
    )


def preflight_b(worktree, env):
    # The professor's end-to-end test explicitly requests CPU 0; never rewrite it.
    acquire_cpus("B", 1, "0")
    directory = STATE / ("B_preflight_" + stamp())
    directory.mkdir()
    version = gams_probe(worktree, env, directory)
    # The original launcher adds -q; two -v flags retain per-test PASSED lines.
    test_env = {**env, "PYTEST_ADDOPTS": "-vv -rs", "PY_COLORS": "0", "NO_COLOR": "1"}
    execution = foreground(
        ["bash", SCRIPT["B"], "test"],
        worktree,
        test_env,
        directory / "test.log",
        cpu=0,
        allocation="B",
    )
    require(execution["exit_code"] == 0, "B preflight failed; no campaign started")
    text = (directory / "test.log").read_text()
    required = [
        "test_gap_coordinates_map_the_admissible_configurations",
        "test_shared_starts_are_reproducible_admissible_and_span_the_space",
        "test_oracle_charges_every_callback_and_solves_each_point_once[uniform]",
        "test_oracle_charges_every_callback_and_solves_each_point_once[dsda]",
        "test_oracle_rejects_a_changed_initial_order",
        "test_mixed_integer_adapters_run_on_live_responses[nomad-PyNomad]",
        "test_mixed_integer_adapters_run_on_live_responses[miso-soogo]",
        "test_surrogate_methods_run_on_live_oracle[bam-bam]",
        "test_surrogate_methods_run_on_live_oracle[fmqa_sa-torch]",
        "test_worker_solves_live_configurations",
    ]
    passed = sorted(set(re.findall(r"::([^\s]+)\s+PASSED", text)))
    require(
        set(required) <= set(passed),
        "Required B tests missing/skipped: " + str(sorted(set(required) - set(passed))),
    )
    summary = dict(
        passed=True,
        required_tests=required,
        passed_tests=passed,
        versions=version,
        execution=execution,
        skipped_lines=[line for line in text.splitlines() if "SKIPPED" in line],
        private_log_directory=str(directory),
    )
    write(directory / "summary.json", summary)
    release_cpus("B")
    return summary


def wait_controller(pid, ticks, which, output):
    observed = set()
    startup = dict(
        controller_present=True,
        worker_affinity_verified=False,
        log_grew=False,
        first_result=None,
    )
    log = output / "controller.log"
    initial_size = log.stat().st_size if log.exists() else 0
    while True:
        try:
            ended, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            ended, status = (0, 0)
            if identity(pid) != ticks:
                return None
        if ended:
            return os.waitstatus_to_exitcode(status)
        for child in Path("/proc").iterdir():
            if not child.name.isdigit() or child.name in observed:
                continue
            try:
                command = (child / "cmdline").read_bytes().replace(b"\0", b" ").decode()
                if str(output) in command and " worker " in command:
                    affinity = sorted(os.sched_getaffinity(int(child.name)))
                    require(
                        len(affinity) == 1, "B child worker affinity is not one CPU"
                    )
                    record = dict(
                        pid=int(child.name), affinity=affinity, observed_utc=now()
                    )
                    with (STATE / "B_worker_observations.jsonl").open("a") as stream:
                        stream.write(json.dumps(record) + "\n")
                    observed.add(child.name)
                    startup["worker_affinity_verified"] = True
            except (OSError, UnicodeDecodeError):
                pass
        if log.exists() and log.stat().st_size > initial_size:
            startup["log_grew"] = True
        if startup["first_result"] is None:
            first = next((output / "runs").glob("*/result.json"), None)
            if first:
                read(first)
                startup["first_result"] = str(first)
        if startup != saved(which).get("startup_checks"):
            update(which, startup_checks=dict(startup))
        time.sleep(5)


def collect_status():
    supervisor = (
        read(STATE / "supervisor.json") if (STATE / "supervisor.json").exists() else {}
    )
    if alive(supervisor) or not STATE.exists():
        return
    archive = ROOT / ("RETURN_STATUS_" + stamp() + ".zip")
    require(not archive.exists(), "Status archive already exists")
    included, withheld = [], []
    for path in sorted(STATE.rglob("*")):
        if (
            not path.is_file()
            or path.suffix not in (".json", ".jsonl", ".log")
            or "private" in path.name
        ):
            continue
        try:
            no_secret_files([path])
            included.append(path)
        except RuntimeError:
            withheld.append(str(path.relative_to(STATE)))
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for path in included:
            out.write(path, str(Path("state") / path.relative_to(STATE)))
        out.writestr("withheld_files.json", json.dumps(withheld, indent=2) + "\n")
    audit = zip_check(archive)
    archive.with_suffix(".zip.sha256").write_text(
        audit["sha256"] + "  " + archive.name + "\n"
    )
    print("STATUS_ARCHIVE=" + str(archive))


def run_b():
    if saved("B")["state"] in (
        "validated",
        "finished_with_failures",
        "archive_too_large",
    ):
        return
    worktree = prepare("B")
    env, versions = b_environment()
    update("B", state="preflight", environment=versions)
    previous = saved("B")
    if previous.get("preflight", {}).get("passed"):
        preflight = previous["preflight"]
    else:
        preflight = preflight_b(worktree, env)
    unchanged(worktree, "B")
    requested = int(os.environ.get("CATDIST_WORKERS", "16"))
    require(1 <= requested <= 16, "CATDIST_WORKERS must be between 1 and 16")
    cpus = acquire_cpus("B", requested, os.environ.get("CPUS"))
    output = Path(
        previous.get("output", str(worktree / "results/catalytic_distillation_live"))
    )
    require(
        previous.get("output") or not output.exists(),
        "B output already exists outside this package; nothing overwritten",
    )
    require(
        not alive(previous.get("controller", {})),
        "B controller already alive; duplicate run refused",
    )
    # Also detect a controller without a usable saved PID.
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            cmd = path.read_bytes().replace(b"\0", b" ")
            require(
                not (str(output).encode() in cmd and b"run.py run " in cmd),
                "A controller for this output is already running",
            )
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            pass
    env.update(
        CPUS=",".join(str(r["cpu"]) for r in cpus),
        CATDIST_WORKERS=str(len(cpus)),
        CATDIST_OUTPUT=str(output),
    )
    log = STATE / ("B_start_" + stamp() + ".log")
    update(
        "B",
        state="starting",
        output=str(output),
        cpus=cpus,
        preflight=preflight,
        environment=versions,
        started_utc=now(),
    )
    execution = foreground(["bash", SCRIPT["B"], "run"], worktree, env, log)
    require(execution["exit_code"] == 0, "B launcher failed")
    found = re.search(r"Controller PID (\d+)", log.read_text())
    require(found, "B controller PID not returned")
    pid = int(found[1])
    hold_process("B", pid)
    controller = dict(
        pid=pid,
        start_ticks=identity(pid),
        started_utc=now(),
        log=str(output / "controller.log"),
    )
    require(
        alive(controller),
        "B controller exited before startup confirmation; inspect its log",
    )
    update("B", state="running", controller=controller, launch_execution=execution)
    exit_code = wait_controller(pid, controller["start_ticks"], "B", output)
    update("B", state="checking", finished_utc=now(), controller_exit_code=exit_code)
    require(exit_code in (0, None), f"B controller terminated abnormally: {exit_code}")
    unchanged(worktree, "B")
    audit = audit_b(output)
    model = worktree / "gdp_models/catalytic_distillation"
    require(
        audit["cache_provenance"]["model_sha256"]
        == sha(model / "distillation_model_corrected.gms")
        and audit["cache_provenance"]["init_sha256"] == sha(model / "init.gdx")
        and audit["cache_provenance"]["solver"] == "conopt",
        "B cache provenance changed",
    )
    collect = foreground(
        ["bash", SCRIPT["B"], "collect"],
        worktree,
        env,
        STATE / ("B_collect_" + stamp() + ".log"),
    )
    require(collect["exit_code"] == 0, "B collection failed; original results retained")
    matched = re.findall(
        r"^Please send back: (.+)$", Path(collect["log"]).read_text(), re.M
    )
    require(len(matched) == 1, "B original ZIP not identified")
    archive_path = Path(matched[0])
    archive = zip_check(archive_path)
    audit = audit_b_summary(output, audit)
    write(STATE / "B_validation.json", audit)
    archive_path.with_suffix(".zip.sha256").write_text(
        archive["sha256"] + "  " + archive_path.name + "\n"
    )
    update("B", validation=audit, original_archive=str(archive_path), archive=archive)
    if archive["bytes"] > 90_000_000:
        update(
            "B",
            state="archive_too_large",
            publication_blocked=True,
            reason="Original ZIP exceeds 90,000,000 bytes; preserve it on the server without deletion, splitting, or LFS conversion",
        )
        return
    no_secret_files([archive_path])
    destination = (
        worktree
        / "results"
        / (
            "catalytic_distillation_live_"
            + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
        )
    )
    require(
        not destination.exists(),
        "B result publication directory exists; nothing overwritten",
    )
    (destination / "evidence").mkdir(parents=True)
    shutil.copy2(archive_path, destination / "evidence" / archive_path.name)
    shutil.copy2(
        archive_path.with_suffix(".zip.sha256"),
        destination / "evidence" / (archive_path.name + ".sha256"),
    )
    for name in ("runs.csv", "conditions.csv", "best_known.json"):
        shutil.copy2(output / name, destination / name)
    write(destination / "wrapper_validation.json", audit)
    write(destination / "wrapper_execution.json", saved("B"))
    state = saved("B")
    lines = [
        "# Dantzig live-NLP catalytic distillation results",
        "",
        f"Execution revision: `{PIN['B']}`.",
        f"Host: `{platform.node()}`; workers: {len(cpus)}; CPUs: `{env['CPUS']}`.",
        f"Started: `{state['started_utc']}`; finished: `{state['finished_utc']}` (UTC).",
        f"GAMS/CONOPT: `{json.dumps(preflight['versions'], sort_keys=True)}`.",
        f"Python environments: `{json.dumps(versions, sort_keys=True)}`.",
        "Every numeric worker used one thread and one logical CPU on a distinct observed idle physical core.",
        f"Planned runs: 210; completed: {audit['completed']}; result failures: {audit['result_failures']}; worker failures: {audit['worker_failures']}; worker timeouts: {audit['worker_timeouts']}; missing: 0; duplicates: 0.",
        "Execution failures and timeouts remain in the planned denominator of ten seeds per method-budget condition.",
        f"Best-known objective: `{audit['best_known']['objective']}` at positions `{audit['best_known']['positions']}`.",
        "Best-known means the best accepted observed value from this campaign or the specified same-protocol pilot, not a global optimum or a proven lower bound.",
        f"Unique cache entries: {audit['unique_cached_configurations']}; recorded NLP calls: {audit['recorded_nlp_calls']}; exact total identifiable: {audit['nlp_call_count_exact']}.",
        audit["cache_note"],
        "Preflight solves use separate temporary data and are excluded from campaign statistics.",
        f"Original ZIP: `evidence/{archive_path.name}`; bytes: {archive['bytes']}; SHA256: `{archive['sha256']}`; CRC passed.",
        "",
        "| Method | Budget | Planned | Result files | Completed | Hits |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in audit["conditions"]:
        lines.append(
            f"| {r['method']} | {r['budget']} | 10 | {r['results']} | {r['completed']} | {r['hits']} |"
        )
    lines += [
        "",
        "Reproduce from the pinned worktree with the existing environments:",
        "",
        "```bash",
    ]
    for key in (
        "DFO_PYTHON",
        "FMQA_PYTHON",
        "MIDFO_PYTHON",
        "COIN_BIN",
        "BAM_LICENSE_FILE",
        "GAMS_EXE",
    ):
        lines.append(f"export {key}='{env[key]}'")
    lines += [
        "bash experiments/catalytic_distillation_live/run_dantzig.sh test",
        "bash experiments/catalytic_distillation_live/run_dantzig.sh run",
        "bash experiments/catalytic_distillation_live/run_dantzig.sh status",
        "bash experiments/catalytic_distillation_live/run_dantzig.sh collect",
        "```",
        "",
        "The original model, configuration, cache policy, optimizer settings, and native statuses remain unchanged.",
        "Only this packaged result directory is intended for the PR; the working output, environment, and license files must not be staged.",
    ]
    (destination / "README.md").write_text("\n".join(lines) + "\n")
    update(
        "B",
        state="finished_with_failures"
        if audit["result_failures"] or audit["worker_failures"]
        else "validated",
        result_directory=str(destination),
    )
    pack_return("B", destination)


def status():
    supervisor = (
        read(STATE / "supervisor.json") if (STATE / "supervisor.json").exists() else {}
    )
    print(
        "SUPERVISOR_ALIVE="
        + str(alive(supervisor))
        + "; PID="
        + str(supervisor.get("pid"))
    )
    configuration = (
        read(ROOT / "PACKAGE_CONFIG.json")
        if (ROOT / "PACKAGE_CONFIG.json").exists()
        else {}
    )
    for which in [configuration["task"]] if configuration else ("A", "B"):
        data = saved(which)
        print(
            f"{which}: STATE={data['state']}; revision={data.get('revision')}; log={data.get('log') or data.get('controller', {}).get('log')}"
        )
        if data.get("output"):
            output = Path(data["output"])
            statuses = {}
            for p in (output / "runs").glob("*/result.json"):
                try:
                    value = read(p)["status"]
                    statuses[value] = statuses.get(value, 0) + 1
                except (ValueError, KeyError):
                    pass
            print(
                f"  results={sum(statuses.values())}/{1470 if which == 'A' else 210}; statuses={json.dumps(statuses)}; output={output}"
            )
        for key in ("error", "return_archive", "return_sha256", "original_archive"):
            if key in data:
                print(f"  {key}={data[key]}")
        if data.get("controller"):
            print("  controller_alive=" + str(alive(data["controller"])))
        if data.get("cpus"):
            print("  cores=" + json.dumps(data["cpus"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["launch", "supervise", "status", "collect"])
    parser.add_argument("task", nargs="?", choices=["A", "B", "all"], default="all")
    parser.add_argument("--lock-fd", type=int)
    args = parser.parse_args()
    configuration = (
        read(ROOT / "PACKAGE_CONFIG.json")
        if (ROOT / "PACKAGE_CONFIG.json").exists()
        else {}
    )
    if configuration:
        if args.task == "all":
            args.task = configuration["task"]
        require(
            args.task == configuration["task"],
            "This ZIP is restricted to task " + configuration["task"],
        )
    if args.mode == "status":
        status()
        return
    if args.mode == "collect":
        status()
        collect_status()
        print(
            "Completed result returns are generated automatically; private GAMS listings and running campaigns are not collected."
        )
        return
    host_guard()
    STATE.mkdir(exist_ok=True)
    if args.mode == "launch":
        lock = (STATE / "supervisor.lock").open("a+")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A package supervisor is already running; use STATUS.sh.")
            return
        log = STATE / ("supervisor_" + stamp() + ".log")
        with log.open("a") as stream:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__)),
                    "supervise",
                    args.task,
                    "--lock-fd",
                    str(lock.fileno()),
                ],
                env=ENV,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                pass_fds=(lock.fileno(),),
            )
        write(
            STATE / "supervisor.json",
            dict(
                pid=process.pid,
                start_ticks=identity(process.pid),
                log=str(log),
                task=args.task,
                started_utc=now(),
            ),
        )
        lock.close()
        print(f"SUPERVISOR_STARTED PID={process.pid}; LOG={log}")
        return
    require(args.lock_fd is not None, "Supervisor must be started through launch")
    # Adopt the unchanged shell launcher's nohup controller to record its real exit code.
    require(
        ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0,
        "Cannot enable controller exit-code supervision",
    )
    for which in ("A", "B") if args.task == "all" else (args.task,):
        try:
            (run_a if which == "A" else run_b)()
        except Exception as error:
            message = str(error)
            update(which, state="blocked_or_failed", error=message)
            print(traceback.format_exc(), flush=True)
            print(
                "No result is marked verified or published for this failed stage.",
                flush=True,
            )
            break
        finally:
            release_cpus(which)
    print("Supervisor finished.", flush=True)


if __name__ == "__main__":
    main()
