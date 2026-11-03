"""Bind only the original end-to-end test's CPU argument to the selected core."""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pytest


def bound_arguments(argv, cpu):
    if not 17 <= cpu <= 48:
        raise ValueError("Preflight CPU must be within 17-48")
    result = list(argv)
    if not result or result[0] != "run":
        return result, False
    if result.count("--cpus") != 1:
        raise ValueError("Unexpected preflight run arguments")
    index = result.index("--cpus") + 1
    if index == len(result) or result[index] != "0":
        raise ValueError("Original test no longer requests CPU 0; review required")
    result[index] = str(cpu)
    return result, True


@pytest.fixture(autouse=True)
def selected_preflight_cpu(request, monkeypatch):
    if request.node.name != "test_worker_solves_live_configurations":
        yield
        return
    cpu = int(os.environ["PR57_PREFLIGHT_CPU"])
    destination = Path(os.environ["PR57_PREFLIGHT_CPU_RECORD"])
    if destination.exists():
        raise RuntimeError("Preflight CPU record already exists")
    main = request.module.live.main
    records = []

    def on_selected_cpu(argv):
        arguments, changed = bound_arguments(argv, cpu)
        if not changed:
            return main(argv)
        affinity = sorted(os.sched_getaffinity(0))
        if affinity != [cpu]:
            raise RuntimeError("Preflight parent is not pinned to the selected CPU")
        record = dict(
            original_cpu=0,
            selected_cpu=cpu,
            original_arguments=list(argv),
            executed_arguments=arguments,
            parent_affinity=affinity,
            test_source_sha256=hashlib.sha256(
                Path(request.module.__file__).read_bytes()
            ).hexdigest(),
            started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        records.append(record)
        destination.write_text(json.dumps(record, indent=2) + "\n")
        value = main(arguments)
        record.update(
            returncode=value, finished_utc=dt.datetime.now(dt.timezone.utc).isoformat()
        )
        destination.write_text(json.dumps(record, indent=2) + "\n")
        return value

    monkeypatch.setattr(request.module.live, "main", on_selected_cpu)
    yield
    if len(records) != 1:
        raise RuntimeError("Expected exactly one original end-to-end run")
