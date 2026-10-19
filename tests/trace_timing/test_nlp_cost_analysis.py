"""Scientific accounting checks for measured NLP costs on fixed traces."""

import pytest

import nlp_cost_analysis as analysis


def fake_run(monkeypatch, case="small_batch", size=None):
    point = (2, 2, 1) if case == "small_batch" else (1, 4) if case == "dynamic" else (5, 3)
    bad = (1, 1, 1) if case == "small_batch" else (9, 2) if case == "dynamic" else (1, 5)
    monkeypatch.setattr(analysis, "problem", lambda spec: {"objective": lambda p: 10.0 if tuple(p) == point else float("inf")})
    run = {"spec": {"case_name": case, "grid_size": size, "csv_name": "test.csv", "method": "dsda",
                    "seed": 0, "n_starts": 1, "max_evaluations": 3},
           "events": [{"evaluation_index": i, "point": list(p), "phase": "initial" if i == 1 else "adaptive",
                       "completed_elapsed_s": t, "objective_wall_s": .1}
                      for i, (p, t) in enumerate(((point, 1), (bad, 3), (point, 8)), 1)],
           "completion": 10, "target": 10, "source": "test", "overhead_host": "test"}
    measured = {"all_attempts_total_wall_s": 5.0, "total_wall_s": 2.0, "attempt_count": 2,
                "accepted": True, "objective": 10.0, "attempt_ids": ["failed", "retry"], "selected_attempt_id": "retry"}
    costs = {(case, size, point): measured,
             (case, size, bad): {**measured, "accepted": False, "objective": None}}
    return run, costs


def test_all_recorded_outcomes_charged_per_callback(monkeypatch):
    run, costs = fake_run(monkeypatch)
    result, ledger = analysis.reconstruct(run, costs, 7)
    assert result["scenario_total_s"] == pytest.approx(15.7)
    assert result["scenario_first_hit_s"] == pytest.approx(2.9)
    assert result["nlp_selected_attempts_s"] == 6
    assert result["point_cost_policy"] == "selected_recorded_evaluation_all_outcomes"
    assert [row["charged_cost_s"] for row in ledger] == [2, 2, 2]
    assert ledger[0]["charged_successful_attempt_id"] == "retry"
    assert ledger[1]["charged_cost_s"] == 2
    assert ledger[1]["measured_point_all_attempts_s"] == 5
    assert result["unsuccessful_point_calls"] == 1
    assert result["preparation_s"] == 0


def test_other_retry_attempts_are_not_an_observed_callback_retry_sequence(monkeypatch):
    run, costs = fake_run(monkeypatch)
    before, before_ledger = analysis.reconstruct(run, costs, 0)
    costs[("small_batch", None, (2, 2, 1))]["all_attempts_total_wall_s"] = 5000
    after, after_ledger = analysis.reconstruct(run, costs, 0)
    assert before == after
    for original, updated in zip(before_ledger, after_ledger):
        assert original["charged_cost_s"] == updated["charged_cost_s"]
        assert original["scenario_elapsed_s"] == updated["scenario_elapsed_s"]


def test_dynamic_preparation_once_and_cache_is_explicit(monkeypatch):
    run, costs = fake_run(monkeypatch, "dynamic")
    result, ledger = analysis.reconstruct(run, costs, .25, cache=True)
    assert result["scenario_total_s"] == pytest.approx(14.05)
    assert result["scenario_first_hit_s"] == pytest.approx(3.15)
    assert result["nlp_selected_attempts_s"] == 4
    assert result["cache_hit_calls"] == 1
    assert ledger[2]["charged_cost_s"] == .1


def test_missing_feasible_cost_is_not_zero(monkeypatch):
    run, costs = fake_run(monkeypatch)
    costs.pop(("small_batch", None, (2, 2, 1)))
    result, ledger = analysis.reconstruct(run, costs, 0)
    assert result["scenario_total_s"] is None
    assert result["scenario_first_hit_s"] is None
    assert result["unmeasured_calls"] == 2
    assert ledger[0]["charged_cost_s"] is None


