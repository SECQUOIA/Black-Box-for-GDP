"""Protect attempt selection and equal-cohort three-method comparisons."""

import json
import subprocess
import sys

import pytest

from scripts import compare_grid_scip_recoveries as audit


def test_comparison_cannot_drop_a_failed_attempt():
    baseline = {'a': {'status': 'error', 'reference_minimum': 0},
                'b': {'status': 'error', 'reference_minimum': 0}}
    with pytest.raises(ValueError, match='every original error'):
        audit.select_descriptive(baseline, {'a': {'reference_minimum': 0}})


def test_comparison_cannot_adjust_reference_for_new_incumbent():
    with pytest.raises(ValueError, match='Reference changed'):
        audit.select_descriptive({'a': {'status': 'error', 'reference_minimum': 0}},
                                 {'a': {'reference_minimum': 0.0864917}})


def test_three_method_comparison_preserves_cohorts_costs_and_misses(tmp_path):
    result = subprocess.run([sys.executable, str(audit.ROOT / 'scripts/compare_grid_scip_recoveries.py'),
                             '--output', str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    s = json.loads((tmp_path / 'summary.json').read_text())
    assert s['original_attempts']['jobs'] == 63
    assert s['original_attempts']['target_hits'] == 12
    assert s['original_attempts']['target_hits_without_error'] == 11
    assert s['recovery_attempts']['jobs'] == 46 and s['recovery_attempts']['target_hits'] == 40
    assert s['recovery_attempts']['errors'] == 0
    assert s['recovery_attempts']['time_limits'] == s['recovery_attempts']['time_limits_with_target'] == 7
    assert s['descriptive_inventory']['jobs'] == 63 and s['descriptive_inventory']['target_hits'] == 51
    assert s['descriptive_inventory']['optimal_but_misses_target'] == 7
    assert s['every_method_misses'] == ['holder_table', 'michalewicz', 'shubert']
    assert s['grids_with_at_least_one_target_hit'] == 18
    assert s['grids_with_all_three_target_hits'] == 15
    assert len(s['common_recovery_grids']) == 9
    assert [(r['common_jobs'], r['both_hit']) for r in s['pairwise_common_recovery']] == [(9, 9), (12, 10), (15, 14)]
    assert all(r['a_only'] == r['b_only'] == 0 for r in s['pairwise_common_recovery'])
    assert s['benchmark_recovery_scip_mip_calls'] == 67506 and s['benchmark_recovery_nlp_calls'] == 0
    assert s['cumulative_worker_s'] > s['descriptive_inventory']['worker_wall_s'] > s['recovery_attempts']['worker_wall_s']
