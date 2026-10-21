"""Exact identity checks, unchanged GDP validation and one-call safety; no NLP solve."""

from pathlib import Path
import sys

import pytest

from review_diagnostics import feasibility as f
from review_diagnostics import feasibility_tautology as t
from review_diagnostics.common import ROOT, read, save

PRIOR = ROOT / "results/review_feasibility_followup_20261020"


@pytest.fixture
def original(cstr_diagnostic_sources):
    return f.verify_input(PRIOR)


def test_only_three_proved_identities_change_and_original_remains_intact(original, tmp_path):
    reference, _, _ = original
    untouched = t.inventory(reference)
    nlp, proof = t.preprocess(reference)
    assert t.inventory(reference) == untouched
    assert proof["active_constraint_sets_identical"] is False
    assert proof["remaining_constraints_identical"]
    for key in ("variables", "booleans", "objectives", "logic"):
        assert proof["before"][key] == proof["after"][key]
    changed = {name for name in proof["before"]["constraints"] if proof["before"]["constraints"][name] != proof["after"]["constraints"][name]}
    assert changed == set(t.CANDIDATES)
    assert all(p["exact_body"] == p["exact_lower"] == p["exact_upper"] == "1" for p in proof["omitted_identities"])
    _, before = t.write_nl(f.prepare_fixed_nlp(reference), tmp_path / "before/model.nl")
    _, after = t.write_nl(nlp, tmp_path / "after/model.nl")
    t.check_nl_change(before, after)
    assert (after["variables"], after["equalities"]) == (156, 155)


@pytest.mark.parametrize("defect", ["free_binary", "undefined", "continuous", "fractional", "false", "near", "sub_float_epsilon", "inequality", "unfixed_boolean"])
def test_same_name_is_not_sufficient_for_omission(original, defect):
    from gdp_models.comparison import pyo

    reference, _, _ = original
    nlp = f.prepare_fixed_nlp(reference)
    row = nlp.find_component(t.CANDIDATES[0])
    variable = nlp.YF_asbinary[1]
    if defect == "free_binary":
        variable.unfix()
    elif defect == "undefined":
        variable.set_value(None)
    elif defect == "continuous":
        nlp.diagnostic_continuous = pyo.Var(initialize=0)
        row.set_value((1, row.body + nlp.diagnostic_continuous, 1))
    elif defect == "fractional":
        variable.set_value(1e-12, skip_validation=True)
    elif defect == "unfixed_boolean":
        nlp.YF[1].unfix()
    elif defect == "inequality":
        row.set_value(row.body <= 1)
    else:
        addition = {"false": 1, "near": 1e-12, "sub_float_epsilon": 1e-20}[defect]
        row.set_value((1, row.body + addition, 1))
    with pytest.raises(ValueError):
        t.prove_identities(nlp)
    assert all(nlp.find_component(name).active for name in t.CANDIDATES)


def test_original_gdp_rechecks_omitted_logic_and_discrete_configuration(original):
    reference, before, _ = original
    nlp, _ = t.preprocess(reference)
    restored, check = t.original_check(nlp, before["discrete_configuration"])
    assert all(row["active_on_original_GDP"] and row["independently_checked"] and row["violation"] == 0 for row in check["omitted_identities_rechecked_on_original_GDP"])
    assert len(check["active_constraint_names"]) == len(before["active_constraint_names"])
    assert not check["numerically_feasible_under_stated_residual_test"]  # W03 exceeds 1e-8.
    nlp.YF_asbinary[1].set_value(1)
    _, bad = t.original_check(nlp, before["discrete_configuration"])
    assert not bad["configuration_matches"]
    assert not bad["numerically_feasible_under_stated_residual_test"]
    assert any(r["violation"] > 0 for r in bad["omitted_identities_rechecked_on_original_GDP"])


def test_prewritten_nl_symbol_map_loads_actual_returned_values(tmp_path, pyomo_env):
    from pyomo.opt import SolverResults, SolverStatus, TerminationCondition
    from gdp_models.comparison import pyo

    m = pyo.ConcreteModel()
    m.x = pyo.Var(initialize=2)
    m.c = pyo.Constraint(expr=m.x >= 1)
    m.o = pyo.Objective(expr=m.x**2)
    smap, info = t.write_nl(m, tmp_path / "model.nl")
    assert info["variables"] == 1
    result = SolverResults()
    result.solver.status = SolverStatus.ok
    result.solver.termination_condition = TerminationCondition.optimal
    result.solution.add().variable["v0"] = {"Value": 1.25}
    assert t.load_returned(m, result, smap)
    assert m.x.value == 1.25


