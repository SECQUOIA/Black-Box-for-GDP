"""Guard scientific interpretation, original evidence and solver-free reproduction."""
from copy import deepcopy
import csv
import hashlib
import platform
import json
import subprocess
import sys
import zipfile

import pytest
from scripts import analyze_process_scip_four_return as audit
from review_diagnostics.replay import equivalent


def test_watchdog_time_is_not_zero_when_method_clock_is_absent():
    assert audit.clock({'worker_wall_s': 1800.1}) == (1800.1, 'worker_wall_s_watchdog')
    assert audit.clock({'worker_wall_s': 1800.1, 'method_wall_s': None}) == (1800.1, 'worker_wall_s_watchdog')
    assert audit.clock({'method_wall_s': 10, 'worker_wall_s': 11}) == (10, 'method_wall_s')
    with pytest.raises(ValueError, match='Missing measured clock'):
        audit.clock({})


def test_modified_or_missing_archive_members_are_rejected(tmp_path):
    path = tmp_path / 'broken.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('run/result.json', 'changed')
        z.writestr('run/SHA256SUMS', hashlib.sha256(b'original').hexdigest() + '  result.json\n')
    with zipfile.ZipFile(path) as z, pytest.raises(ValueError, match='Checksum mismatch'):
        audit.verify_return(z, 'loa')


def test_absolute_target_and_minimization_attainment_remain_distinct():
    old = {'objective': '3.0', 'target_hit': 'True', 'target_attained': 'True',
           'measured_total_with_preparation_s': '100', 'status': 'finished', 'termination': 'optimal'}
    new = {'instance_id': 'test', 'method': 'hull', 'objective': 2.9, 'target_value': 3.0,
           'target_hit': False, 'target_attained': True, 'status': 'finished', 'termination': 'optimal',
           'total_with_preparation_s': 90}
    pair = audit.paired(old, new)
    assert pair['pair_class'] == 'old_only' and pair['new_target_attained']
    assert pair['new_minus_old_objective'] < 0
    old['target_hit'] = 'False'
    with pytest.raises(ValueError, match='Historical target'):
        audit.paired(old, new)


