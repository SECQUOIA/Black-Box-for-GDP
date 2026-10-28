"""Feasible initialization, isolated workers and recoverable seven-point archives."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile

import pytest

import cstr30_retry as retry


@pytest.mark.parametrize("point", retry.POINTS)
def test_feasible_start_preserves_original_nlp(point):
    pytest.importorskip("pyomo.environ")
    pytest.importorskip("networkx")
    from gdp_models.models import prepare_nlp
    from gdp_models.evaluation import primal_violation

    if not (retry.ROOT / "external/dsda-gdp/.git").exists():
        pytest.skip("Original model checkout not initialized")
    prepared = prepare_nlp("cstr", point, cstr_size=30, initialization="default")
    before = retry.formulation_fingerprint(prepared)
    retry.initialize_feasible(prepared)
    assert retry.formulation_fingerprint(prepared) == before
    assert primal_violation(prepared) < 1e-8
    assert prepared.model.QR.value == 0
    assert prepared.metadata["initialization"] == "mass_balance_zero_recycle"


def test_each_child_is_a_distinct_process_and_failures_are_observable(tmp_path):
    first = retry.run_child([sys.executable, "-c", "print('first')"], tmp_path / "a.log", 10)
    second = retry.run_child([sys.executable, "-c", "raise RuntimeError('probe')"],
                             tmp_path / "b.log", 10)
    assert first["worker_pid"] != second["worker_pid"] != os.getpid()
    assert first["worker_returncode"] == 0 and second["worker_returncode"] != 0
    assert "probe" in (tmp_path / "b.log").read_text()


def test_timeout_stops_child_and_does_not_block_next_point(tmp_path):
    timed = retry.run_child([sys.executable, "-c", "import time; time.sleep(60)"],
                            tmp_path / "timeout.log", 0.1)
    assert timed["worker_timed_out"] and timed["worker_returncode"] != 0
    assert timed["worker_process_wall_s"] < 10
    next_one = retry.run_child([sys.executable, "-c", "print('next')"], tmp_path / "next.log", 10)
    assert next_one["worker_returncode"] == 0


@pytest.mark.parametrize("signum", [0, signal.SIGTERM, signal.SIGKILL])
def test_darwin_group_retry_reaps_worker_and_checks_same_group(monkeypatch, signum):
    monkeypatch.setattr(retry.sys, "platform", "darwin")
    events = []
    process = SimpleNamespace(pid=12345, poll=lambda: events.append("reap"))

    def killpg(pid, sig):
        assert (pid, sig) == (process.pid, signum)
        events.append("signal")
        if events.count("signal") == 1:
            raise PermissionError("exiting group")
        raise ProcessLookupError("group disappeared after reap")

    monkeypatch.setattr(retry.os, "killpg", killpg)
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)
    with pytest.raises(ProcessLookupError):
        retry._signal_process_group(process, signum)
    assert events == ["signal", "reap", "signal"]


@pytest.mark.parametrize("platform,attempts", [("darwin", 3), ("linux", 1)])
def test_persistent_group_permission_error_is_not_suppressed(monkeypatch, platform, attempts):
    monkeypatch.setattr(retry.sys, "platform", platform)
    calls = []
    denied = PermissionError("actual permission denial")
    process = SimpleNamespace(pid=12345, poll=lambda: None)

    def killpg(pid, sig):
        calls.append((pid, sig))
        raise denied

    monkeypatch.setattr(retry.os, "killpg", killpg)
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError) as error:
        retry._signal_process_group(process, signal.SIGKILL)
    assert error.value is denied
    assert calls == [(process.pid, signal.SIGKILL)] * attempts


def test_reaped_leader_does_not_skip_surviving_group_cleanup(monkeypatch):
    monkeypatch.setattr(retry.sys, "platform", "darwin")
    calls = []
    denied_once = False
    process = SimpleNamespace(pid=12345, poll=lambda: -signal.SIGTERM,
                              wait=lambda: calls.append("wait"))

    def killpg(pid, sig):
        nonlocal denied_once
        assert pid == process.pid
        calls.append(sig)
        if sig == 0 and not denied_once:
            denied_once = True
            raise PermissionError("leader exiting, descendants still present")

    monkeypatch.setattr(retry.os, "killpg", killpg)
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)
    retry.stop_process(process, grace=0)
    assert calls == [signal.SIGTERM, 0, 0, signal.SIGKILL, "wait"]


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin zombie-only process-group behavior")
def test_darwin_cleanup_of_exited_but_unreaped_worker():
    process = subprocess.Popen([sys.executable, "-c", "pass"],
                               start_new_session=True, stdout=subprocess.PIPE)
    try:
        # EOF leaves the worker unreaped, unlike Popen.poll()/wait().
        # Allow exit to settle without requiring a particular Darwin errno.
        process.stdout.read()
        time.sleep(0.05)
        retry.stop_process(process, grace=0.05)
        assert process.returncode == 0
        with pytest.raises(ChildProcessError):
            os.waitpid(process.pid, os.WNOHANG)
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def manifest():
    return {"kind": retry.KIND, "points": [list(p) for p in retry.POINTS], "config": {}}


def assert_archive(directory):
    path = directory.with_name(directory.name + ".zip")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == path.with_suffix(".zip.sha256").read_text().split()[0]
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for line in z.read(directory.name + "/SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(z.read(directory.name + "/" + name)).hexdigest() == digest
        return json.loads(z.read(directory.name + "/summary.json"))


def fake_success(directory, point, config):
    report = {"case": "cstr", "cstr_size": 30, "point": point, "solver": "gams_ipopt",
              "accepted": True, "objective": 3.1, "status": "accepted", "total_wall_s": 1}
    retry.write_json(directory / "records" / (retry.point_name(point) + ".json"), report)
    return report


def test_one_worker_error_keeps_all_other_results_and_zip(tmp_path, monkeypatch):
    directory = tmp_path / "results"
    directory.mkdir()
    calls = []

    def one_error(directory, point, config):
        calls.append(tuple(point))
        if point == [5, 3]:
            raise OSError("Failed to start worker")
        return fake_success(directory, point, config)

    monkeypatch.setattr(retry, "run_point", one_error)
    result = retry.run_points(directory, manifest())
    assert calls == list(retry.POINTS)
    assert result["complete"] and not result["all_accepted"]
    assert result["completed_points"] == 7 and result["accepted_points"] == 6
    assert result["nonaccepted_points"] == [[5, 3]]
    assert assert_archive(directory) == result
    assert len((directory / "evaluations.csv").read_text().splitlines()) == 8


def test_interruption_packages_completed_records_and_pending_points(tmp_path, monkeypatch):
    directory = tmp_path / "interrupted"
    directory.mkdir()

    def interrupted(directory, point, config):
        if point == [6, 2]:
            raise KeyboardInterrupt
        return fake_success(directory, point, config)

    monkeypatch.setattr(retry, "run_point", interrupted)
    with pytest.raises(KeyboardInterrupt):
        retry.run_points(directory, manifest())
    summary = assert_archive(directory)
    assert summary["accepted_points"] == 2
    assert not summary["complete"] and len(summary["pending_points"]) == 5


def test_missing_worker_record_becomes_explicit_error(tmp_path, monkeypatch):
    (tmp_path / "records").mkdir()
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(retry, "run_child", lambda *a: {
        "worker_pid": 1234, "worker_returncode": 1, "worker_timed_out": False,
        "worker_process_wall_s": 0.2})
    result = retry.run_point(tmp_path, (5, 3), {"executable": "/gams", "time_limit": 60,
                                             "worker_timeout": 180})
    assert result["status"] == "worker_error" and not result["accepted"]
    assert result["original_point_index"] == 13
    assert result["worker_process_wall_s"] == 0.2 and "total_wall_s" not in result


def test_small_bundle_has_own_directory_and_verified_source(tmp_path):
    path = tmp_path / "runner.zip"
    retry.bundle(path)
    assert path.stat().st_size < 100_000
    with zipfile.ZipFile(path) as z:
        assert all(n.startswith("cstr30_retry_runner/") for n in z.namelist())
        assert not any("/external/" in n or "/results/" in n for n in z.namelist())
        for line in z.read("cstr30_retry_runner/RETRY_RUNNER_SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(z.read("cstr30_retry_runner/" + name)).hexdigest() == digest


def test_only_selected_seven_points_are_allowed():
    assert retry.parse_point("5,3") == (5, 3)
    with pytest.raises(ValueError):
        retry.parse_point("30,30")
