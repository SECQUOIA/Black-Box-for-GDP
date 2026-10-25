"""Do not infer returned solutions from starts, objectives, or status text."""
import hashlib
import json
import subprocess
import sys
import zipfile

import pytest
from scripts import analyze_process_scip_return as audit

pyo = pytest.importorskip("pyomo.environ")
from pyomo.gdp import Disjunct, Disjunction  # noqa: E402


@pytest.fixture
def returned():
    model = pyo.ConcreteModel()
    model.x = pyo.Var(bounds=(0, 3), initialize=1)
    model.unused = pyo.Var(bounds=(0, 3), initialize=2)
    model.fixed_input = pyo.Var(initialize=2)
    model.fixed_input.fix()
    model.selected = Disjunct()
    model.selected.c = pyo.Constraint(expr=model.x >= 1)
    model.inactive_choice = Disjunct()
    model.inactive_choice.c = pyo.Constraint(expr=model.x >= 3)
    model.choice = Disjunction(expr=[model.selected, model.inactive_choice])
    model.logic = pyo.LogicalConstraint(expr=model.selected.indicator_var)
    model.obj = pyo.Objective(expr=model.x)
    solution = {"objective": 1., "variables": {
        "x": 1., "unused": 2., "fixed_input": 2.,
        "selected.binary_indicator_var": 1., "inactive_choice.binary_indicator_var": 0.}}
    result = {"objective": 1., "selected_disjuncts": ["selected"], "selected_booleans": []}
    return model, solution, result


def test_checks_selected_branch_and_original_logic_without_solving(returned, monkeypatch):
    def no_solver(*args, **kwargs):
        pytest.fail("Solution verification must not construct a solver")
    monkeypatch.setattr(type(pyo.SolverFactory), "__call__", no_solver)
    checked = audit.verify_solution(*returned)
    assert checked["original_gdp_feasible"]
    assert checked["max_original_violation"] == 0
    assert checked["checks"]["logical_constraints"] == 1


def test_missing_required_value_cannot_reuse_constructor_start(returned):
    del returned[1]["variables"]["x"]
    with pytest.raises(ValueError, match="Undefined constraint"):
        audit.verify_solution(*returned)


def test_truly_unused_missing_value_is_cleared_and_disclosed(returned):
    del returned[1]["variables"]["unused"]
    checked = audit.verify_solution(*returned)
    assert returned[0].unused.value is None
    assert checked["missing_unreferenced_variables"] == ["unused"]


@pytest.mark.parametrize("variable,value", [("x", 4), ("fixed_input", 3), ("inactive_choice.binary_indicator_var", 1)])
def test_bounds_fixed_inputs_and_xor_are_checked(returned, variable, value):
    returned[1]["variables"][variable] = value
    if variable == "x":
        returned[1]["objective"] = returned[2]["objective"] = value
    with pytest.raises(ValueError):
        audit.verify_solution(*returned)


def test_saved_objective_is_not_trusted(returned):
    returned[1]["objective"] = -10
    with pytest.raises(ValueError, match="objective mismatch"):
        audit.verify_solution(*returned)


def test_better_value_does_not_silently_change_fixed_target_rule():
    assert not audit.hit(2.8, 2.9)
    assert audit.attained(2.8, 2.9)
    assert audit.hit(167427.65, 167427.66)  # Historical scale-adjusted tolerance.


def test_archive_identity_checked_before_importing_sources(tmp_path):
    path = tmp_path / "modified.zip"
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="Archive identity"):
        audit.analyze(path, tmp_path / "out")


def test_internal_member_corruption_is_rejected(tmp_path):
    prefix = audit.ARCHIVE.removesuffix(".zip") + "/"
    path = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(prefix + "run.json", b"changed")
        archive.writestr(prefix + "SHA256SUMS", hashlib.sha256(b"original").hexdigest() + "  run.json\n")
    with zipfile.ZipFile(path) as archive, pytest.raises(ValueError, match="Checksum mismatch"):
        audit.verify_archive(archive)


def test_complete_return_reproduces_and_retains_failed_jobs(tmp_path):
    output = tmp_path / "audit"
    run = subprocess.run([sys.executable, str(audit.ROOT / "scripts/analyze_process_scip_return.py"),
                          "--output", str(output)], text=True, capture_output=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    summary = json.loads((output / "summary.json").read_text())
    manifest = json.loads((output / "manifest.json").read_text())
    assert summary["jobs"] == 27 and summary["returned_feasible_solutions"] == 26
    assert summary["actual_started_benchmark_calls"] == {"highs/mip": 2368, "scip/nlp": 2342}
    assert summary["logged_benchmark_solver_calls"]["scip/nlp"] == 2341
    assert summary["new_optimization_calls_during_analysis"] == 0
    assert summary["termination_counts"] == {"optimal": 18, "error": 1, "maxTimeLimit": 8}
    assert [r["scip_target_hits"] for r in summary["by_method"]] == [1, 6, 6]
    assert all(r["jobs"] == 9 for r in summary["by_method"])
    assert len(summary["bound_conflicts"]) == 6
    assert len(manifest["sealed_files_omitted_by_packer"]) == 5
    assert manifest["terminal_jobs_fully_verifiable"] == 26
    recorded = audit.ROOT / "results/process_gdpopt_scip_20261025"
    recorded_manifest = json.loads((recorded / "manifest.json").read_text())
    files = ["solver_calls.csv", "gdp_path_events.csv", "issues.json"]
    # Cross-platform floating-point evaluation and environment metadata need not
    # have identical bytes, while the original archived journals must do so.
    if all(manifest[k] == recorded_manifest[k] for k in
           ("analysis_python", "analysis_pyomo", "analysis_system", "analysis_machine")):
        files += ["jobs.csv", "paired_baron_scip.csv", "methods.csv", "solution_checks.json", "summary.json", "manifest.json"]
    for name in files:
        assert (output / name).read_bytes() == (audit.ROOT / "results/process_gdpopt_scip_20261025" / name).read_bytes(), name
