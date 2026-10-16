"""GAMS routing, option files and independent status/feasibility acceptance."""
# ruff: noqa: E402 -- optional GDP dependencies.

from pathlib import Path
import hashlib
import importlib
import os
from types import SimpleNamespace

import pytest

pyo = pytest.importorskip("pyomo.environ")

from gdp_models import evaluation, solvers
from gdp_models.models import PreparedNLP
from gdp_models.preflight import SetupError


@pytest.fixture
def gams_binaries(tmp_path, monkeypatch):
    from pyomo.common import Executable

    original_path = os.environ.get("PATH", "")
    paths = []
    for name in ("on-path", "requested"):
        directory = tmp_path / name
        directory.mkdir()
        binary = directory / "gams"
        binary.write_text(f"#!/bin/sh\n# {name}\nexit 99\n")
        binary.chmod(0o755)
        paths.append(binary)
    monkeypatch.setenv("PATH", str(paths[0].parent))
    Executable("gams").rehash()
    yield paths
    # Do not leak a cached executable into other tests after PATH is restored.
    monkeypatch.setenv("PATH", original_path)
    Executable("gams").rehash()


@pytest.mark.parametrize("solver", solvers.GAMS_SOLVERS)
@pytest.mark.parametrize("path_present", [True, False])
def test_real_gams_object_uses_requested_binary_for_all_calls(
        solver, path_present, gams_binaries, tmp_path, monkeypatch):
    from pyomo.common import Executable
    from pyomo.solvers.plugins.solvers.GAMS import GAMSShell

    _, requested = gams_binaries
    if not path_present:
        monkeypatch.setenv("PATH", "")
        Executable("gams").rehash()
    calls = []

    class DispatchReached(Exception):
        pass

    def run(command, **kwargs):
        calls.append(command)
        assert command[0] == str(requested)
        if command[1] == "model.gms":
            raise DispatchReached
        return SimpleNamespace(returncode=0, stdout="GAMS 52.2.0.0")

    gams_module = importlib.import_module("pyomo.solvers.plugins.solvers.GAMS")
    monkeypatch.setattr(gams_module.subprocess, "run", run)
    optimizer = solvers.optimizer_for(solver, requested)
    assert isinstance(optimizer, GAMSShell)  # Exercise Pyomo, not a factory double.
    assert optimizer.executable() == str(requested)
    assert optimizer.available(exception_flag=False)
    assert optimizer.version() == (52, 2, 0, 0)
    m = pyo.ConcreteModel()
    m.x = pyo.Var(initialize=1)
    m.obj = pyo.Objective(expr=m.x**2)
    with pytest.raises(DispatchReached):
        optimizer.solve(m, tmpdir=str(tmp_path / "solve"), solver="ipopt", mtype="nlp",
                        io_options={"put_results_format": "dat"})
    assert any(command[1].endswith("test.gms") for command in calls)
    assert any(command[1] == "audit" for command in calls)
    assert any(command[1] == "model.gms" for command in calls)


@pytest.mark.parametrize("kind", ["missing", "nonexecutable", "directory"])
def test_gams_invalid_requested_binary_never_falls_back_to_path(
        kind, gams_binaries, tmp_path, monkeypatch):
    requested = tmp_path / "invalid-gams"
    if kind == "nonexecutable":
        requested.write_text("not executable")
    elif kind == "directory":
        requested.mkdir()

    def no_probe(self, n):
        pytest.fail("Unavailable explicit binaries must not probe the GAMS on PATH")

    monkeypatch.setattr(solvers.GAMSShell, "_run_simple_model", no_probe)
    optimizer = solvers.optimizer_for("conopt", requested)
    assert not optimizer.available(exception_flag=False)
    with pytest.raises((RuntimeError, NameError), match="GAMS|gams"):
        optimizer.available()


@pytest.mark.parametrize("explicit", [True, False])
def test_point_records_effective_gams_executable(gams_binaries, monkeypatch, explicit):
    on_path, requested = gams_binaries
    m = pyo.ConcreteModel()
    monkeypatch.setattr(evaluation, "prepare_nlp", lambda *a, **k: PreparedNLP(m, (1, 1), {}, {}, []))

    def stop(optimizer, *args, **kwargs):
        assert optimizer.executable() == str(requested if explicit else on_path)
        raise RuntimeError("stop before execution")

    monkeypatch.setattr(evaluation, "solve_gams", stop)
    # Resolve relative paths and symlinks before recording provenance.
    link = requested.parent / "gams-link"
    link.symlink_to(requested)
    monkeypatch.chdir(requested.parent)
    result = evaluation.evaluate_point("cstr", (1, 1), solver="conopt",
                                       executable="./gams-link" if explicit else None)
    assert result["status"] == "solver_error"
    assert result["message"] == "stop before execution"
    assert result["solver_executable"] == str(requested if explicit else on_path)


