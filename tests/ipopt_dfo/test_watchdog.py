"""Real disposable process groups; no solvers or historical data required."""
import importlib
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX session watchdog")


@pytest.fixture(params=["ipopt_dfo_cstr", "ipopt_dfo_non_cstr"])
def runner(request):
    return importlib.import_module(request.param)


@pytest.mark.parametrize("interrupted", [False, True])
def test_cleanup_kills_stubborn_child_after_cooperative_leader_exits(
    runner, tmp_path, monkeypatch, interrupted
):
    heartbeat = tmp_path / "heartbeat"
    ready = tmp_path / "ready"
    child = (
        "import signal, time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"p = Path({str(heartbeat)!r})\n"
        "while True:\n p.write_text(str(time.monotonic_ns()))\n time.sleep(.01)\n"
    )
    worker = (
        "import os, signal, subprocess, sys, time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        f"while not Path({str(heartbeat)!r}).exists(): time.sleep(.01)\n"
        f"Path({str(ready)!r}).write_text(str(os.getpid()))\n"
        "while True: time.sleep(.1)\n"
    )
    original_wait, original_killpg = subprocess.Popen.wait, os.killpg
    original_stop = runner._stop_process_group
    signals = []
    first_wait = True

    def wait(process, timeout=None):
        nonlocal first_wait
        if first_wait:
            first_wait = False
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert ready.exists(), "Disposable worker failed to start"
            if interrupted:
                raise KeyboardInterrupt
            raise subprocess.TimeoutExpired(process.args, timeout)
        return original_wait(process, timeout=timeout)

    def killpg(group, signum):
        signals.append((group, signum))
        return original_killpg(group, signum)

    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(runner, "_stop_process_group", lambda p: original_stop(p, grace_seconds=.1))
    try:
        if interrupted:
            with pytest.raises(KeyboardInterrupt):
                runner.launch([sys.executable, "-c", worker], tmp_path / "worker.log", 30)
        else:
            code, elapsed, expired = runner.launch(
                [sys.executable, "-c", worker], tmp_path / "worker.log", 30
            )
            assert code == 0  # The parent cooperated; its child did not.
            assert expired and elapsed > 0
        group = int(ready.read_text())
        assert (group, signal.SIGTERM) in signals
        assert (group, signal.SIGKILL) in signals
        time.sleep(.05)
        last = heartbeat.read_bytes()
        time.sleep(.1)
        assert heartbeat.read_bytes() == last
    finally:
        if ready.exists():
            try:
                original_killpg(int(ready.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_cleanup_tolerates_group_already_gone(runner, monkeypatch):
    waited = []

    def missing(*args):
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", missing)
    process = SimpleNamespace(pid=123, poll=lambda: 0, wait=lambda: waited.append(True))
    runner._stop_process_group(process, grace_seconds=.01)
    assert waited == [True]


def test_normal_exit_is_not_a_timeout(runner, tmp_path):
    code, elapsed, expired = runner.launch([sys.executable, "-c", "pass"], tmp_path / "ok.log", 5)
    assert code == 0 and elapsed > 0 and not expired
