"""GAMS routing, option files and independent status/feasibility acceptance."""
# ruff: noqa: E402 -- optional GDP dependencies.

from pathlib import Path
from types import SimpleNamespace

import pytest

pyo = pytest.importorskip("pyomo.environ")

from gdp_models import evaluation, solvers
from gdp_models.models import PreparedNLP
from gdp_models.preflight import SetupError


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

    def solve(model, **kwargs):
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

    def factory(name, **kwargs):
        assert name == "gams" and kwargs["solver_io"] == "shell"
        assert kwargs["executable"] == "/gams/52.2/gams"
        return SimpleNamespace(solve=solve)

    monkeypatch.setattr(pyo, "SolverFactory", factory)
    monkeypatch.setattr(m.solutions, "load_from", lambda result: m.x.set_value(state["value"]))
    return state


@pytest.mark.parametrize("solver", ["gams_ipopt", "ipopth", "conopt", "baron"])
def test_gams_solver_is_explicit_and_original_status_is_saved(solver, gams_result):
    result = evaluation.evaluate_point("cstr", (1, 1), solver=solver, executable="/gams/52.2/gams")
    assert result["accepted"] and result["objective"] == 1
    assert result["gams_solver"] == solvers.GAMS_SOLVERS[solver]
    assert result["gams_solve_status"] == 1 and result["gams_model_status"] == 2
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
