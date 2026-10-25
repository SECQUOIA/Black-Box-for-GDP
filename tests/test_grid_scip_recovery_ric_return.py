"""Keep failed attempts, target mismatches and recovery costs visible."""

from copy import deepcopy
import json
import subprocess
import sys
import zipfile

import pytest

from scripts import analyze_grid_scip_recovery_ric_return as audit


@pytest.fixture
def selection():
    baseline = [r for r in json.loads((audit.ROOT / 'results/grid_gdpopt_scip_20261025/jobs.json').read_text())
                if r['method'] == 'ric']
    path = audit.PACKAGES / 'grid_gdpopt_scip_recovery_ric_dantzig_20261025.zip'
    with zipfile.ZipFile(path) as z:
        selected = json.loads(z.read(path.stem + '/RECOVERY_SELECTION.json'))
    return selected, baseline


def test_missing_failed_attempt_is_not_excluded(selection):
    chosen, baseline = deepcopy(selection)
    chosen['jobs'].pop()
    with pytest.raises(ValueError, match='Missing or duplicate'):
        audit.verify_selection(chosen, baseline)


def test_timeout_cannot_silently_enter_error_recovery(selection):
    chosen, baseline = deepcopy(selection)
    timeout = next(r for r in baseline if r['termination'] == 'maxTimeLimit')
    chosen['jobs'][0]['grid_name'] = timeout['grid_name']
    with pytest.raises(ValueError, match='original errors'):
        audit.verify_selection(chosen, baseline)


def test_original_incumbent_hit_cannot_be_removed_from_pairing(selection):
    chosen, baseline = deepcopy(selection)
    hit = next(r for r in chosen['jobs'] if r['target_hit_verified'])
    hit['target_hit_verified'] = False
    with pytest.raises(ValueError, match='target_hit_verified'):
        audit.verify_selection(chosen, baseline)


def test_return_audit_keeps_false_optimal_and_time_limited_target_hits(tmp_path):
    result = subprocess.run([sys.executable, str(audit.ROOT / 'scripts/analyze_grid_scip_recovery_ric_return.py'),
                             '--output', str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['recovery']['jobs'] == 12
    assert summary['recovery']['target_hits'] == 10
    assert summary['recovery']['errors'] == 0
    assert summary['recovery']['time_limits'] == 3
    assert summary['original_ric_21']['target_hits'] == 7
    assert summary['descriptive_ric_21_after_error_recovery']['target_hits'] == 16
    assert summary['original_ric_21']['errors'] == 12
    assert summary['benchmark_scip_mip_calls'] == 18349
    assert summary['benchmark_nlp_calls'] == summary['network_retry_events'] == 0
    assert summary['cumulative_ric_worker_s_all_original_and_recovery_attempts'] > summary['descriptive_ric_21_after_error_recovery']['worker_wall_s']
    diagnoses = json.loads((tmp_path / 'target_mismatch_diagnostics.json').read_text())
    assert len(diagnoses) == 5
    assert all(r['original_gdp_witness']['target_hit_verified'] for r in diagnoses)
    assert all(r['discrete_selections'] == 1 and r['before_subproblem_callbacks'] == 0 for r in diagnoses)
    assert all(not r['local_presolve_allows_solver'] and r['local_fbbt_error'] for r in diagnoses)