def test_batch_hashes_the_gams_binary_used_by_pyomo(gams_binaries, monkeypatch):
    from gdp_models import batch

    _, requested = gams_binaries
    monkeypatch.setattr(batch, "dependency_versions", lambda: {})
    monkeypatch.setattr(batch, "initialization_info", lambda *a: ("default", []))
    monkeypatch.setattr(batch, "model_check", lambda *a: {})
    monkeypatch.setattr(batch, "provenance", lambda *a: {})
    monkeypatch.setattr(batch.platform, "platform", lambda: "test platform")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[0] == str(requested)
        return SimpleNamespace(returncode=0, stdout="GAMS 52.2.0.0")

    def smoke(solver, binary, digest):
        assert binary == str(requested)
        assert digest == hashlib.sha256(requested.read_bytes()).hexdigest()
        return {"status": "passed"}

    gams_module = importlib.import_module("pyomo.solvers.plugins.solvers.GAMS")
    monkeypatch.setattr(gams_module.subprocess, "run", run)
    monkeypatch.setattr(batch, "gams_smoke_check", smoke)
    identity = batch._runtime_identity("cstr", 5, "auto", "conopt", requested)
    assert calls and all(command[0] == str(requested) for command in calls)
    assert identity["solver_executable"] == str(requested)
    assert identity["solver_executable_sha256"] == hashlib.sha256(requested.read_bytes()).hexdigest()
    assert identity["solver_version"] == [52, 2, 0, 0]


@pytest.fixture
def gams_result(monkeypatch):
    m = pyo.ConcreteModel()
    m.x = pyo.Var(initialize=0)
    m.c = pyo.Constraint(expr=m.x == 1)
    m.obj = pyo.Objective(expr=m.x)
    prepared = PreparedNLP(m, (1, 1), {}, {}, [m.c])
    monkeypatch.setattr(evaluation, "prepare_nlp", lambda *a, **k: prepared)
    state = {"solve_status": 1, "model_status": 2, "value": 1,
             "status": "ok", "termination": "locallyOptimal", "calls": []}

    def solve(self, model, **kwargs):
        assert self.executable() == "/gams/52.2/gams"
        state["calls"].append(kwargs)
        assert kwargs["load_solutions"] is False
        assert kwargs["io_options"]["put_results_format"] == "dat"
        assert kwargs["warmstart"] is True  # Write the specified initial .l values.
        assert kwargs["mtype"] == "nlp"
        path = Path(kwargs["tmpdir"])
        if kwargs["solver"] in {"ipopt", "ipopth"}:
            content = (path / f"{kwargs['solver']}.opt").read_text()
            assert "tol 1e-8" in content and "warm_start_init_point no" in content
            assert f"linear_solver {'mumps' if kwargs['solver'] == 'ipopt' else 'ma27'}" in content
            assert "GAMS_MODEL.optfile=1;" in kwargs["add_options"]
        (path / "resultsstat.dat").write_text(
            f"status values\nSOLVESTAT {state['solve_status']}\nMODELSTAT {state['model_status']}\nETSOLVE 0.5\n"
        )
        return SimpleNamespace(solution=[object()], solver=SimpleNamespace(
            status=state["status"], termination_condition=state["termination"], message="test"))

    # Double only the actual solver call; retain the real Pyomo object/routing.
    monkeypatch.setattr(solvers.GAMSShell, "solve", solve)
    monkeypatch.setattr(m.solutions, "load_from", lambda result: m.x.set_value(state["value"]))
    return state


@pytest.mark.parametrize("solver", ["gams_ipopt", "ipopth", "conopt", "baron"])
def test_gams_solver_is_explicit_and_original_status_is_saved(solver, gams_result):
    result = evaluation.evaluate_point("cstr", (1, 1), solver=solver, executable="/gams/52.2/gams")
    assert result["accepted"] and result["objective"] == 1
    assert result["gams_solver"] == solvers.GAMS_SOLVERS[solver]
    assert result["gams_solve_status"] == 1 and result["gams_model_status"] == 2
    assert result["rejection_phase"] is None
    assert gams_result["calls"][0]["solver"] == solvers.GAMS_SOLVERS[solver]


def test_gams_limit_cannot_be_hidden_by_optimal_model_status(gams_result):
    gams_result["solve_status"] = 3
    result = evaluation.evaluate_point("cstr", (1, 1), solver="ipopth", executable="/gams/52.2/gams")
    assert result["termination"] == "maxTimeLimit"
    assert not result["accepted"] and result["objective"] is None
    assert result["candidate_objective"] == 1


def test_gams_optimal_status_still_requires_primal_feasibility(gams_result):
    gams_result["value"] = 0.5
    result = evaluation.evaluate_point("cstr", (1, 1), solver="conopt", executable="/gams/52.2/gams")
    assert not result["accepted"] and result["max_primal_violation"] == 0.5


def test_gams_error_status_is_recorded_without_loading_bad_solution(gams_result):
    gams_result.update(status="error", termination="solverFailure", solve_status=10, model_status=13)
    result = evaluation.evaluate_point("cstr", (1, 1), solver="ipopth", executable="/gams/52.2/gams")
    assert result["status"] == "solver_error" and result["gams_solve_status"] == 10
    assert result["termination"] == "solverFailure" and result["objective"] is None


def test_gams_license_failure_stops_batch(gams_result):
    gams_result.update(status="aborted", termination="licensingProblems", solve_status=7, model_status=11)
    with pytest.raises(SetupError, match="license failure"):
        evaluation.evaluate_point("cstr", (1, 1), solver="ipopth", executable="/gams/52.2/gams")


def test_gams_preflight_runs_solver_and_propagates_unavailability(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("solver not installed")

    monkeypatch.setattr(solvers, "optimizer_for", lambda *args: object())
    monkeypatch.setattr(solvers, "solve_gams", unavailable)
    with pytest.raises(SetupError, match="solver not installed"):
        solvers.gams_smoke_check.__wrapped__("conopt", "/gams", "digest")
