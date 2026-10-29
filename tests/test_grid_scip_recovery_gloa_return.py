"""Verify the GLOA recovery cohort and retain its false-optimal outcome."""

from copy import deepcopy
import json
import subprocess
import sys
import zipfile

import pytest

from scripts import analyze_grid_scip_recovery_gloa_return as audit


@pytest.fixture
def selection():
    baseline = [r for r in json.loads((audit.ROOT / 'results/grid_gdpopt_scip_20261025/jobs.json').read_text())
                if r['method'] == 'gloa']
    path = audit.PACKAGES / 'grid_gdpopt_scip_recovery_gloa_dantzig_20261025.zip'
    with zipfile.ZipFile(path) as z:
        selected = json.loads(z.read(path.stem + '/RECOVERY_SELECTION.json'))
    return selected, baseline


def test_missing_failed_attempt_is_not_excluded(selection):
    chosen, baseline = deepcopy(selection)
    chosen['jobs'].pop()
    with pytest.raises(ValueError, match='Missing or duplicate'):
        audit.verify_selection(chosen, baseline)


def test_previous_false_optimal_is_not_silently_added_to_recovery(selection):
    chosen, baseline = deepcopy(selection)
    chosen['jobs'][0]['grid_name'] = 'shubert'
    with pytest.raises(ValueError, match='original errors'):
        audit.verify_selection(chosen, baseline)


def test_original_error_cannot_be_relabelled_as_a_target_hit(selection):
    chosen, baseline = deepcopy(selection)
    chosen['jobs'][0]['target_hit_verified'] = True
    with pytest.raises(ValueError, match='target_hit_verified'):
        audit.verify_selection(chosen, baseline)


def test_gloa_return_keeps_mismatch_timeout_and_distinct_method_cohorts(tmp_path):
    process = subprocess.run([sys.executable, str(audit.ROOT / 'scripts/analyze_grid_scip_recovery_gloa_return.py'),
                              '--output', str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stdout + process.stderr
    s = json.loads((tmp_path / 'summary.json').read_text())
    assert s['recovery']['jobs'] == 15 and s['recovery']['target_hits'] == 14
    assert s['recovery']['errors'] == 0 and s['recovery']['time_limits'] == 1
    assert s['original_gloa_21']['target_hits'] == 3 and s['original_gloa_21']['errors'] == 15
    assert s['descriptive_gloa_21_after_error_recovery']['target_hits'] == 17
    assert s['benchmark_scip_mip_calls'] == 22280
    assert s['benchmark_nlp_calls'] == s['network_retry_events'] == 0
    assert s['recorded_optimal_target_mismatches'] == ['michalewicz']
    diagnoses = json.loads((tmp_path / 'target_mismatch_diagnostics.json').read_text())
    assert len(diagnoses) == 1
    d = diagnoses[0]
    assert d['original_gdp_witness']['target_hit_verified']
    assert d['discrete_selections'] == 1 and d['before_subproblem_callbacks'] == 0
    assert not d['local_presolve_allows_solver'] and d['local_fbbt_error']
    comparison = json.loads((tmp_path / 'ric_gloa_recovery_comparison.json').read_text())
    assert comparison['ric_recovery_jobs'] == 12 and comparison['gloa_recovery_jobs'] == 15
    assert comparison['common_jobs'] == comparison['both_hit'] == 9
