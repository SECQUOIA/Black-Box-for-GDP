"""Validate callback coverage and recovery, without requiring licensed solvers."""

import csv
import json
import math
import sys
from types import SimpleNamespace
import zipfile

import pytest

import grid_trace_runner as runner


@pytest.fixture
def spec():
    return runner.plan("bam", ["ackley"], [0], [10])[0]


@pytest.fixture
def fake_solvers(monkeypatch):
    def minimize(objective, **kwargs):
        options = kwargs["options"]
        starts, values = options["x_evaluated"], options["f_evaluated"]
        # A repeat must be recorded, not deduplicated by the trace runner.
        points = [starts[0], [15, 15]]
        all_points = list(starts) + points
        all_values = list(values) + [objective(point) for point in points]
        index = min(range(len(all_values)), key=all_values.__getitem__)
        return SimpleNamespace(fun=all_values[index], x=all_points[index], nfev=2,
                               nit=2, status=0, message="test completion")

    class Algorithm:
        def __init__(self, settings, black_box, **kwargs):
            self.objective = black_box
            self.starts = kwargs["init_node_pos"]
            assert kwargs["init_node_val"] is None
            assert kwargs["do_init_strategy"] is False

        def optimize(self):
            points = list(self.starts) + [self.starts[0], [15, 15]]
            values = [self.objective(point) for point in points]
            best = min(range(len(values)), key=values.__getitem__)
            return values[best], points[best], 2, len(values), 0

    monkeypatch.setitem(sys.modules, "bam", SimpleNamespace(minimize=minimize, set_license_file=lambda _: None))
    monkeypatch.setitem(sys.modules, "rbfopt", SimpleNamespace(
        RbfoptSettings=lambda **kwargs: kwargs, RbfoptAlgorithm=Algorithm,
        RbfoptUserBlackBox=lambda n, lb, ub, types, objective: objective))


def config(method):
    return {"method": method, "cpu": None, "bonmin": sys.executable,
            "ipopt": sys.executable, "bam_license": "", "max_run_seconds": 0}


def persist(attempt, spec):
    attempt.mkdir(parents=True)
    result = runner.lookup(spec, config(spec["method"]), attempt)
    runner.save(attempt / "result.json", result)
    runner.save(attempt / "complete.json", {"result_sha256": runner.sha(attempt / "result.json")})
    return result


def test_full_plan_preserves_original_designs_and_separate_methods():
    for method in ("rbfopt", "bam"):
        jobs = runner.plan(method)
        assert len(jobs) == len({s["job_id"] for s in jobs}) == 1050
        assert len({s["csv_name"] for s in jobs}) == 21
        assert {s["max_evaluations"] for s in jobs} == {10, 30, 50, 70, 100}
        assert all(s["method"] == method and s["n_starts"] == 3 for s in jobs)
        assert jobs[0]["starting_points"] == [[4, 7], [30, 30], [12, 11]]
    with pytest.raises(ValueError, match="seeds"):
        runner.plan("bam", seeds=[10])


@pytest.mark.parametrize("method", ["rbfopt", "bam"])
def test_actual_adapters_capture_initial_repeat_and_adaptive_calls(tmp_path, fake_solvers, method):
    spec = runner.plan(method, ["ackley"], [0], [10])[0]
    result = persist(tmp_path / "attempt_1", spec)
    _, saved, events = runner.completed(tmp_path, spec)
    assert saved == result
    assert [e["point"] for e in events] == spec["starting_points"] + [[4, 7], [15, 15]]
    assert [e["repeated_point"] for e in events] == [False, False, False, True, False]
    assert [e["phase"] for e in events] == ["initial"] * 3 + ["adaptive"] * 2
    assert saved["lookup_wall_s"] == sum(e["objective_wall_s"] for e in events)
    assert saved["search_wall_s"] >= events[-1]["completed_elapsed_s"]
    assert saved["result_record"]["unique_evals"] == 4


def test_partial_attempt_is_retained_and_never_exported(tmp_path, spec, fake_solvers, monkeypatch):
    run = {"kind": runner.KIND, "config": config("bam"), "plan": [spec]}
    runner.save(tmp_path / "run.json", run)
    attempt = tmp_path / "jobs" / spec["job_id"] / "attempt_1"
    attempt.mkdir(parents=True)

    def fail(objective, **kwargs):
        objective([15, 15])
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(sys.modules["bam"], "minimize", fail)
    assert runner.worker(tmp_path, attempt, spec["job_id"]) == 1
    assert runner.completed(attempt.parent, spec) is None
    partial = list(attempt.glob("lookup.traces/*.partial.jsonl"))
    assert len(partial) == 1
    events = [json.loads(line) for line in partial[0].read_text().splitlines()]
    assert sum(e["event"] == "evaluation" for e in events) == 4
    summary = runner.export(tmp_path, run)
    assert summary["completed_runs"] == summary["evaluation_callbacks"] == 0
    assert partial[0].exists()


def test_checksum_and_objective_tampering_are_rejected(tmp_path, spec, fake_solvers):
    attempt = tmp_path / "attempt_1"
    result = persist(attempt, spec)
    trace = attempt / result["trace"]["path"]
    original = trace.read_text()
    trace.write_text(original + "\n")
    with pytest.raises(ValueError, match="Trace checksum"):
        runner.completed(tmp_path, spec)
    trace.write_text(original)
    entries = [json.loads(line) for line in original.splitlines()]
    entries[1]["value"] += .01
    with pytest.raises(ValueError, match="objective/incumbent"):
        runner.validate_grid_events(entries[1:-1], result["result_record"], spec)


