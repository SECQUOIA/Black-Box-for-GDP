"""Solver-free checks of imported evidence, denominator and historical pairing."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'results/gdpopt_scip_ipopt_analysis_20261030'
spec = importlib.util.spec_from_file_location('scip_ipopt_return', ROOT / 'scripts/analyze_gdpopt_scip_ipopt_return.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def read(name):
    return json.loads((REPORT / name).read_text())


def test_every_planned_job_is_retained_once():
    rows = read('jobs.json')
    assert len(rows) == len({r['job_id'] for r in rows}) == 90
    for scope, expected in [('grid', 21), ('process', 9)]:
        for method in ('loa', 'ric', 'gloa'):
            assert sum(r['scope'] == scope and r['method'] == method for r in rows) == expected
    assert all(sum(r['package_id'] == p['package_id'] for r in rows) == 15 for p in read('packages.json'))


def test_target_feasibility_and_termination_are_distinct():
    rows = read('jobs.json')
    assert sum(r['original_gdp_feasible'] for r in rows) == 90
    assert sum(r['target_hit'] for r in rows) == 55
    assert sum(r['termination'] == 'maxTimeLimit' for r in rows) == 28
    assert sum(r['status'] == 'hard_time_limit' for r in rows) == 4
    assert sum(r['termination'] == 'optimal' and not r['target_hit'] for r in rows) == 17
    assert not any(r['global_optimality_certified'] for r in rows)


def test_local_audit_fills_watchdog_gap_without_inventing_target_hits():
    checks = read('solution_checks.json')
    gaps = [r for r in checks if not r['server_validation'].get('original_gdp_feasible')]
    assert {r['job_id'] for r in gaps} == {'grid__alpine2__loa', 'grid__alpine2__gloa', 'grid__easom__gloa', 'grid__rastrigin__ric'}
    assert all(r['original_gdp_feasible'] and r['max_original_violation'] == 0 for r in gaps)
    assert not any(r['target_hit'] for r in read('jobs.json') if r['job_id'] in {c['job_id'] for c in gaps})


def test_actual_routing_and_call_counts():
    rows = read('jobs.json')
    assert all(r['actual_ipopt_calls'] == 0 for r in rows if r['scope'] == 'grid')
    assert all(r['actual_ipopt_calls'] > 0 for r in rows if r['scope'] == 'process')
    assert sum(r['actual_scip_calls'] for r in rows) == 76513
    assert sum(r['actual_ipopt_calls'] for r in rows) == 2373
    assert read('summary.json')['preflight_solver_calls'] == 12


def test_matched_cohorts_and_process_tradeoffs():
    pairs = read('paired_comparisons.json')
    primary = [r for r in pairs if r['cohort'] == 'previous_scip_scip']
    assert len(primary) == 90
    assert sum(r['old_target_hit'] for r in primary) == 64
    assert sum(r['new_target_hit'] for r in primary) == 55
    process = [r for r in primary if r['scope'] == 'process']
    assert {r['job_id'] for r in process if r['pair_class'] == 'new_only'} == {'process__dynamic__loa', 'process__dynamic__ric'}
    assert {r['job_id'] for r in process if r['pair_class'] == 'old_only'} == {
        'process__cstr_10__loa', 'process__cstr_10__ric', 'process__cstr_25__loa', 'process__cstr_25__ric'}
    assert all(not r['causal_solver_speed_comparison'] for r in pairs)
    for cohort in ('previous_baron', 'previous_highs_scip'):
        assert sum(r['cohort'] == cohort for r in pairs) == 27


def test_absolute_target_does_not_treat_lower_value_as_equal():
    assert not module.audit.hit(1.9, 2.0)
    assert module.audit.attained(1.9, 2.0)
    assert not module.audit.hit(None, 2.0)


def test_comparison_keeps_missing_solution_and_cost():
    new = {'job_id': 'example', 'scope': 'process', 'method': 'loa', 'reference': 2.0,
        'target_hit': False, 'target_attained': False, 'objective': None,
        'worker_seconds': 1800., 'termination': 'maxTimeLimit'}
    pair = module.comparison({'objective': 2.0, 'target_hit': True, 'seconds': 5., 'termination': 'optimal'},
                             new, 'historical', 'worker_seconds')
    assert pair['pair_class'] == 'old_only' and pair['new_seconds'] == 1800.
    assert pair['new_minus_old_objective'] is None


def test_tampered_evidence_is_rejected_before_model_evaluation(tmp_path):
    entries = read('evidence/IMPORT.json')
    (tmp_path / 'IMPORT.json').write_text(json.dumps(entries))
    (tmp_path / entries[0]['compact_archive']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='Compact evidence changed'):
        module.analyze(tmp_path, tmp_path / 'output')


def test_reproduce_all_saved_analysis_without_solver(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_gdpopt_scip_ipopt_return.py'),
        '--output', str(tmp_path)], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    for name in ('jobs.json', 'paired_comparisons.json', 'solution_checks.json', 'issues.json',
                 'packages.json', 'summary.json', 'provenance.json', 'README.md'):
        assert (tmp_path / name).read_bytes() == (REPORT / name).read_bytes(), name
