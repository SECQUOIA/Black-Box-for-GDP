"""Conservative, read-only CPU 2 and SMT occupancy check before launch."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import time

CPU = 2
MAX_INTERVAL_BUSY_PERCENT = 5.0
MAX_WINDOW_BUSY_PERCENT = 2.0
BACKGROUND_EXECUTABLES = frozenset({"/opt/microsoft/mdatp/sbin/wdavdaemon"})
COMPUTE = re.compile(
    r"python|gams|scip|bonmin|ipopt|baron|matlab|julia|torch|bam|Rscript", re.I
)


def cpulist(text):
    result = set()
    for part in text.strip().split(","):
        if "-" in part:
            first, last = map(int, part.split("-"))
            result.update(range(first, last + 1))
        elif part:
            result.add(int(part))
    return result


def load_checked_background(process, online_cpus):
    """Known unrestricted OS activity is still charged to both CPU load caps."""
    command = process["command"].split(maxsplit=1)
    return bool(
        command
        and command[0] in BACKGROUND_EXECUTABLES
        and online_cpus is not None
        and set(process["allowed"]) == set(online_cpus)
    )


def cpu_times(siblings):
    result = {}
    for line in Path("/proc/stat").read_text().splitlines():
        fields = line.split()
        if fields and fields[0] in {f"cpu{n}" for n in siblings}:
            values = list(map(int, fields[1:]))
            result[int(fields[0][3:])] = (sum(values[:8]), values[3] + values[4])
    if set(result) != set(siblings):
        raise RuntimeError("Cannot read both logical CPUs of the physical core")
    return result


def ancestors():
    result, pid = set(), os.getpid()
    while pid > 0 and pid not in result:
        result.add(pid)
        text = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        pid = int(text[1])
    return result


def processes(siblings, excluded):
    result, unknown = {}, []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit() or int(path.name) in excluded:
            continue
        try:
            command = (
                (path / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode(errors="replace")
                .strip()
            )
            for task in (path / "task").iterdir():
                try:
                    fields = (task / "stat").read_text().rsplit(")", 1)[1].split()
                    status = dict(
                        line.split(":", 1)
                        for line in (task / "status").read_text().splitlines()
                        if ":" in line
                    )
                    allowed = cpulist(status["Cpus_allowed_list"])
                    if allowed & set(siblings):
                        result[task.name] = dict(
                            pid=int(path.name),
                            tid=int(task.name),
                            command=command,
                            state=fields[0],
                            ticks=int(fields[11]) + int(fields[12]),
                            start_ticks=int(fields[19]),
                            last_cpu=int(fields[36]),
                            allowed=sorted(allowed),
                        )
                except (FileNotFoundError, ProcessLookupError):
                    continue
                except (PermissionError, KeyError) as error:
                    unknown.append(
                        {"pid": path.name, "task": task.name, "error": str(error)}
                    )
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            unknown.append({"pid": path.name, "error": str(error)})
    return result, unknown


def decide(
    siblings, samples, process_samples, unknown, scheduler_blockers, online_cpus=None
):
    blockers = list(scheduler_blockers)
    if unknown:
        blockers.append("Some process affinity/activity could not be inspected")
    loads = []
    for previous, current in zip(samples, samples[1:]):
        interval = {}
        for cpu in siblings:
            total = current[cpu][0] - previous[cpu][0]
            idle = current[cpu][1] - previous[cpu][1]
            if total <= 0:
                blockers.append(f"No CPU accounting interval for CPU {cpu}")
                continue
            interval[cpu] = 100 * (total - idle) / total
            if not 0 <= idle <= total:
                blockers.append(f"Invalid CPU accounting for CPU {cpu}")
            if interval[cpu] > MAX_INTERVAL_BUSY_PERCENT:
                blockers.append(
                    f"CPU {cpu} busy {interval[cpu]:.2f}% during a sample interval"
                )
        loads.append(interval)
    for cpu in siblings:
        total = samples[-1][cpu][0] - samples[0][cpu][0]
        idle = samples[-1][cpu][1] - samples[0][cpu][1]
        if total <= 0 or not 0 <= idle <= total:
            blockers.append(f"Invalid full-window CPU accounting for CPU {cpu}")
        elif 100 * (total - idle) / total > MAX_WINDOW_BUSY_PERCENT:
            blockers.append(
                f"CPU {cpu} busy {100 * (total - idle) / total:.2f}% over the complete observation window"
            )
    for group in process_samples:
        for p in group.values():
            if not set(p["allowed"]) & set(siblings):
                continue
            constrained = (
                set(p["allowed"]) != set(online_cpus)
                if online_cpus is not None
                else len(p["allowed"]) <= 8
            )
            if COMPUTE.search(p["command"]) and constrained:
                blockers.append(
                    f"Existing compute process/thread {p['pid']}/{p['tid']} has constrained affinity overlapping this core"
                )
            if (
                p.get("state") == "R"
                and p["last_cpu"] in siblings
                and not load_checked_background(p, online_cpus)
            ):
                blockers.append(
                    f"Running process/thread {p['pid']}/{p['tid']} observed on CPU {p['last_cpu']}"
                )
    for previous, current in zip(process_samples, process_samples[1:]):
        for tid, p in current.items():
            old = previous.get(tid)
            if (
                old
                and p["start_ticks"] == old["start_ticks"]
                and p["ticks"] > old["ticks"]
            ):
                if load_checked_background(p, online_cpus) and load_checked_background(
                    old, online_cpus
                ):
                    continue
                if p["last_cpu"] in siblings or old["last_cpu"] in siblings:
                    blockers.append(
                        f"Active process/thread {p['pid']}/{tid} observed on this core"
                    )
                elif COMPUTE.search(p["command"]) and online_cpus is None:
                    blockers.append(
                        f"Active process/thread {p['pid']}/{tid} affinity cannot be classified without the online CPU set"
                    )
    return sorted(set(blockers)), loads


def inspect():
    if os.name != "posix" or not Path("/proc/stat").exists():
        raise RuntimeError("CPU 2 availability requires Dantzig Linux /proc inspection")
    allowed = sorted(os.sched_getaffinity(0))
    if CPU not in allowed:
        raise RuntimeError(
            "CPU 2 is outside the permitted CPU set; no alternative CPU selected"
        )
    topology = Path(f"/sys/devices/system/cpu/cpu{CPU}/topology")
    siblings = sorted(cpulist((topology / "thread_siblings_list").read_text()))
    online = cpulist(Path("/sys/devices/system/cpu/online").read_text())
    if not set(siblings) <= online:
        raise RuntimeError("CPU 2 or an SMT sibling is offline/unknown")
    schedulers = {
        name: shutil.which(name) for name in ("squeue", "scontrol", "qstat", "bjobs")
    }
    allocation = {
        k: os.environ[k]
        for k in ("SLURM_JOB_ID", "SLURM_CPUS_ON_NODE", "PBS_JOBID", "LSB_JOBID")
        if k in os.environ
    }
    scheduler_blockers = []
    allocation_record = None
    if any(schedulers.values()):
        if "SLURM_JOB_ID" in allocation and schedulers["scontrol"]:
            command = [
                schedulers["scontrol"],
                "show",
                "job",
                allocation["SLURM_JOB_ID"],
            ]
        elif "PBS_JOBID" in allocation and schedulers["qstat"]:
            command = [schedulers["qstat"], "-f", allocation["PBS_JOBID"]]
        elif "LSB_JOBID" in allocation and schedulers["bjobs"]:
            command = [schedulers["bjobs"], "-l", allocation["LSB_JOBID"]]
        else:
            command = None
            scheduler_blockers.append(
                "Scheduler detected without an inspectable current allocation"
            )
        if command:
            check = subprocess.run(command, capture_output=True, text=True, timeout=20)
            allocation_record = dict(
                command=command,
                returncode=check.returncode,
                stdout=check.stdout,
                stderr=check.stderr,
            )
            if check.returncode:
                scheduler_blockers.append("Scheduler allocation inspection failed")
            # Do not infer which physical cores are assigned from generic job text.
            if CPU not in allowed or len(allowed) == len(online):
                scheduler_blockers.append(
                    "Scheduler CPU allocation is not independently constrained by affinity"
                )
    excluded = ancestors()
    samples, process_samples, unknown, sample_times = [], [], [], []
    for i in range(7):
        if i:
            time.sleep(2)
        sample_times.append(time.time())
        samples.append(cpu_times(siblings))
        current, missing = processes(siblings, excluded)
        process_samples.append(current)
        unknown.extend(missing)
    blockers, loads = decide(
        siblings,
        samples,
        process_samples,
        unknown,
        scheduler_blockers,
        online_cpus=online,
    )
    ps = subprocess.run(
        ["ps", "-eo", "pid,ppid,psr,pcpu,stat,comm,args", "--sort=-pcpu"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if ps.returncode:
        blockers.append("Full process listing failed")
    return dict(
        cpu=CPU,
        allowed_before_pin=allowed,
        online_cpus=sorted(online),
        siblings=siblings,
        physical_package_id=(topology / "physical_package_id").read_text().strip(),
        core_id=(topology / "core_id").read_text().strip(),
        sample_times=sample_times,
        cpu_accounting_samples=samples,
        busy_percent_by_interval=loads,
        busy_percent_over_window={
            cpu: 100
            * (
                1
                - (samples[-1][cpu][1] - samples[0][cpu][1])
                / (samples[-1][cpu][0] - samples[0][cpu][0])
            )
            for cpu in siblings
            if samples[-1][cpu][0] > samples[0][cpu][0]
        },
        thresholds={
            "maximum_interval_busy_percent": MAX_INTERVAL_BUSY_PERCENT,
            "maximum_window_busy_percent": MAX_WINDOW_BUSY_PERCENT,
        },
        process_samples=process_samples,
        background_services_assessed_by_load=list(
            {
                (p["pid"], p["tid"]): p
                for group in process_samples
                for p in group.values()
                if load_checked_background(p, online)
            }.values()
        ),
        inspection_errors=unknown,
        schedulers=schedulers,
        allocation=allocation,
        allocation_record=allocation_record,
        process_listing=ps.stdout,
        process_listing_status=ps.returncode,
        permitted_to_start=not blockers and ps.returncode == 0,
        blockers=blockers,
        policy="Seven samples over at least 12 seconds; each core sibling <=5% in every interval and <=2% over the full window, including wdavdaemon activity; the exact wdavdaemon executable with unrestricted online-CPU affinity is assessed by these load caps; constrained compute affinity and observed activity from other tasks block launch; affinity is not exclusive reservation.",
    )
