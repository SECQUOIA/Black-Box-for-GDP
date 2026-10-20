"""Provenance and external process limits for the bounded diagnostics."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

ROOT = Path(
    os.environ.get("RBFOPT_DIAGNOSTICS_REPO", Path(__file__).resolve().parents[1])
).resolve()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def environment():
    versions = {}
    for name in ("numpy", "torch", "dimod", "dwave-samplers", "pyomo", "scipy"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "versions": versions,
    }


def bounded(command, log, seconds):
    """Kill the entire child process group at the external wall-clock limit."""
    started = time.monotonic()
    with Path(log).open("w") as stream:
        child = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        timed_out = False
        try:
            code = child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait()
    return {
        "command": command,
        "returncode": code,
        "timed_out": timed_out,
        "wall_s": time.monotonic() - started,
        "external_wall_limit_s": seconds,
    }


def outputs(directory):
    return {
        str(p.relative_to(directory)): sha(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
