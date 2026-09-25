"""Explicit Linux CPU selection and physical-core checks for benchmark runners."""

import argparse
import json
import os
from pathlib import Path


TOPOLOGY_ROOT = Path("/sys/devices/system/cpu")


def pin_cpu(requested=None):
    """Pin this process; forked and exec'd children inherit its affinity."""
    if not hasattr(os, "sched_getaffinity"):
        if requested is not None:
            raise ValueError("Explicit --cpu requires Linux CPU affinity support")
        return None
    allowed = os.sched_getaffinity(0)
    cpu = min(allowed) if requested is None else requested
    if cpu not in allowed:
        raise ValueError(f"CPU {cpu} is not allowed; available CPUs: {sorted(allowed)}")
    os.sched_setaffinity(0, {cpu})
    if os.sched_getaffinity(0) != {cpu}:
        raise RuntimeError(f"Failed to restrict execution to CPU {cpu}")
    return cpu


def cpu_topology(cpu):
    record = {"cpu": cpu}
    if cpu is not None:
        for name in ("physical_package_id", "core_id", "thread_siblings_list"):
            try:
                record[name] = (TOPOLOGY_ROOT / f"cpu{cpu}" / "topology" / name).read_text().strip()
            except OSError:
                record[name] = None
    return record


def affinity_record(cpu):
    return {**cpu_topology(cpu),
            "effective_cpus": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
            "policy": "one logical CPU; not an exclusive reservation"}


def check_cpu_pair(first, second):
    """Fail before launching if CPUs are unavailable or share a physical core."""
    if not hasattr(os, "sched_getaffinity"):
        raise ValueError("CPU-pair checking requires Linux CPU affinity support")
    allowed = os.sched_getaffinity(0)
    if first == second or not {first, second} <= allowed:
        raise ValueError(f"Choose two distinct allowed CPUs; available CPUs: {sorted(allowed)}")
    records = [cpu_topology(cpu) for cpu in (first, second)]
    identities = [(r["physical_package_id"], r["core_id"]) for r in records]
    if any(value in (None, "", "-1") for identity in identities for value in identity):
        raise ValueError("Physical-core topology unavailable; cannot verify CPU separation")
    if identities[0] == identities[1]:
        raise ValueError(f"CPUs {first} and {second} share a physical core; choose another CPU")
    return {"distinct_physical_cores": True, "cpus": records,
            "note": "Affinity does not exclude other users' jobs or shared memory/cache contention"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-pair", type=int, nargs=2, required=True, metavar=("FMQA_CPU", "GDP_CPU"))
    args = parser.parse_args()
    try:
        print(json.dumps(check_cpu_pair(*args.check_pair), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
