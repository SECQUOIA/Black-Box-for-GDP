"""Enumeration coverage, checkpoint recovery, and batch failure reporting."""
# ruff: noqa: E402 -- check optional GDP dependencies before imports.

import csv
import fcntl
import json
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("pyomo.environ")
pytest.importorskip("networkx")

from pyomo.common.errors import InfeasibleConstraintException

from gdp_models import batch
from gdp_models.domains import enumeration_plan
from gdp_models.models import _fix_static, build_gdp


@pytest.mark.parametrize("case,size,logical,box", [
    ("cstr", 5, 15, 25), ("cstr", 30, 465, 900),
    ("small_batch", 5, 27, 27), ("column", 5, 64, 225), ("dynamic", 5, 37, 72),
])
def test_coordinate_counts_and_unique_order(case, size, logical, box):
    plan = enumeration_plan(case, cstr_size=size)
    full = enumeration_plan(case, cstr_size=size, domain="box")
    points = list(map(tuple, plan["points"]))
    assert len(points) == logical and len(full["points"]) == box
    assert points == sorted(set(points))
    assert set(points) <= set(map(tuple, full["points"]))
    assert plan["excluded_by_logic"] == box - logical


@pytest.mark.parametrize("case", ["cstr", "column", "small_batch"])
def test_logical_filter_matches_original_gdp(case):
    if not (Path(__file__).resolve().parents[1] / "external/dsda-gdp/.git").exists():
        pytest.skip("Initialize GDP submodules")
    # Check every tuple against the original logical rules without using any
    # objective/feasibility table or solving a continuous subproblem.
    original = build_gdp(case)
    selected = set(map(tuple, enumeration_plan(case)["points"]))
    for point in enumeration_plan(case, domain="box")["points"]:
        try:
            _fix_static(original.clone(), case, tuple(point))
            allowed = True
        except InfeasibleConstraintException:
            allowed = False
        assert allowed == (tuple(point) in selected), (case, point)


@pytest.fixture
def fake_runtime(monkeypatch):
    identity = {"solver_executable": "/test/ipopt", "identity": "original"}
    monkeypatch.setattr(batch, "_runtime_identity", lambda *args: dict(identity))
    calls = []

    def evaluate(case, point, **kwargs):
        calls.append(tuple(point))
        return {"case": case, "point": point, "cstr_size": None,
                "solver": kwargs["solver"], "status": "accepted", "accepted": True,
                "objective": sum(point), "termination": "optimal", "total_wall_s": 0.5,
                "solve_wall_s": 0.3}

    monkeypatch.setattr(batch, "evaluate_point", evaluate)
    return calls, identity, evaluate


