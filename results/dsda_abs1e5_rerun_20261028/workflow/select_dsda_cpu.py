#!/usr/bin/env python3
"""Select an idle allowed logical CPU, then pin and execute one D-SDA command."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import unittest


THREADS = {
    name: "1"
    for name in (
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
THREADS.update(OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE", CUDA_VISIBLE_DEVICES="")


def cpu_list(text):
    result = set()
    for item in text.strip().split(","):
        if not item:
            continue
        if "-" in item:
            lo, hi = map(int, item.split("-", 1))
            result.update(range(lo, hi + 1))
        else:
            result.add(int(item))
    return result


def parse_ticks(text, allowed):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields or not fields[0].startswith("cpu") or not fields[0][3:].isdigit():
            continue
        cpu = int(fields[0][3:])
        if cpu not in allowed:
            continue
        values = list(map(int, fields[1:]))
        if len(values) < 8:
            raise RuntimeError("Incomplete /proc/stat accounting")
        # Guest time is already included in user/nice; never count it twice.
        result[cpu] = (sum(values[:8]), values[3] + values[4])
    if set(result) != set(allowed):
        raise RuntimeError("Some allowed CPUs have no readable accounting")
    return result


def utilization(samples):
    result = {cpu: [] for cpu in samples[0]}
    for previous, current in zip(samples, samples[1:]):
        for cpu in result:
            total = current[cpu][0] - previous[cpu][0]
            idle = current[cpu][1] - previous[cpu][1]
            if total <= 0 or not 0 <= idle <= total:
                raise RuntimeError(
                    "Invalid CPU accounting interval for CPU " + str(cpu)
                )
            result[cpu].append(100.0 * (total - idle) / total)
    return result


def choose_cpu(loads, siblings, preferred=2, max_busy=5.0, allowed=None):
    allowed = set(loads) if allowed is None else set(allowed)
    candidates = [
        cpu
        for cpu, values in loads.items()
        if cpu in allowed and values and max(values) <= max_busy
    ]
    if not candidates:
        return None
    if preferred in candidates:
        return preferred

    # A fully idle physical core wins over an idle SMT thread on a busy core.
    # If only the latter is available, it remains usable and is reported as such.
    def rank(cpu):
        group = siblings.get(cpu, {cpu})
        whole_core_idle = all(s in loads and max(loads[s]) <= max_busy for s in group)
        return (
            not whole_core_idle,
            sum(loads[cpu]) / len(loads[cpu]),
            max(loads[cpu]),
            cpu,
        )

    return min(candidates, key=rank)


def select(
    preferred=2, max_busy=5.0, intervals=3, interval_seconds=1.0, wait_seconds=60.0
):
    if platform.system() != "Linux" or not hasattr(os, "sched_getaffinity"):
        raise RuntimeError(
            "CPU selection requires Linux /proc and CPU affinity support"
        )
    allowed = set(os.sched_getaffinity(0))
    if not allowed:
        raise RuntimeError("The current process has no allowed CPU")
    siblings = {}
    for cpu in allowed:
        topology = Path(
            f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list"
        )
        siblings[cpu] = cpu_list(topology.read_text())
    # Also observe SMT siblings outside the allowed set, without selecting them.
    observed = allowed | set().union(*siblings.values())
    started = time.monotonic()
    rounds = []
    while True:
        samples = [parse_ticks(Path("/proc/stat").read_text(), observed)]
        for _ in range(intervals):
            time.sleep(interval_seconds)
            samples.append(parse_ticks(Path("/proc/stat").read_text(), observed))
        loads = utilization(samples)
        selected = choose_cpu(loads, siblings, preferred, max_busy, allowed=allowed)
        rounds.append(
            dict(
                utc=datetime.now(timezone.utc).isoformat(),
                busy_percent_by_interval=loads,
                selected=selected,
            )
        )
        record = dict(
            allowed_cpus=sorted(allowed),
            selected_cpu=selected,
            threshold_busy_percent=max_busy,
            measurement_intervals=intervals,
            interval_seconds=interval_seconds,
            elapsed_seconds=time.monotonic() - started,
            preferred_cpu=preferred,
            rounds=rounds,
            selection_rule="Every sampled interval must be below or equal to the utilization threshold; use CPU 2 if eligible, otherwise prefer a fully idle physical core.",
            exclusive_reservation=False,
            note="A utilization observation and affinity setting do not reserve a CPU against future competing work.",
        )
        if selected is not None:
            group = siblings[selected]
            record["smt_siblings"] = sorted(group)
            record["smt_sibling_busy_percent"] = {cpu: loads[cpu] for cpu in group}
            record["physical_core_observed_idle"] = all(
                max(loads[cpu]) <= max_busy for cpu in group
            )
            return record
        print(
            "No eligible idle CPU observed; waiting within the configured limit.",
            file=sys.stderr,
            flush=True,
        )
        if time.monotonic() - started >= wait_seconds:
            return record


class SelectionTests(unittest.TestCase):
    def test_cpu_two_is_preferred_when_idle(self):
        self.assertEqual(
            choose_cpu({2: [1, 2, 0], 50: [0, 0, 0]}, {2: {2, 50}, 50: {2, 50}}), 2
        )

    def test_busy_cpu_two_is_rejected(self):
        self.assertEqual(
            choose_cpu({2: [100, 100, 100], 50: [0, 0, 0]}, {2: {2, 50}, 50: {2, 50}}),
            50,
        )

    def test_fully_idle_core_is_preferred(self):
        loads = {2: [90], 50: [0], 3: [1], 51: [1]}
        siblings = {2: {2, 50}, 50: {2, 50}, 3: {3, 51}, 51: {3, 51}}
        self.assertEqual(choose_cpu(loads, siblings), 3)

    def test_one_busy_interval_rejects_candidate(self):
        self.assertIsNone(choose_cpu({2: [0, 6, 0]}, {2: {2}}))

    def test_all_busy_returns_none(self):
        self.assertIsNone(choose_cpu({2: [100], 50: [100]}, {2: {2, 50}, 50: {2, 50}}))

    def test_forbidden_cpu_is_never_selected(self):
        self.assertIsNone(choose_cpu({2: [100], 50: [0]}, {2: {2, 50}}, allowed={2}))

    def test_guest_time_not_double_counted(self):
        parsed = parse_ticks("cpu0 10 2 3 80 5 0 0 0 4 1\n", {0})
        self.assertEqual(parsed, {0: (100, 85)})

    def test_utilization(self):
        self.assertEqual(utilization([{2: (100, 80)}, {2: (200, 175)}]), {2: [5.0]})

    def test_parse_cpu_ranges(self):
        self.assertEqual(cpu_list("0-2,48,50-51"), {0, 1, 2, 48, 50, 51})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Inspect only; do not launch D-SDA"
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--preferred", type=int, default=2)
    parser.add_argument("--max-busy", type=float, default=5.0)
    parser.add_argument("--intervals", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--wait-seconds", type=float, default=60.0)
    parser.add_argument("--record", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SelectionTests)
        return (
            0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
        )
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not args.check and not command:
        parser.error("Use --check or provide the D-SDA command after --")
    if args.check and command:
        parser.error("--check does not execute a command")
    if not math.isfinite(args.max_busy) or not 0 <= args.max_busy < 100:
        parser.error("--max-busy must be finite and in [0,100)")
    if (
        args.intervals < 1
        or not math.isfinite(args.interval_seconds)
        or args.interval_seconds <= 0
    ):
        parser.error("Measurement intervals and duration must be positive")
    if not math.isfinite(args.wait_seconds) or args.wait_seconds < 0:
        parser.error("--wait-seconds must be finite and nonnegative")
    record = select(
        args.preferred,
        args.max_busy,
        args.intervals,
        args.interval_seconds,
        args.wait_seconds,
    )
    record.update(
        command=command, check_only=args.check, numerical_library_threads=THREADS
    )
    selected = record["selected_cpu"]
    if selected is not None and not args.check:
        os.sched_setaffinity(0, {selected})
        effective = sorted(os.sched_getaffinity(0))
        if effective != [selected]:
            raise RuntimeError("Could not pin exactly the selected CPU")
        record["effective_cpus"] = effective
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    report = (
        args.record
        or Path(__file__).resolve().parent
        / "results"
        / f"dsda_cpu_selection_{stamp}_{os.getpid()}.json"
    )
    report = report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print("CPU_SELECTION_RECORD", report, flush=True)
    if selected is None:
        print(
            "No idle allowed CPU found; D-SDA was not started.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    print(
        "SELECTED_CPU",
        selected,
        "SMT_SIBLINGS",
        record["smt_siblings"],
        "PHYSICAL_CORE_IDLE",
        record["physical_core_observed_idle"],
        flush=True,
    )
    if args.check:
        print("Check only; no CPU reserved and no D-SDA started.", flush=True)
        return 0
    environment = {
        **os.environ,
        **THREADS,
        "DSDA_CPU_SELECTION_RECORD": str(report),
        "DSDA_SELECTED_CPU": str(selected),
    }
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    sys.exit(main())
