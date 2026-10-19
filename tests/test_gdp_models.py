"""GDP mappings, infeasible logic, and acceptance of actual solver results."""
# ruff: noqa: E402 -- optional GDP dependencies must be checked before imports.

import math
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

pyo = pytest.importorskip("pyomo.environ")
pytest.importorskip("networkx")

from pyomo.common.errors import InfeasibleConstraintException
from pyomo.gdp import Disjunction

from gdp_models import build_gdp, evaluate_point, prepare_nlp
from gdp_models.models import PreparedNLP


@pytest.fixture
def sources():
    root = Path(__file__).resolve().parents[1] / "external"
    if not all((root / name / ".git").exists() for name in ("dsda-gdp", "ld-sda-dynamic")):
        pytest.skip("Initialize the original GDP submodules to run model tests")


@pytest.mark.parametrize("case,point", [
    ("cstr", (3, 1)), ("column", (13, 4)),
    ("small_batch", (2, 2, 1)), ("dynamic", (1, 4)),
])
def test_original_gdp_becomes_continuous_subproblem(sources, case, point):
    original = build_gdp(case)
    assert list(original.component_data_objects(Disjunction, active=True))
    prepared = prepare_nlp(case, point)
    m = prepared.model
    assert m is not original
    assert not list(m.component_data_objects(Disjunction, active=True))
    assert not [v for v in m.component_data_objects(pyo.Var, active=True)
                if (v.is_integer() or v.is_binary()) and not v.fixed]
    assert prepared.metadata["source"]["files_sha256"]
    if case == "cstr":
        assert pyo.value(m.YF[3]) and pyo.value(m.YR[1])
        assert [i for i in m.N if pyo.value(m.YP_is_cstr[i].indicator_var)] == [1, 2, 3]
    elif case == "column":
        # External coordinates are positions, not physical tray numbers.
        assert pyo.value(m.YR[14]) and pyo.value(m.YB[5])
    elif case == "small_batch":
        assert all(pyo.value(m.Y[k, j]) for k, j in zip(point, m.j))
    else:
        assert [next(k for k in m.mode if pyo.value(m.stage_mode[s, k].indicator_var))
                for s in m.stage] == [1, 2, 2, 2, 3, 3, 3, 3, 3]
        assert len(m.t1) == 91
        assert prepared.metadata["preparation_id"]


@pytest.mark.parametrize("case,point", [
    ("cstr", (1, 5)), ("column", (1, 15)), ("dynamic", (4, 4)),
])
def test_invalid_gdp_logic_is_not_solved(sources, case, point):
    with pytest.raises(InfeasibleConstraintException):
        prepare_nlp(case, point)
    result = evaluate_point(case, point, solver="ipopt")
    assert result["status"] == "preprocessing_infeasible"
    assert result["rejection_phase"] == "logical"
    assert result["objective"] is None
    assert result["solve_wall_s"] == 0
    assert result["total_wall_s"] > 0


def test_column_fbbt_rejection_is_distinct_from_logical_rejection(sources, monkeypatch):
    def no_solver(*args, **kwargs):
        pytest.fail("Rejected configurations must not construct a solver")

    monkeypatch.setattr("gdp_models.evaluation.optimizer_for", no_solver)
    with pytest.raises(InfeasibleConstraintException, match="minimum_num_trays"):
        prepare_nlp("column", (8, 8))
    logical = evaluate_point("column", (1, 15), solver="ipopt")
    algebraic = evaluate_point("column", (8, 8), solver="ipopt")
    assert logical["rejection_phase"] == "logical"
    assert algebraic["rejection_phase"] == "preprocessing"
    for result in (logical, algebraic):
        assert result["status"] == "preprocessing_infeasible"
        assert result["termination"] == "not_solved"
        assert result["solve_wall_s"] == 0
        assert result["accepted"] is False and result["objective"] is None


@pytest.mark.parametrize("point", [(0, 1), (6, 1), (2,), (2.5, 1), (math.nan, 1)])
def test_bad_coordinates_rejected(sources, point):
    with pytest.raises(ValueError):
        prepare_nlp("cstr", point)