def test_pause_and_resume_all_points_exactly_once(tmp_path, fake_runtime):
    calls, _, _ = fake_runtime
    first = batch.run_batch("small_batch", tmp_path, solver="ipopt", max_points=3)
    assert first["completed_points"] == 3 and not first["complete"]
    assert first["status"] == "paused"
    # Simulate a crash between the durable JSON record and CSV append.
    (tmp_path / "evaluations.csv").write_text("truncated,csv\n")
    (tmp_path / "records/point_000004.json.tmp").write_text("unfinished JSON")
    final = batch.run_batch("small_batch", tmp_path, solver="ipopt", resume=True)
    assert final["complete"] and final["completed_points"] == 27
    assert len(calls) == len(set(calls)) == 27
    with (tmp_path / "evaluations.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 27
    assert {tuple(json.loads(r["point"])) for r in rows} == set(calls)
    assert all(r["x3"] for r in rows)
    assert final["sum_evaluation_wall_s"] == 13.5
    batch.run_batch("small_batch", tmp_path, solver="ipopt", resume=True)
    assert len(calls) == 27  # A completed resume calls no NLP solver.


def test_interrupt_preserves_only_finished_points(tmp_path, monkeypatch, fake_runtime):
    calls, _, evaluate = fake_runtime

    def interrupt(case, point, **kwargs):
        if len(calls) == 1:
            raise KeyboardInterrupt
        return evaluate(case, point, **kwargs)

    monkeypatch.setattr(batch, "evaluate_point", interrupt)
    with pytest.raises(KeyboardInterrupt):
        batch.run_batch("small_batch", tmp_path, solver="ipopt")
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["status"] == "interrupted" and summary["completed_points"] == 1
    monkeypatch.setattr(batch, "evaluate_point", evaluate)
    batch.run_batch("small_batch", tmp_path, solver="ipopt", resume=True)
    assert len(calls) == len(set(calls)) == 27


def test_errors_are_recorded_and_do_not_hide_other_points(tmp_path, monkeypatch, fake_runtime):
    _, _, evaluate = fake_runtime

    def mixed(case, point, **kwargs):
        if point == [1, 1, 1]:
            raise RuntimeError("unexpected model failure")
        result = evaluate(case, point, **kwargs)
        if point == [1, 1, 2]:
            result.update(status="solver_error", accepted=False, objective=None)
        elif point == [1, 1, 3]:
            result.update(status="preprocessing_infeasible", accepted=False, objective=None,
                          rejection_phase="preprocessing", solve_wall_s=0.0)
        return result

    monkeypatch.setattr(batch, "evaluate_point", mixed)
    summary = batch.run_batch("small_batch", tmp_path, solver="ipopt")
    assert summary["complete"] and summary["status"] == "completed_with_errors"
    assert summary["error_points"] == 2 and summary["accepted_points"] == 24
    assert "unexpected model failure" in (tmp_path / "run.log").read_text()
    report = json.loads((tmp_path / "records/point_000001.json").read_text())
    assert report["objective"] is None and report["total_wall_s"] > 0
    with (tmp_path / "evaluations.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["solve_wall_s"] == ""  # Unknown costs must not become zero.
    assert rows[2]["rejection_phase"] == "preprocessing"
    assert json.loads((tmp_path / "records/point_000003.json").read_text())["rejection_phase"] == "preprocessing"


@pytest.mark.parametrize("changed", ["options", "runtime", "domain"])
def test_resume_refuses_incompatible_results(tmp_path, fake_runtime, changed):
    calls, identity, _ = fake_runtime
    batch.run_batch("small_batch", tmp_path, solver="ipopt", max_points=1)
    kwargs = {}
    if changed == "options":
        kwargs["time_limit"] = 120
    elif changed == "runtime":
        identity["identity"] = "different source or solver"
    else:
        kwargs["domain"] = "box"
    with pytest.raises(ValueError, match="Resume requires"):
        batch.run_batch("small_batch", tmp_path, solver="ipopt", resume=True, **kwargs)
    assert len(calls) == 1


def test_refuses_overwrite_or_wrong_checkpoint(tmp_path, fake_runtime):
    batch.run_batch("small_batch", tmp_path, solver="ipopt", max_points=1)
    with pytest.raises(FileExistsError):
        batch.run_batch("small_batch", tmp_path, solver="ipopt")
    path = tmp_path / "records/point_000001.json"
    report = json.loads(path.read_text())
    report["point"] = [3, 3, 3]
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Invalid checkpoint"):
        batch.run_batch("small_batch", tmp_path, solver="ipopt", resume=True)


def test_rejects_concurrent_writer(tmp_path, fake_runtime):
    with (tmp_path / ".batch.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="Another batch"):
            batch.run_batch("small_batch", tmp_path, solver="ipopt")


def test_dry_run_needs_no_solver_and_writes_no_output(tmp_path):
    output = tmp_path / "not-created"
    completed = subprocess.run([
        sys.executable, "-m", "gdp_models.batch", "--case", "cstr", "--cstr-size", "30",
        "--solver", "ipopt", "--executable", "/nonexistent/ipopt", "--dry-run",
        "--output-dir", str(output),
    ], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["candidate_count"] == 465
    assert not output.exists()


def test_preflight_failure_does_not_create_fake_results(tmp_path, monkeypatch):
    def unavailable(*args):
        raise FileNotFoundError("missing IPOPT")

    monkeypatch.setattr(batch, "_runtime_identity", unavailable)
    with pytest.raises(FileNotFoundError, match="missing IPOPT"):
        batch.run_batch("small_batch", tmp_path, solver="ipopt")
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "evaluations.csv").exists()


def test_deferred_import_failure_stops_without_recording_bad_points(tmp_path, monkeypatch, fake_runtime):
    from pyomo.common.dependencies import DeferredImportError
    from gdp_models.preflight import SetupError

    calls, _, evaluate = fake_runtime

    def missing(case, point, **kwargs):
        if calls:
            raise DeferredImportError("No module named 'sympy'")
        return evaluate(case, point, **kwargs)

    monkeypatch.setattr(batch, "evaluate_point", missing)
    with pytest.raises(SetupError, match="sympy"):
        batch.run_batch("small_batch", tmp_path, solver="ipopt")
    result = json.loads((tmp_path / "summary.json").read_text())
    assert result["status"] == "batch_error"
    assert result["completed_points"] == 1 and not result["complete"]
    assert len(list((tmp_path / "records").glob("*.json"))) == 1