def test_native_result_roundoff_is_allowed_but_wrong_values_and_points_fail(tmp_path, fake_solvers):
    spec = runner.plan("bam", ["alpine2"], [8], [70])[0]
    result = persist(tmp_path / "attempt_1", spec)
    _, _, events = runner.completed(tmp_path, spec)
    record = result["result_record"]
    rounded = {**record, "best_value": math.nextafter(record["best_value"], math.inf)}
    assert rounded["best_value"] != record["best_value"]
    runner.validate_grid_events(events, rounded, spec)
    with pytest.raises(ValueError, match="Final optimizer result"):
        runner.validate_grid_events(events, {**record, "best_value": record["best_value"] + 1e-9}, spec)
    with pytest.raises(ValueError, match="Final optimizer result"):
        runner.validate_grid_events(events, {**rounded, "best_point": [0, 0]}, spec)


def test_validation_upgrade_preserves_original_source_and_completed_work(tmp_path, spec, fake_solvers):
    # Use the published experiment's immutable snapshot. Current documentation
    # may change independently of the one-file historical validation upgrade.
    source = runner.ROOT / "results/archives/grid_trace_rbfopt_20261008_190603_og2app39.zip"
    assert runner.sha(source) == source.with_suffix(".zip.sha256").read_text().split()[0]
    with zipfile.ZipFile(source) as archive:
        prefix = source.stem + "/"
        original = json.loads(archive.read(prefix + "run.json"))["source_sha256"]
        assert original["grid_trace_runner.py"] == runner.ORIGINAL_RUNNER_SHA256
        for name in original:
            path = tmp_path / "source" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(prefix + "source/" + name))
            assert runner.sha(path) == original[name]
    hashes = {**original, "grid_trace_runner.py": runner.sha(runner.ROOT / "grid_trace_runner.py")}
    run = {"kind": runner.KIND, "config": config("bam"), "plan": [spec], "source_sha256": original}
    runner.save(tmp_path / "run.json", run)
    result = persist(tmp_path / "jobs" / spec["job_id"] / "attempt_1", spec)
    runner.upgrade_roundoff_validation(tmp_path, run, hashes)
    assert runner.read(tmp_path / "validation_fix/original_run.json")["source_sha256"] == original
    assert run["source_sha256"] == original
    assert run["resume_source_sha256"] == hashes
    assert run["validation_fix"]["completed_runs_preserved"] == 1
    assert runner.sha(tmp_path / "source/grid_trace_runner.py") == runner.ORIGINAL_RUNNER_SHA256
    assert runner.sha(tmp_path / "validation_fix/grid_trace_runner.py") == hashes["grid_trace_runner.py"]
    assert runner.completed(tmp_path / "jobs" / spec["job_id"], spec)[1] == result


def test_roundoff_upgrade_cannot_bypass_unrelated_source_changes(tmp_path):
    original = {"grid_trace_runner.py": runner.ORIGINAL_RUNNER_SHA256, "benchmark.py": "unchanged"}
    run = {"source_sha256": original}
    hashes = {"grid_trace_runner.py": "fixed", "benchmark.py": "different algorithm"}
    with pytest.raises(ValueError, match="all other inputs unchanged"):
        runner.upgrade_roundoff_validation(tmp_path, run, hashes)
    assert not (tmp_path / "validation_fix").exists()


def test_resume_skips_completed_and_exports_all_callbacks(tmp_path, fake_solvers, monkeypatch):
    specs = runner.plan("bam", ["ackley"], [0, 1], [10])
    run = {"kind": runner.KIND, "config": config("bam"), "plan": specs,
           "runtime": {}, "source_sha256": {}}
    runner.save(tmp_path / "run.json", run)
    persist(tmp_path / "jobs" / specs[0]["job_id"] / "attempt_1", specs[0])
    old = tmp_path / "jobs" / specs[1]["job_id"] / "attempt_0" / "partial.txt"
    old.parent.mkdir(parents=True)
    old.write_text("interrupted attempt")
    launched = []

    def launch(directory, spec, limit):
        launched.append(spec["job_id"])
        persist(directory / "jobs" / spec["job_id"] / "attempt_1", spec)
        return runner.completed(directory / "jobs" / spec["job_id"], spec)

    monkeypatch.setattr(runner, "source_hashes", lambda: {})
    monkeypatch.setattr(runner, "runtime", lambda _: {})
    monkeypatch.setattr(runner, "launch", launch)
    runner.execute(tmp_path, run)
    assert launched == [specs[1]["job_id"]]
    assert old.read_text() == "interrupted attempt"
    with (tmp_path / "evaluations.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 10
    assert sum(r["repeated_point"] == "True" for r in rows) == 2
    assert runner.read(tmp_path / "summary.json")["all_completed"]
    with zipfile.ZipFile(tmp_path.with_suffix(".zip")) as archive:
        assert archive.testzip() is None
        assert tmp_path.name + "/SHA256SUMS" in archive.namelist()


def test_active_run_cannot_be_resumed_or_packed(tmp_path):
    with runner.locked(tmp_path):
        with pytest.raises(RuntimeError, match="active"):
            with runner.locked(tmp_path):
                pass


def test_bundle_contains_verified_inputs_and_no_local_artifacts(tmp_path):
    path = tmp_path / "runner.zip"
    runner.bundle(path)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len([name for name in names if "/benchmark_grids/" in name]) == 21
        assert all(".venv" not in name and "bamlice" not in name and "__pycache__" not in name for name in names)
        prefix = "grid_dfo_trace_runner/"
        for line in archive.read(prefix + "SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            import hashlib
            assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == digest
    with pytest.raises(FileExistsError):
        runner.bundle(path)