def test_no_or_incomplete_returned_vector_cannot_reuse_initial_values(tmp_path, pyomo_env):
    from pyomo.opt import SolverResults, SolverStatus
    from gdp_models.comparison import pyo

    m = pyo.ConcreteModel()
    m.x = pyo.Var(initialize=2)
    m.o = pyo.Objective(expr=m.x**2)
    smap, _ = t.write_nl(m, tmp_path / "model.nl")
    result = SolverResults()
    result.solver.status = SolverStatus.ok
    assert not t.load_returned(m, result, smap)
    result.solution.add()
    with pytest.raises(ValueError, match="Incomplete"):
        t.load_returned(m, result, smap)
    assert m.x.value == 2


def test_no_solution_assessment_has_no_new_objective(tmp_path):
    save(tmp_path / "provenance.json", {"lower_bound": 3.5})
    before = {"objective": 2.8, "maximum_unscaled_primal_violation": 1e-7, "numerically_feasible_under_stated_residual_test": True, "configuration_matches": True, "logic_valid": True, "largest_residuals": []}
    save(tmp_path / "before_residuals.json", before)
    save(tmp_path / "worker_result.json", {"solution_loaded": False, "solver_status": "ok", "termination": "optimal"})
    summary = t.assess(tmp_path)
    assert summary["assessment"]["objective"] is None
    assert not summary["tightened_feasibility_passed"]
    assert summary["bound_discrepancy_persists"] is None
    assert not (tmp_path / "solution.json").exists()


def test_existing_output_and_call_marker_prevent_invocation(tmp_path, pyomo_env):
    with pytest.raises(FileExistsError):
        t.prepare(PRIOR, tmp_path, Path(sys.executable))
    save(tmp_path / "solver_call.json", {"test_marker": True})
    with pytest.raises(FileExistsError, match="already has"):
        t.worker(tmp_path)


@pytest.mark.parametrize("timed_out", [False, True])
def test_controller_never_retries_even_without_a_point(tmp_path, monkeypatch, timed_out):
    output = tmp_path / "new"
    calls = []

    def prepare(*args):
        output.mkdir()

    def bounded(command, log, seconds):
        calls.append(command)
        assert seconds == 300
        return {"timed_out": timed_out, "returncode": -9 if timed_out else 0}

    monkeypatch.setattr(t, "prepare", prepare)
    monkeypatch.setattr(t, "bounded", bounded)
    monkeypatch.setattr(t, "assess", lambda directory: None)
    monkeypatch.setattr(t, "seal", lambda directory: None)
    t.run(PRIOR, output, Path(sys.executable))
    assert len(calls) == 1
    assert read(output / "execution.json")["timed_out"] == timed_out


def test_retained_returned_point_replays_without_solver(monkeypatch, cstr_diagnostic_sources):
    from gdp_models.comparison import pyo

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved-result replay must never construct a solver")

    monkeypatch.setattr(pyo, "SolverFactory", forbidden)
    directory = ROOT / "results/review_feasibility_tautology_20261020"
    report = t.verify(directory, PRIOR)
    assert report["returned_point_rechecked"] and report["new_solver_calls"] == 0
    assessment = report["summary"]["assessment"]
    assert assessment["maximum_unscaled_primal_violation"] <= 1e-8
    assert assessment["bound_minus_witness"] > assessment["audit_tolerance"]


def test_replay_rejects_summary_disagreeing_with_independent_check(tmp_path, cstr_diagnostic_sources):
    import shutil

    directory = tmp_path / "copied_result"
    shutil.copytree(ROOT / "results/review_feasibility_tautology_20261020", directory)
    summary = read(directory / "summary.json")
    summary["tightened_feasibility_passed"] = False
    save(directory / "summary.json", summary)
    # Even a newly hashed metadata file cannot override independent GDP validation.
    t.seal(directory)
    with pytest.raises(ValueError, match="Summary differs"):
        t.verify(directory, PRIOR)