def test_cstr30_initialization_is_explicit(sources):
    prepared = prepare_nlp("cstr", (30, 30), cstr_size=30)
    assert prepared.metadata["initialization"] == "constructor_defaults (no upstream saved initialization)"
    with pytest.raises(FileNotFoundError, match="No saved initialization"):
        prepare_nlp("cstr", (30, 30), cstr_size=30, initialization="saved")


def test_dynamic_all_mode_one_boundary(sources):
    m = prepare_nlp("dynamic", (9, 9)).model
    assert all(pyo.value(m.stage_mode[s, 1].indicator_var) for s in m.stage)


def test_dynamic_discretizes_once_and_clones_independent_starts(sources, monkeypatch):
    from gdp_models import models

    models.dynamic_template.cache_clear()
    calls = []
    original = models._discretize_dynamic

    def discretize(model):
        calls.append(model)
        original(model)

    monkeypatch.setattr(models, "_discretize_dynamic", discretize)
    try:
        first = prepare_nlp("dynamic", (1, 4))
        template = models.dynamic_template()
        var = next(v for v in first.model.component_data_objects(pyo.Var)
                   if not v.fixed and not v.is_binary())
        start = var.value
        var.set_value(1 if start is None else start + 1, skip_validation=True)
        second = prepare_nlp("dynamic", (2, 5))
        assert len(calls) == 1
        assert second.model.find_component(var.name).value == start
        assert template.model.find_component(var.name).value == start
        assert list(template.model.component_data_objects(Disjunction, active=True))
        assert first.metadata["preparation_id"] == second.metadata["preparation_id"]
        assert template.preparation["dae_wall_s"] > 0
        assert template.preparation["included_in_point_total_wall_s"] is False
    finally:
        models.dynamic_template.cache_clear()


@pytest.mark.parametrize("termination,value,accepted", [
    ("optimal", 1, True), ("locallyOptimal", 1, True),
    ("maxTimeLimit", 1, False), ("infeasible", 1, False),
    ("optimal", 0, False), ("optimal", math.nan, False),
])
def test_solver_status_and_primal_feasibility_both_required(monkeypatch, termination, value, accepted):
    # A solver's positive status alone is insufficient: test against an
    # independent equality, including a feasible time-limit incumbent.
    m = pyo.ConcreteModel()
    m.x = pyo.Var(initialize=1)
    m.c = pyo.Constraint(expr=m.x == 1)
    m.obj = pyo.Objective(expr=m.x)
    prepared = PreparedNLP(m, (1, 1), {}, {}, [m.c])
    monkeypatch.setattr("gdp_models.evaluation.prepare_nlp", lambda *a, **k: prepared)

    def solve(*args, **kwargs):
        m.x.set_value(value, skip_validation=True)
        return SimpleNamespace(solver=SimpleNamespace(
            termination_condition=termination, status="ok", message="test solver"
        ))

    monkeypatch.setattr(pyo, "SolverFactory", lambda *a, **k: SimpleNamespace(solve=solve))
    result = evaluate_point("cstr", (1, 1), solver="ipopt")
    assert result["accepted"] is accepted
    assert result["objective"] == (1 if accepted else None)


def test_solver_exception_is_not_a_success(monkeypatch):
    m = pyo.ConcreteModel()
    prepared = PreparedNLP(m, (1, 1), {}, {}, [])
    monkeypatch.setattr("gdp_models.evaluation.prepare_nlp", lambda *a, **k: prepared)

    def fail(*args, **kwargs):
        raise RuntimeError("solver unavailable")

    monkeypatch.setattr(pyo, "SolverFactory", lambda *a, **k: SimpleNamespace(solve=fail))
    result = evaluate_point("cstr", (1, 1), solver="ipopt")
    assert result["status"] == "solver_error"
    assert result["objective"] is None and not result["accepted"]
    assert result["total_wall_s"] >= result["solve_wall_s"] >= 0


def test_cli_stdout_is_json_even_with_upstream_warnings(sources):
    result = subprocess.run([
        sys.executable, "-m", "gdp_models", "--case", "cstr",
        "--point", "1,5", "--solver", "ipopt",
    ], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "preprocessing_infeasible"
