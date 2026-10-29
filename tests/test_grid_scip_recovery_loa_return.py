"""Verify the LOA recovery cohort and retain its false-optimal outcome."""

from copy import deepcopy
import json
import subprocess
import sys
import zipfile

import pytest

from scripts import analyze_grid_scip_recovery_loa_return as audit


@pytest.fixture
def selection():
    baseline = [r for r in json.loads((audit.ROOT / 'results/grid_gdpopt_scip_20261025/jobs.json').read_text())
                if r['method'] == 'loa']
    path = audit.PACKAGES / 'grid_gdpopt_scip_recovery_loa_dantzig_20261025.zip'
    with zipfile.ZipFile(path) as z:
        selected = json.loads(z.read(path.stem + '/RECOVERY_SELECTION.json'))
    return selected, baseline


def test_missing_failed_attempt_is_not_excluded(selection):
    chosen, baseline = deepcopy(selection)
    chosen['jobs'].pop()
    with pytest.raises(ValueError, match='Missing or duplicate'):
        audit.verify_selection(chosen, baseline)


def test_previous_non_error_is_not_silently_added_to_recovery(selection):
    chosen, baseline = deepcopy(selection)
    chosen['jobs'][0]['grid_name'] = 'alpine1'
    with pytest.raises(ValueError, match='original errors'):
        audit.verify_selection(chosen, baseline)


def test_original_error_cannot_be_relabelled_as_a_target_hit(selection):
    chosen, baseline = deepcopy(selection)
    chosen['jobs'][0]['target_hit_verified'] = True
    with pytest.raises(ValueError, match='target_hit_verified'):
        audit.verify_selection(chosen, baseline)


def test_loa_return_keeps_mismatch_timeout_and_distinct_method_cohorts(tmp_path):
    process = subprocess.run([sys.executable, str(audit.ROOT / 'scripts/analyze_grid_scip_recovery_loa_return.py'),
                              '--output', str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stdout + process.stderr
    s = json.loads((tmp_path / 'summary.json').read_text())
    assert s['recovery']['jobs'] == 19 and s['recovery']['target_hits'] == 16
    assert s['recovery']['errors'] == 0 and s['recovery']['time_limits'] == 3
    assert s['original_loa_21']['target_hits'] == 2 and s['original_loa_21']['errors'] == 19
    assert s['descriptive_loa_21_after_error_recovery']['target_hits'] == 18
    assert s['benchmark_scip_mip_calls'] == 26877
    assert s['benchmark_nlp_calls'] == s['network_retry_events'] == 0
    assert s['recorded_optimal_target_mismatches'] == ['holder_table', 'michalewicz', 'shubert']
    diagnoses = json.loads((tmp_path / 'target_mismatch_diagnostics.json').read_text())
    assert len(diagnoses) == 6
    assert all(d['original_gdp_witness']['target_hit_verified'] for d in diagnoses)
    assert all(d['discrete_selections'] == 1 and d['before_subproblem_callbacks'] == 0 for d in diagnoses)
    assert all(not d['local_presolve_allows_solver'] and d['local_fbbt_error'] for d in diagnoses)
    assert s['unprovided_recovery_methods'] == []