def test_cstr30_transfer_is_separate_from_exact_model(monkeypatch):
    run, costs = fake_run(monkeypatch, "cstr", 5)
    costs = {(case, 30, point): value for (case, _, point), value in costs.items()}
    exact, _ = analysis.reconstruct(run, costs, 0)
    proxy, _ = analysis.reconstruct(run, costs, 0, cstr_policy="cstr30_transfer")
    assert exact["scenario_total_s"] is None
    assert proxy["scenario_total_s"] == pytest.approx(15.7)
    assert proxy["strict_total_s"] is None
    assert proxy["cstr30_transferred_calls"] == 3


def test_rejected_nlp_measurement_is_charged_even_when_lookup_is_feasible(monkeypatch):
    run, costs = fake_run(monkeypatch)
    costs[("small_batch", None, (2, 2, 1))].update(accepted=False, objective=None)
    result, ledger = analysis.reconstruct(run, costs, 0)
    assert result["scenario_total_s"] == pytest.approx(15.7)
    assert result["scenario_first_hit_s"] == pytest.approx(2.9)
    assert result["nlp_selected_attempts_s"] == 6
    assert ledger[0]["charged_cost_s"] == 2
    assert ledger[0]["cost_status"] == "exact_model_measurement"
    assert result["lookup_solved"]
    assert not result["measured_path_target_hit"]
    assert result["unsuccessful_point_calls"] == 3
    assert result["unmeasured_calls"] == 0
    assert result["objective_disagreement_calls"] == 2


def test_missing_infeasible_measurement_is_not_waived(monkeypatch):
    run, costs = fake_run(monkeypatch)
    costs.pop(("small_batch", None, (1, 1, 1)))
    result, ledger = analysis.reconstruct(run, costs, 0)
    assert result["scenario_total_s"] is None
    assert ledger[1]["charged_cost_s"] is None
    assert result["unmeasured_calls"] == 1


def test_profiles_retain_all_failed_instances_and_pairing():
    rows = [{"csv_name": "test", "seed": seed, "n_starts": 3, "max_evals": 10,
             "method": method, "scenario_total_s": 10, "scenario_first_hit_s": 2 + i if seed == 0 and i < 2 else None,
             "lookup_solved": seed == 0 and i < 2}
            for seed in (0, 1) for i, method in enumerate(analysis.METHODS)]
    result = analysis.performance_ratios(rows, "scenario_first_hit_s")
    assert len(result) == 8
    assert [r["time_ratio"] for r in result] == [1.0, 1.5, None, None, None, None, None, None]
    with pytest.raises(ValueError, match="Unpaired"):
        analysis.performance_ratios(rows[:-1], "scenario_first_hit_s")


def test_killed_gdp_job_retains_watchdog_clock_and_no_solution():
    row = {"status": "hard_time_limit", "objective": None, "has_feasible_solution": False,
           "worker_wall_s": 1800.1, "template_wall_s": .25}
    result = analysis.baseline_record(row, 3)
    assert result["measured_total_with_preparation_s"] == pytest.approx(1800.35)
    assert result["clock_source"] == "worker_wall_s_watchdog"
    assert not result["target_hit"]
    assert result["objective"] is None


def test_conflicting_baron_certificate_is_flagged_without_changing_objective():
    rows = [
        {"instance_id": "cstr_30", "method": "bigm", "objective": 2.76957,
         "has_feasible_solution": True, "reported_lower_bound": .094, "global_optimality_certified": False},
        {"instance_id": "cstr_30", "method": "hull", "objective": 2.809386,
         "has_feasible_solution": True, "reported_lower_bound": 2.809386, "global_optimality_certified": True},
        {"instance_id": "other", "method": "hull", "objective": 2.809386,
         "has_feasible_solution": True, "reported_lower_bound": 2.809386, "global_optimality_certified": True},
    ]
    analysis.flag_bound_conflicts(rows)
    assert rows[1]["bound_conflict_with_saved_solution"]
    assert rows[1]["solver_reported_global_optimality_certified"]
    assert not rows[1]["global_optimality_certified"]
    assert rows[1]["objective"] == 2.809386
    assert not rows[0]["bound_conflict_with_saved_solution"]
    assert rows[2]["global_optimality_certified"]
