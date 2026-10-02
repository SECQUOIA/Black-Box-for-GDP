"""Partial GDP updates cannot invent completion clocks or substitute old solvers."""

import json

import pytest

from nlp_cost_analysis import baseline_comparison, baseline_record


def source(path, rows, nlp):
    path.mkdir()
    (path / "summary.json").write_text(json.dumps({"results": rows}))
    (path / "run.json").write_text(json.dumps({"cpu": 2, "host": "dantzig.ecn.purdue.edu",
                                              "created_utc": nlp}))


def row(method, objective, nlp="baron", status="finished"):
    return {"case": "column", "cstr_size": None, "instance_id": "column", "method": method,
            "objective": objective, "has_feasible_solution": True, "status": status,
            "method_wall_s": 2, "template_wall_s": .1,
            "global_optimality_certified": method == "hull", "reported_lower_bound": objective,
            "solver_policy": {"nlp": nlp, "mip": "highs"}}


def test_partial_selection_omits_running_and_old_gdpopt_but_keeps_cross_source_bound_audit(tmp_path):
    new, old = tmp_path / "new", tmp_path / "old"
    source(new, [row("ric", 1), row("gloa", .5, status="running")], "new")
    source(old, [row("ric", 9, "ipopt"), row("gloa", 9, "ipopt"), row("hull", 2)], "old")
    selection = {"sources": [{"directory": str(new), "methods": ["ric", "gloa"]},
                             {"directory": str(old), "methods": ["hull"]}]}
    (tmp_path / "selection.json").write_text(json.dumps(selection))
    rows = baseline_comparison(tmp_path, tmp_path, [{"spec": {"case_name": "column", "grid_size": None}, "target": 1}])
    assert [r["method"] for r in rows] == ["ric", "hull"]
    assert rows[0]["objective"] == 1 and rows[0]["nlp_solver"] == "baron"
    assert rows[0]["measured_total_with_preparation_s"] == 2.1
    assert rows[1]["bound_conflict_with_saved_solution"]
    assert not rows[1]["global_optimality_certified"]


def test_duplicate_selected_methods_are_rejected(tmp_path):
    new, old = tmp_path / "new", tmp_path / "old"
    source(new, [row("ric", 1)], "new")
    source(old, [row("ric", 9, "ipopt")], "old")
    (tmp_path / "selection.json").write_text(json.dumps({"sources": [
        {"directory": str(p), "methods": ["ric"]} for p in (new, old)]}))
    with pytest.raises(ValueError, match="Duplicate GDP"):
        baseline_comparison(tmp_path, tmp_path, [{"spec": {"case_name": "column", "grid_size": None}, "target": 1}])


def test_unselected_historical_incumbent_still_invalidates_a_reported_bound(tmp_path):
    old = tmp_path / "old"
    source(old, [row("ric", 1, "ipopt"), row("hull", 2)], "old")
    (tmp_path / "selection.json").write_text(json.dumps({"sources": [
        {"directory": str(old), "methods": ["hull"]}]}))
    rows = baseline_comparison(tmp_path, tmp_path, [{"spec": {"case_name": "column", "grid_size": None}, "target": 1}])
    assert len(rows) == 1 and rows[0]["method"] == "hull"
    assert rows[0]["bound_conflict_with_saved_solution"]
    assert rows[0]["bound_evidence_method"] == "ric"
    assert rows[0]["bound_evidence_source_directory"] == str(old)


def test_better_than_lookup_counts_as_attainment_without_changing_historical_exact_match():
    record = baseline_record(row("loa", 2.82935061823614), 2.829394057)
    assert record["target_attained"]
    assert not record["target_hit"]
    invalid = row("loa", 1)
    invalid["has_feasible_solution"] = False
    record = baseline_record(invalid, 2)
    assert not record["target_attained"] and not record["target_hit"]
