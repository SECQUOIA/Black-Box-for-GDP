"""Reject missing/inconsistent returned vectors in the solver-free audit."""
from copy import deepcopy
import zipfile

import pytest

pytest.importorskip("pyomo.environ")
from scripts import analyze_grid_scip_return as audit


@pytest.fixture
def returned():
    name = next(n for n in audit.ARCHIVES if "minlp" in n)
    with zipfile.ZipFile(audit.ROOT / "results/archives" / name) as archive:
        root = name.removesuffix(".zip") + "/benchmark/ackley/bigm/"
        return audit.read_json(archive, root + "solution.json"), audit.read_json(archive, root + "result.json")


def test_valid_return_is_independently_recomputed(returned):
    solution, result = returned
    checked = audit.verify_solution("ackley", solution, result)
    assert checked["grid_point"] == [15,15]
    assert checked["target_hit_verified"] and checked["original_gdp_feasible"]
    assert checked["analytic_grid_points_checked"] == 961


def test_missing_variable_cannot_reuse_model_initialization(returned):
    solution, result = deepcopy(returned)
    del solution["variables"]["x"]
    with pytest.raises(ValueError, match="Missing original variables"):
        audit.verify_solution("ackley", solution, result)


def test_inconsistent_physical_coordinates_are_rejected(returned):
    solution, result = deepcopy(returned)
    solution["variables"]["x"] += 0.01
    with pytest.raises(ValueError, match="Invalid original GDP"):
        audit.verify_solution("ackley", solution, result)


def test_two_selected_disjuncts_are_rejected(returned):
    solution, result = deepcopy(returned)
    solution["variables"]["Xchoice[14].binary_indicator_var"] = 1
    with pytest.raises(ValueError, match="Invalid XOR"):
        audit.verify_solution("ackley", solution, result)


def test_forged_objective_is_rejected(returned):
    solution, result = deepcopy(returned)
    solution["objective"] = -1
    with pytest.raises(ValueError, match="Invalid original GDP"):
        audit.verify_solution("ackley", solution, result)


def test_reported_target_flag_is_not_trusted(returned):
    solution, result = deepcopy(returned)
    result["target_hit"] = False
    with pytest.raises(ValueError, match="target flag"):
        audit.verify_solution("ackley", solution, result)


def test_archive_identity_is_checked_before_processing(tmp_path):
    path = tmp_path / "changed.zip"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="identity mismatch"):
        audit.audit_archive(path, "0" * 64)
