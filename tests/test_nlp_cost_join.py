"""Selected point costs must come from one checksummed raw observation."""

import json

import pytest

import nlp_cost_analysis as analysis


def selected_cost_fixture(directory, *, objective=2.0, selected_objective=2.0, changes=None):
    base = {"case": "cstr", "cstr_size": 5, "point": [3, 1], "solver": "gams_ipopt"}
    old = {**base, "accepted": True, "objective": 1.0, "total_wall_s": 5.0}
    new = {**base, "accepted": selected_objective is not None,
           "objective": selected_objective, "total_wall_s": 3.0}
    point = {**new, "objective": objective, "all_attempts_total_wall_s": 8.0,
             "attempt_ids": ["old", "new"], "selected_attempt_id": "new"}
    new.update(changes or {})
    (directory / "points.jsonl").write_text(json.dumps(point) + "\n")
    (directory / "attempts.jsonl").write_text("\n".join(json.dumps(entry) for entry in (
        {"attempt_id": "old", "record": old}, {"attempt_id": "new", "record": new})) + "\n")
    (directory / "dynamic_preparation.json").write_text(json.dumps([{"record": {
        "preparation_id": "one", "included_in_point_total_wall_s": False,
        "total_preparation_wall_s": .25}}]))
    # Recompute the complete valid inventory so tests reach semantic validation.
    (directory / "SHA256SUMS").write_text("".join(
        f"{analysis.sha(directory / name)}  {name}\n"
        for name in ("points.jsonl", "attempts.jsonl", "dynamic_preparation.json")))


@pytest.mark.parametrize("objective,selected_objective", [(1.0, 2.0), (None, 2.0), (2.0, None)])
def test_selected_cost_cannot_reuse_another_attempt_objective(tmp_path, objective, selected_objective):
    selected_cost_fixture(tmp_path, objective=objective, selected_objective=selected_objective)
    with pytest.raises(ValueError, match="Selected point cost differs from its source attempt"):
        analysis.load_costs(tmp_path, "gams_ipopt")


@pytest.mark.parametrize("changes", [
    {"case": "column"}, {"cstr_size": 30}, {"point": [4, 2]}, {"solver": "conopt"},
])
def test_selected_cost_must_match_source_point_identity(tmp_path, changes):
    selected_cost_fixture(tmp_path, changes=changes)
    with pytest.raises(ValueError, match="Selected point cost differs from its source attempt"):
        analysis.load_costs(tmp_path, "gams_ipopt")


@pytest.mark.parametrize("objective,selected_objective", [(2.0, 2.0), (2.0 + 5e-13, 2.0), (None, None)])
def test_true_selected_cost_objective_and_time_are_preserved(tmp_path, objective, selected_objective):
    selected_cost_fixture(tmp_path, objective=objective, selected_objective=selected_objective)
    costs, preparation = analysis.load_costs(tmp_path, "gams_ipopt")
    row = costs["cstr", 5, (3, 1)]
    assert row["objective"] == objective and row["total_wall_s"] == 3.0
    assert row["selected_attempt_id"] == "new" and preparation == .25
    assert not analysis.target_hit(row["objective"], 1.0)
