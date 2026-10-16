"""Real process groups: a worker exiting is not proof its solver child exited."""

import ctypes
import os
import signal
import subprocess
import sys
import time

import pytest

import cstr30_retry as runner


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper reaps disposable grandchildren")

CHILD = """
import os, signal, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(30)
"""
PARENT = """
import subprocess, sys, time
subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])
time.sleep(30)
"""


def wait_file(path):
    deadline = time.monotonic() + 5
    while not path.exists():
        if time.monotonic() >= deadline:
            pytest.fail(f"Disposable child did not become ready: {path}")
        time.sleep(0.01)
    return int(path.read_text())


def reap(pid):
    deadline = time.monotonic() + 5
    while True:
        found, status = os.waitpid(pid, os.WNOHANG)
        if found:
            return status
        if time.monotonic() >= deadline:
            pytest.fail(f"Disposable descendant {pid} is still alive")
        time.sleep(0.01)


@pytest.fixture
def processes(monkeypatch):
    # Adopt only this test's orphaned grandchildren so teardown can reap them,
    # including on the deliberately failing pre-fix regression run.
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    owned = []
    original = subprocess.Popen

    def popen(*args, **kwargs):
        assert kwargs.get("start_new_session") is True
        process = original(*args, **kwargs)
        owned.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", popen)
    try:
        yield owned
    finally:
        try:
            for process in owned:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for process in owned:
                original.wait(process, timeout=5)
                # Reap only adopted children in this owned group.
                deadline = time.monotonic() + 5
                while True:
                    try:
                        pid, _ = os.waitpid(-process.pid, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if not pid:
                        assert time.monotonic() < deadline, "Could not reap disposable descendants"
                        time.sleep(0.01)
        finally:
            assert libc.prctl(36, previous.value, 0, 0, 0) == 0


@pytest.mark.parametrize("interrupt", [False, True])
def test_launch_cleans_surviving_child_and_preserves_outcome(
        processes, tmp_path, monkeypatch, interrupt):
    stop = runner.stop_process
    monkeypatch.setattr(runner, "stop_process", lambda process: stop(process, grace=0.05))
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    pidfile = tmp_path / "child.pid"
    original_popen = subprocess.Popen

    def ready_worker(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        wait_file(pidfile)
        if interrupt:
            original_wait = process.wait
            first = True

            def wait(*args, **kwargs):
                nonlocal first
                if first:
                    first = False
                    raise KeyboardInterrupt
                return original_wait(*args, **kwargs)

            monkeypatch.setattr(process, "wait", wait)
        return process

    monkeypatch.setattr(subprocess, "Popen", ready_worker)
    command = [sys.executable, "-c", PARENT, CHILD, str(pidfile)]
    if interrupt:
        with pytest.raises(KeyboardInterrupt):
            runner.run_child(command, tmp_path / "worker.log", 0.05)
    else:
        result = runner.run_child(command, tmp_path / "worker.log", 0.05)
        assert result["worker_timed_out"] is True
        assert result["worker_returncode"] == -signal.SIGTERM
        assert result["worker_process_wall_s"] >= 0.05
    worker = processes[-1]
    assert worker.returncode == -signal.SIGTERM
    child_status = reap(int(pidfile.read_text()))
    assert os.WIFSIGNALED(child_status) and os.WTERMSIG(child_status) == signal.SIGKILL
    assert unrelated.poll() is None  # The watchdog owns only the new worker session.


def test_launch_normal_exit_is_reaped_without_timeout(processes, tmp_path):
    result = runner.run_child([sys.executable, "-c", "raise SystemExit(7)"],
                              tmp_path / "normal.log", 5)
    assert result["worker_returncode"] == 7 and result["worker_timed_out"] is False
    assert result["worker_process_wall_s"] >= 0
    assert processes[-1].returncode == 7
    with pytest.raises(ChildProcessError):
        os.waitpid(processes[-1].pid, os.WNOHANG)


def test_stop_tolerates_an_already_reaped_group(processes):
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    assert process.wait(timeout=5) == 0
    runner.stop_process(process, grace=0.05)
    assert process.returncode == 0


@pytest.mark.parametrize("phase", ["grace", "kill", "reap"])
def test_interrupt_during_cleanup_still_kills_and_reaps(
        processes, tmp_path, monkeypatch, phase):
    pidfile = tmp_path / "child.pid"
    process = subprocess.Popen([sys.executable, "-c", PARENT, CHILD, str(pidfile)], start_new_session=True)
    child = wait_file(pidfile)
    original_wait = process.wait
    original_sleep = time.sleep
    original_killpg = os.killpg
    interrupted = False

    def once(callback):
        def call(*args, **kwargs):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return callback(*args, **kwargs)
        return call

    if phase == "grace":
        monkeypatch.setattr(time, "sleep", once(original_sleep))
    elif phase == "reap":
        monkeypatch.setattr(process, "wait", once(original_wait))
    else:
        kill_once = once(original_killpg)

        def killpg(group, sig):
            return kill_once(group, sig) if sig == signal.SIGKILL else original_killpg(group, sig)

        monkeypatch.setattr(os, "killpg", killpg)
    with pytest.raises(KeyboardInterrupt):
        runner.stop_process(process, grace=0.05)
    assert interrupted and process.returncode is not None
    status = reap(child)
    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
