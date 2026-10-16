"""Regressions for actual Pyomo failures; no benchmark timing claims."""
import importlib
import logging
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest
from pyomo.common.errors import IntervalException
from pyomo.contrib.gdpopt import util
from pyomo.contrib.gdpopt.loa import GDP_LOA_Solver
from pyomo.core.expr.numeric_expr import PowExpression

import grid_gdp_benchmark as runner
from gdp_models.grid import build_grid_gdp
from gdp_models.grid_retry_fixes import PROFILE, corrected_gdpopt


def subproblem(name, i, j):
    m = build_grid_gdp(name, verify_csv=False)
    m.x.set_value(pyo.value(m.gx[i]))
    m.y.set_value(pyo.value(m.gy[j]))
    m.u = pyo.Block()
    m.u.algebraic_variable_list = [m.x, m.y]
    util.move_nonlinear_objective_to_constraints(m.u, logging.getLogger(__name__))
    for k in m.I:
        m.Xchoice[k].indicator_var.fix(k == i)
        m.Ychoice[k].indicator_var.fix(k == j)
    pyo.TransformationFactory("gdp.fix_disjuncts").apply_to(m)
    return m


@pytest.mark.parametrize("name,point", [
    ("camel3", (1, 0)), ("dropwave", (0, 1)), ("sum_of_squares", (0, 10))])
def test_reproduces_archived_error_then_validates_every_grid_point(name, point):
    fbbt = importlib.import_module("pyomo.contrib.fbbt.fbbt")
    with pytest.raises(IntervalException, match="fractional power"):
        fbbt.fbbt(subproblem(name, *point))
    original = fbbt._prop_bnds_root_to_leaf_map[PowExpression]
    with corrected_gdpopt(PROFILE, name, "ric") as audit:
        for i in range(31):
            for j in range(31):
                m = subproblem(name, i, j)
                fbbt.fbbt(m)
                for v, expected in [(m.x, pyo.value(m.gx[i])), (m.y, pyo.value(m.gy[j]))]:
                    assert v.lb - 1e-6 <= expected <= v.ub + 1e-6
                expected = pyo.value(m.obj)
                assert m.u.objective_value.lb <= expected + 1e-6
                assert m.u.objective_value.ub is None or expected <= m.u.objective_value.ub + 1e-6
        assert audit["fixed_exponent_bound_resets"] > 0
    assert fbbt._prop_bnds_root_to_leaf_map[PowExpression] is original


def test_variable_fractional_exponent_domain_error_is_not_suppressed():
    fbbt = importlib.import_module("pyomo.contrib.fbbt.fbbt")
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(-3, -2))
    m.y = pyo.Var(bounds=(.25, .75))
    m.c = pyo.Constraint(expr=m.x**m.y <= 4)
    with corrected_gdpopt(PROFILE, "camel3", "ric"):
        with pytest.raises(IntervalException):
            fbbt.fbbt(m)


def test_alpine_loa_finishes_at_zero_without_differentiating_abs_zero():
    if not pyo.SolverFactory("highs").available(False):
        pytest.skip("Native HiGHS is only used for the local algorithm regression")
    original = GDP_LOA_Solver._add_cuts_to_discrete_problem
    with corrected_gdpopt(PROFILE, "alpine1", "loa") as audit:
        m = build_grid_gdp("alpine1", verify_csv=False)
        result = pyo.SolverFactory("gdpopt.loa").solve(
            m, mip_solver="highs", nlp_solver="highs", time_limit=20,
            force_subproblem_nlp=True, init_algorithm="set_covering")
        assert str(result.solver.termination_condition) == "optimal"
        assert pyo.value(m.obj) == 0
        assert audit["loa_cuts_skipped_after_bound_convergence"] == 1
    assert GDP_LOA_Solver._add_cuts_to_discrete_problem is original


def test_unconverged_loa_still_adds_cuts_and_patch_restores_on_error(monkeypatch):
    def cuts(*args):
        raise RuntimeError("regular cuts called")
    monkeypatch.setattr(GDP_LOA_Solver, "_add_cuts_to_discrete_problem", cuts)
    solver = SimpleNamespace(LB=0, UB=1, bounds_converged=lambda config: False)
    with pytest.raises(RuntimeError, match="regular cuts"):
        with corrected_gdpopt(PROFILE, "alpine1", "loa"):
            GDP_LOA_Solver._add_cuts_to_discrete_problem(solver, None, None, None, None, None)
    assert GDP_LOA_Solver._add_cuts_to_discrete_problem is cuts


def test_profile_rejects_other_grids_and_pyomo_versions(monkeypatch):
    with pytest.raises(ValueError, match="ten diagnosed"):
        with corrected_gdpopt(PROFILE, "ackley", "loa"):
            pass
    monkeypatch.setattr("pyomo.version.version", "6.11.0")
    with pytest.raises(ValueError, match="requires Pyomo"):
        with corrected_gdpopt(PROFILE, "camel3", "loa"):
            pass


def test_profile_does_not_accept_network_or_unrelated_error(tmp_path, monkeypatch):
    # A changed profile must never silently broaden the exact failed-pair plan.
    monkeypatch.setattr(runner, "select_error_jobs", lambda *a: (
        {"config": {}}, [{"grid_name": "easom", "method": "ric", "error_kind": "network"}]))
    with pytest.raises(ValueError, match="ten diagnosed"):
        runner.retry_errors(SimpleNamespace(run_dir=tmp_path, error_kind="all", dry_run=True,
                                           retry_fix_profile=PROFILE))


@pytest.mark.parametrize("name", ["camel3", "dropwave", "sum_of_squares"])
@pytest.mark.parametrize("method", ["ric", "gloa", "loa"])
def test_restricted_candidate_gdp_smoke(name, method):
    from pyomo.contrib.mcpp.pyomo_mcpp import mcpp_available

    if not pyo.SolverFactory("highs").available(False) or not mcpp_available():
        pytest.skip("Native HiGHS and MC++ are required for this local smoke test")

    @pyo.SolverFactory.register("grid_regression_highs")
    class RegressionHighs:
        def __init__(self, **kwargs):
            pass

        def available(self, **kwargs):
            return True

        def solve(self, model, **kwargs):
            # GDPopt expects a returned infeasible result on exhausted integer
            # assignments, rather than native HiGHS' default loading exception.
            result = pyo.SolverFactory("highs").solve(model, load_solutions=False)
            if len(result.solution):
                model.solutions.load_from(result)
            return result

    try:
        m = build_grid_gdp(name, verify_csv=False)
        for k in m.I:
            if k not in {0, 1, 10, 15}:
                m.Xchoice[k].indicator_var.fix(False)
                m.Ychoice[k].indicator_var.fix(False)
        with corrected_gdpopt(PROFILE, name, method):
            result = pyo.SolverFactory("gdpopt." + method).solve(
                m, mip_solver="grid_regression_highs", nlp_solver="grid_regression_highs",
                time_limit=20, init_algorithm="set_covering", force_subproblem_nlp=True)
        assert str(result.solver.termination_condition) == "optimal"
        assert abs(pyo.value(m.obj)) <= 1e-12
    finally:
        pyo.SolverFactory.unregister("grid_regression_highs")
