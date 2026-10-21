"""Residual/configuration gating, fixed NLP mapping and external wall limits."""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from review_diagnostics import feasibility as f
from review_diagnostics.common import ROOT, bounded, read, save


@pytest.fixture
def witness(cstr_diagnostic_sources):
    return f.verify_input(ROOT / "results/review_diagnostics_20261020")


def test_saved_w03_residual_and_fixed_disjunct_nlp_correspond(witness):
    from gdp_models.comparison import pyo, DESCEND

    m, before, _ = witness
    assert before["objective"] == pytest.approx(2.82935061823614, abs=1e-12)
    assert before["maximum_unscaled_primal_violation"] == pytest.approx(
        5.634494497502862e-7, abs=1e-12
    )
    assert before["numerically_feasible_under_stated_residual_test"]
    assert not f.independent_check(m, 1e-8)[
        "numerically_feasible_under_stated_residual_test"
    ]
    nlp = f.prepare_fixed_nlp(m)
    assert set(before["active_constraint_names"]) == {
        c.name for c in nlp.component_data_objects(pyo.Constraint, active=True)
    }
    for v in nlp.component_data_objects(pyo.Var, descend_into=DESCEND):
        original = m.find_component(v.name)
        assert (v.lb, v.ub) == (original.lb, original.ub)
        if v.is_integer():
            assert v.fixed
        else:
            assert v.fixed == original.fixed
    assert str(nlp.obj.expr) == str(m.obj.expr)


def test_discrete_mismatch_fails_even_when_numerical_residual_passes(witness):
    m, before, _ = witness
    expected = dict(before["discrete_configuration"])
    expected["YR_is_recycle[15].binary_indicator_var"] = 0
    check = f.independent_check(m, 1e-5, expected)
    assert check["maximum_unscaled_primal_violation"] < 1e-5
    assert not check["configuration_matches"]
    assert not check["numerically_feasible_under_stated_residual_test"]


def test_false_logic_and_constraint_violation_fail(witness):
    m, _, _ = witness
    m.Q[1].set_value(20, skip_validation=True)
    c = f.independent_check(m, 1e-5)
    assert not c["numerically_feasible_under_stated_residual_test"]
    assert any(x["violation"] > 1 for x in c["bounds"])
    m.YF[15].set_value(False)
    assert not f.independent_check(m, 1e-5)["logic_valid"]


def test_optimal_solver_report_cannot_override_failed_residual(
    witness, tmp_path, monkeypatch
):
    from gdp_models.comparison import pyo

    m, before, provenance = witness
    monkeypatch.setattr(f, "verify_input", lambda directory: (m, before, provenance))
    prepare = f.prepare_fixed_nlp

    def fake_prepare(model):
        nlp = prepare(model)
        monkeypatch.setattr(nlp.solutions, "load_from", lambda result: None)
        return nlp

    monkeypatch.setattr(f, "prepare_fixed_nlp", fake_prepare)
    passed_options = []

    class FakeSolver:
        def solve(self, model, **kwargs):
            passed_options.append(kwargs["options"])
            return SimpleNamespace(
                solver=SimpleNamespace(status="ok", termination_condition="optimal"),
                solution=[1],
            )

    monkeypatch.setattr(pyo, "SolverFactory", lambda *a, **k: FakeSolver())
    dest = tmp_path / "feasibility/attempt_1"
    dest.mkdir(parents=True)
    f.polish_worker(tmp_path, 1, sys.executable)
    r = read(dest / "result.json")
    assert (
        r["solver_status"] == "ok"
        and r["termination"] == "optimal"
        and r["solution_loaded"]
    )
    assert not r["independent_residual_check"] and not r["new_witness_available"]
    assert set(passed_options[0]) == {"option_file_name"}
    assert (
        "acceptable_iter 0\n" in Path(passed_options[0]["option_file_name"]).read_text()
    )


def test_external_deadline_kills_worker(tmp_path):
    report = bounded(
        [sys.executable, "-c", "import time;time.sleep(5)"], tmp_path / "child.log", 0.1
    )
    assert report["timed_out"] and report["returncode"] != 0
    assert report["wall_s"] < 3


def test_attempt_cannot_be_repeated_or_retry_an_interface_error(tmp_path, pyomo_env):
    first = tmp_path / "feasibility/attempt_1"
    save(first / "solver_call.json", {"call_started": True})
    with pytest.raises(FileExistsError, match="already invoked"):
        f.polish_worker(tmp_path, 1, sys.executable)
    save(
        first / "result.json",
        {
            "error": "unsupported option",
            "solution_loaded": False,
            "new_witness_available": False,
        },
    )
    with pytest.raises(ValueError, match="second call requires"):
        f.polish_worker(tmp_path, 2, sys.executable)
