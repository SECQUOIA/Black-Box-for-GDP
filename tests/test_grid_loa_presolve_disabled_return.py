"""Distinguish failed GAMS compilation from an actual SCIP execution."""
import json
from unittest.mock import patch

from scripts import analyze_grid_loa_presolve_disabled_return as audit


def test_return_audit_is_solver_free_reproducible_and_preserves_missing_results(tmp_path):
    with patch('subprocess.Popen', side_effect=AssertionError('No external process in audit')):
        first = audit.analyze(tmp_path / 'first')
        second = audit.analyze(tmp_path / 'second')
    assert first == second
    assert first['interface_call_attempts'] == first['gams_job_starts'] == 1
    assert first['confirmed_scip_invocations'] == first['returned_solution_count'] == first['actual_full_loa_runs'] == 0
    assert first['presolve_bypass_entered_evaluation'] and first['gams_compilation_error_61_abs_in_nlp']
    assert first['fixed_configurations_not_run'] == 5 and not first['scip_runtime_version_verified']
    compared = json.loads((tmp_path / 'first/comparison.json').read_text())
    assert {r['grid_name'] for r in compared} == {'holder_table', 'michalewicz', 'shubert'}
    assert all(r['new_objective'] is None and r['new_target_hit'] is None for r in compared)
    for path in (tmp_path / 'first').rglob('*'):
        if path.is_file():
            assert path.read_bytes() == (tmp_path / 'second' / path.relative_to(tmp_path / 'first')).read_bytes()


def test_interface_configuration_does_not_prove_scip_execution():
    result = dict(actual_solver_calls=1, returned_solution_count=0, worker_wall_s=0.6)
    calls = [dict(solver='scip', mtype='nlp', status='error', wall_s=0.4)]
    evidence = audit.call_evidence(result, calls, 'solver=scip\nNLP subproblem\n', '')
    assert evidence['interface_call_attempts'] == 1
    assert evidence['confirmed_scip_invocations'] == evidence['gams_job_starts'] == 0
    assert not evidence['gams_compilation_error_61_abs_in_nlp']