@pytest.fixture(scope='module')
def reproduced(tmp_path_factory):
    path = tmp_path_factory.mktemp('scip-four-audit')
    run = subprocess.run([sys.executable, str(audit.ROOT / 'scripts/analyze_process_scip_four_return.py'),
                          '--output', str(path)], text=True, capture_output=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    return path


def test_all_four_returns_reproduce_without_solvers_and_keep_all_denominators(reproduced):
    summary = json.loads((reproduced / 'summary.json').read_text())
    assert summary['jobs'] == 45 and summary['returned_feasible_solutions'] == 43
    assert summary['baron_target_hits'] == 19 and summary['scip_target_hits'] == 20
    assert summary['baron_target_attained'] == 21 and summary['scip_target_attained'] == 25
    assert summary['time_limits'] == 16 and summary['errors'] == 0
    assert summary['new_optimizer_calls_during_analysis'] == 0
    assert all(r['jobs'] == 9 for r in summary['by_method'])
    retained = audit.ROOT / 'results/process_scip_four_analysis_20261026'
    checksums = json.loads((retained / 'artifact_checksums.json').read_text())
    for name in audit.DATA_FILES:
        expected = retained / name
        # Preserve the published bytes independently of portable numeric replay.
        assert hashlib.sha256(expected.read_bytes()).hexdigest() == checksums[str(expected.relative_to(audit.ROOT))]
        compare_reproduction(reproduced / name, expected)


def compare_solution_checks(actual, expected):
    assert len(actual) == len(expected)
    for replayed, saved in zip(actual, expected):
        records = [deepcopy(replayed), deepcopy(saved)]
        servers = []
        for row in records:
            differences = row.pop('cross_platform_evaluation_differences', None)
            if differences is not None:
                server = deepcopy(row)
                for key, values in differences.items():
                    assert values['local'] == row[key] and values['local'] != values['server']
                    server[key] = values['server']
                servers.append(server)
        # These fields describe the same archived server evaluation exactly.
        if servers:
            assert len(servers) == 2 and servers[0] == servers[1]
        left, right = records
        for kind in left['worst_components']:
            if left['worst_components'][kind] != right['worst_components'][kind]:
                # The identity of an effectively zero residual can change with
                # arithmetic ordering. Nonzero worst rows must still match.
                assert max(left['max_violations_by_kind'][kind],
                           right['max_violations_by_kind'][kind]) <= 1e-12
                left['worst_components'][kind] = right['worst_components'][kind]
        assert equivalent(left, right)


def compare_reproduction(actual, expected):
    if actual.suffix == '.csv':
        with actual.open(newline='') as stream, expected.open(newline='') as saved:
            left, right = list(csv.reader(stream)), list(csv.reader(saved))
        assert left[0] == right[0] and len(left) == len(right)
        for a, b in zip(left[1:], right[1:]):
            assert len(a) == len(b)
            for x, y in zip(a, b):
                if x != y:
                    # Category strings/Boolean flags cannot be parsed as floats.
                    assert equivalent(float(x), float(y)), (actual.name, x, y)
    elif actual.suffix == '.json':
        left, right = json.loads(actual.read_text()), json.loads(expected.read_text())
        if actual.name == 'solution_checks.json':
            compare_solution_checks(left, right)
        elif actual.name == 'manifest.json':
            assert left.pop('analysis_python') == platform.python_version()
            assert right.pop('analysis_python') == '3.13.12'
            assert left == right
        else:
            assert equivalent(left, right), actual.name
    else:
        assert actual.read_bytes() == expected.read_bytes(), actual.name


def test_actual_solver_starts_not_conflated_with_network_or_incomplete_interfaces(reproduced):
    summary = json.loads((reproduced / 'summary.json').read_text())
    assert summary['actual_benchmark_solver_invocations'] == {'scip/minlp': 18, 'scip/mip': 2263, 'scip/nlp': 2236}
    assert summary['started_interface_attempts'] == 4520
    assert sum(summary['actual_benchmark_solver_invocations'].values()) == 4517
    assert summary['actual_preflight_solver_invocations'] == 7 and summary['compile_only_preflight_calls'] == 18
    assert summary['recovered_network_errors'] == 5 and summary['network_backoff_s'] == 25


def test_missing_solution_and_false_optimal_are_not_promoted(reproduced):
    issues = json.loads((reproduced / 'issues.json').read_text())
    missing = {(r['instance_id'], r['method']): r for r in issues if r['type'] == 'missing_solution'}
    assert set(missing) == {('cstr_15', 'bigm'), ('column', 'bigm')}
    assert missing['cstr_15', 'bigm']['last_incumbent_validation']['max_primal_violation'] > 1e-5
    assert missing['column', 'bigm']['gams_statistics']['MODELSTAT'] == 14
    conflicts = {(r['instance_id'], r['method']): r for r in issues if r['type'] == 'bound_conflict'}
    assert len(conflicts) == 19
    assert conflicts['dynamic', 'hull']['witness_method'] == 'bigm'
    assert conflicts['dynamic', 'hull']['gap'] > 15
    assert all((f'cstr_{n}', 'gloa') in conflicts for n in range(5, 31, 5))


def test_all_historical_and_new_returned_vectors_are_independently_checked(reproduced):
    checks = json.loads((reproduced / 'solution_checks.json').read_text())
    assert sum(c['cohort'] == 'baron' for c in checks) == 45
    assert sum(c['cohort'] == 'scip' for c in checks) == 43
    assert all(c['original_gdp_feasible'] and c['max_original_violation'] <= 1e-5 for c in checks)
    manifest = json.loads((reproduced / 'manifest.json').read_text())
    assert sum(p['terminal_jobs_verified'] for p in manifest['returned_packages'].values()) == 45
    assert manifest['analysis_solver_calls'] == 0


@pytest.mark.parametrize('change', ['flag', 'count', 'objective', 'worst_row', 'difference'])
def test_portable_replay_still_rejects_changed_evidence(change):
    saved = {'cohort': 'scip', 'original_gdp_feasible': True,
             'variables_checked': 10, 'objective_recomputed': 2.0,
             'worst_components': {'constraints': 'a'},
             'max_violations_by_kind': {'constraints': 1e-7},
             'cross_platform_evaluation_differences': {}}
    actual = deepcopy(saved)
    if change == 'flag':
        actual['original_gdp_feasible'] = False
    elif change == 'count':
        actual['variables_checked'] += 1
    elif change == 'objective':
        actual['objective_recomputed'] += 1e-4
    elif change == 'worst_row':
        actual['worst_components']['constraints'] = 'b'
    else:
        actual['cross_platform_evaluation_differences'] = {
            'objective_recomputed': {'local': 3.0, 'server': 2.0}}
    with pytest.raises(AssertionError):
        compare_solution_checks([actual], [saved])
