"""Follow-up allocation and interpretation tests; no real solver invocations."""

from pathlib import Path

import pytest

from review_diagnostics import feasibility_followup as followup
from review_diagnostics.common import read, save


def checked(violation=1e-9, passed=True):
    return {
        "objective": 2.8,
        "maximum_unscaled_primal_violation": violation,
        "numerically_feasible_under_stated_residual_test": passed,
        "configuration_matches": True,
        "discrete_configuration": {"indicator": 1},
        "logic_valid": True,
        "largest_residuals": [{"kind": "constraint", "name": "balance", "violation": violation}],
    }


def test_feasibility_and_discrepancy_are_separate():
    row = followup.comparison_row("point", checked(), 2.7, True, 1e-8)
    assert row["tightened_feasibility_passed"]
    assert row["bound_discrepancy_persists"] is False
    row = followup.comparison_row("point", checked(), 3.5, True, 1e-8)
    assert row["bound_discrepancy_persists"] is True
    row = followup.comparison_row("unreturned", checked(), 3.5, False, 1e-8)
    assert not row["tightened_feasibility_passed"]
    assert row["bound_discrepancy_persists"] is None
    row = followup.comparison_row("failed_residual", checked(1e-6, False), 3.5, True, 1e-8)
    assert not row["tightened_feasibility_passed"]
    assert row["bound_discrepancy_persists"] is None


@pytest.mark.parametrize("condition", ["timeout", "worker_error", "interface_error", "no_point", "solver_time_limit", "success"])
def test_no_automatic_retry_after_error_or_success(condition):
    execution = {"timed_out": False, "returncode": 0}
    result = {"error": None, "solution_loaded": True, "termination": "optimal"}
    check = checked(1e-6, False)
    if condition == "timeout":
        execution["timed_out"] = True
    elif condition == "worker_error":
        execution["returncode"] = 1
    elif condition == "interface_error":
        result["error"] = "option rejected"
    elif condition == "no_point":
        result["solution_loaded"] = False
    elif condition == "solver_time_limit":
        result["termination"] = "maxTimeLimit"
    else:
        check = checked()
    assert not followup.retry_allowed(execution, result, check)


def test_returned_unacceptable_point_is_only_retry_case():
    assert followup.retry_allowed(
        {"timed_out": False, "returncode": 0},
        {"error": None, "solution_loaded": True, "termination": "optimal"},
        checked(1e-6, False),
    )


@pytest.mark.parametrize("mode,expected_calls", [("success", 1), ("no_point", 1), ("failed_residual", 2)])
def test_controller_stops_and_never_exceeds_two_calls(tmp_path, monkeypatch, mode, expected_calls):
    directory = tmp_path / "new_allocation"
    check = checked() if mode != "failed_residual" else checked(1e-6, False)

    def prepare(dest, executable):
        dest.mkdir()
        save(dest / "manifest.json", {"selection_sha256": "fixture"})
        return checked(1e-6, True), {"lower_bound": 3.5}, str(executable)

    invocations = []

    def fake_bounded(command, log, limit):
        invocations.append(command)
        assert limit == 300
        dest = Path(log).parent
        save(dest / "solver_call.json", {"mock_only": True})
        save(dest / "solution.json", {"variables": {}})
        save(dest / "residuals.json", check)
        save(dest / "result.json", {
            "solution_loaded": mode != "no_point",
            "solver_status": "ok", "termination": "optimal", "error": None,
            "solve_wall_s": 0.01,
        })
        return {"timed_out": False, "returncode": 0, "wall_s": 0.02, "external_wall_limit_s": limit}

    monkeypatch.setattr(followup, "prepare", prepare)
    monkeypatch.setattr(followup, "bounded", fake_bounded)
    monkeypatch.setattr(followup.f, "restore", lambda data: (None, None))
    monkeypatch.setattr(followup.f, "independent_check", lambda *args: check)
    summary = followup.run(directory, Path("mock_solver_not_executed"))
    assert len(invocations) == expected_calls == summary["actual_new_NLP_calls"]
    assert summary["tightened_feasibility_passed"] == (mode == "success")
    if mode == "no_point":
        assert not (directory / "feasibility/attempt_1/solution.json").exists()
        assert (directory / "feasibility/attempt_1/unreturned_state.json").exists()
        assert summary["final_assessment"]["objective"] is None
    assert read(directory / "summary.json") == summary


def test_existing_output_directory_cannot_be_reused(tmp_path):
    with pytest.raises(FileExistsError):
        followup.prepare(tmp_path, Path("must_not_be_invoked"))
