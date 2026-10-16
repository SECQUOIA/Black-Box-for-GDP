"""Full-box enumeration contract: no actual optimizer is called in these tests."""
import csv
import json
from time import perf_counter
from types import SimpleNamespace

import pytest

import enumerate_process_ipopt as enum


@pytest.mark.parametrize('case,total,logical', [('column', 81, 64), ('dynamic', 72, 37)])
def test_plans_cover_every_dfo_coordinate(case, total, logical):
    plan = enum.plan(case)
    assert len(plan['points']) == len({tuple(p) for p in plan['points']}) == total
    assert sum(enum.allowed(case, p) for p in plan['points']) == logical


@pytest.mark.parametrize('case', ['column', 'dynamic'])
def test_original_model_and_reference_hashes_match(case):
    baseline, changes = enum.verify_sources(case)
    assert baseline['config'] == enum.CONFIG
    assert set(changes) == {'evaluation.py', 'solvers.py', 'preflight.py'}


@pytest.mark.parametrize('case,point,status', [('column', [7, 1], 'logical_infeasible'),
    ('column', [8, 8], 'preprocessing_infeasible'), ('dynamic', [2, 2], 'logical_infeasible')])
def test_real_rejection_path_has_measured_time_without_solver(case, point, status, monkeypatch):
    from gdp_models import evaluation
    def forbidden(*args, **kwargs):
        pytest.fail('Rejected point must not call a solver')
    monkeypatch.setattr(evaluation, 'optimizer_for', forbidden)
    report = enum.evaluate(case, point, solver='gams_ipopt', initialization='auto', time_limit=60,
                           feasibility_tolerance=1e-5)
    assert report['status'] == status and not report['accepted'] and not report['solver_called']
    assert report['total_wall_s'] > 0 and report['setup_wall_s'] > 0 and report['logic_wall_s'] > 0
    assert report['objective'] is None
    if status == 'preprocessing_infeasible':
        assert report['preprocess_wall_s'] > 0
    if case == 'column':
        assert report['reflux_tray'] == point[0] + 1 and report['boilup_tray'] == point[1] + 1


@pytest.mark.parametrize('legacy,termination,solve_status,expected', [
    ('accepted', 'locallyOptimal', 1, 'accepted'), ('rejected', 'feasible', 1, 'ipopt_failed'),
    ('solver_error', 'feasible', 3, 'time_limit'), ('rejected', 'maxIterations', 2, 'ipopt_failed'),
    ('exception', 'error', None, 'exception')])
def test_failure_limit_and_exception_states_stay_distinct(legacy, termination, solve_status, expected):
    report = {'status': legacy, 'termination': termination, 'gams_solve_status': solve_status}
    assert enum.classify(report, True) == expected


def test_solver_exception_records_attempt_and_elapsed_time(monkeypatch):
    from gdp_models import evaluation
    prepared = SimpleNamespace(model=None, metadata={'initialization': 'constructor_defaults'},
                               timings={'setup_wall_s': 0.001, 'preprocess_wall_s': 0.001})
    monkeypatch.setattr(evaluation, 'prepare_nlp', lambda *a, **k: prepared)
    monkeypatch.setattr(evaluation, 'optimizer_for',
                        lambda *a, **k: SimpleNamespace(executable=lambda: '/fake/gams'))
    def fail(*a, **k):
        raise RuntimeError('Simulated solver exception; no optimizer invoked')
    monkeypatch.setattr(evaluation, 'solve_gams', fail)
    result = enum.evaluate('column', [13, 4], solver='gams_ipopt')
    assert result['status'] == 'exception' and result['legacy_status'] == 'solver_error'
    assert result['exception_type'] == 'RuntimeError'
    assert result['solver_called'] and result['solve_wall_s'] > 0 and result['total_wall_s'] > 0
    assert not result['accepted'] and not result['mathematical_infeasibility_claim']


@pytest.mark.parametrize('case', ['column', 'dynamic'])
def test_resume_never_repeats_completed_points_and_compares_new_values(case, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(enum, 'runtime_identity', lambda *a: {'solver_executable': '/fake/gams', 'protocol': 'test'})
    def fake(case_name, point, **kwargs):
        calls.append(tuple(point))
        started = perf_counter()
        accepted = enum.allowed(case_name, point)
        return {'case': case_name, 'cstr_size': None, 'point': point, 'solver': 'gams_ipopt',
            'status': 'accepted' if accepted else 'logical_infeasible',
            'legacy_status': 'accepted' if accepted else 'preprocessing_infeasible',
            'accepted': accepted, 'objective': 123.456 if accepted else None,
            'termination': 'optimal' if accepted else 'not_solved', 'total_wall_s': perf_counter() - started}
    monkeypatch.setattr(enum, 'evaluate', fake)
    output = tmp_path / case
    first = enum.run_case(case, output, max_points=7)
    assert first['completed_points'] == 7 and not first['complete']
    second = enum.run_case(case, output, resume=True)
    assert second['complete'] and second['missing_rows'] == second['missing_total_times'] == 0
    assert len(calls) == len(set(calls)) == enum.plan(case)['candidate_count']
    before = list(calls)
    enum.run_case(case, output, resume=True)
    assert calls == before
    with (output / 'comparison.csv').open() as stream:
        comparisons = list(csv.DictReader(stream))
    assert len(comparisons) == enum.plan(case)['candidate_count']
    assert all(r['new_objective'] == '123.456' for r in comparisons if r['new_accepted'] == 'True')
    if case == 'column':
        assert not second['accepted_count_matches_history']  # Never force29 accepted.
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['plan']['bounds'] == enum.plan(case)['bounds']


def test_verified_original_archive_is_used_without_extracted_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(enum, 'REFERENCE', tmp_path / 'absent-inputs')
    for case in enum.CASES:
        files = enum.reference_files(case)
        assert set(files) == {'evaluations.csv', 'manifest.json'}
        baseline, changes = enum.verify_sources(case)
        assert baseline['config'] == enum.CONFIG
        assert '5a9e704' in changes['evaluation.py']['reviewed_change']
        assert '5a9e704' in changes['solvers.py']['reviewed_change']
    assert not (tmp_path / 'absent-inputs').exists()


def test_present_changed_reference_is_not_replaced_by_archive(tmp_path, monkeypatch):
    files = enum.reference_files('column')
    folder = tmp_path / 'inputs' / 'column'
    folder.mkdir(parents=True)
    for name, raw in files.items():
        (folder / name).write_bytes(raw)
    (folder / 'evaluations.csv').write_bytes(files['evaluations.csv'] + b'\n')
    monkeypatch.setattr(enum, 'REFERENCE', folder.parent)
    with pytest.raises(ValueError, match='Historical reference changed: column/evaluations.csv'):
        enum.verify_sources('column')


@pytest.mark.parametrize('name', ['evaluation.py', 'solvers.py', 'models.py'])
def test_builder_refuses_unreviewed_captured_adapter_bytes(name, tmp_path, monkeypatch):
    import build_column_dynamic_ipopt as builder
    from pathlib import Path
    original = Path.read_bytes

    def changed(path):
        raw = original(path)
        if path == builder.ROOT / 'gdp_models' / name:
            return raw + b'\n# unreviewed change\n'
        return raw

    monkeypatch.setattr(Path, 'read_bytes', changed)
    output = tmp_path / 'must-not-exist.zip'
    with pytest.raises(ValueError, match=f'Unreviewed adapter change: {name}'):
        builder.build(output)
    assert not output.exists()


def test_standalone_bundle_passes_real_source_preflight_without_solver(tmp_path, monkeypatch):
    import hashlib
    import os
    import subprocess
    import sys
    import zipfile
    import build_column_dynamic_ipopt as builder

    monkeypatch.setattr(enum, 'REFERENCE', tmp_path / 'absent-inputs')
    output = tmp_path / 'runner.zip'
    builder.build(output)
    with zipfile.ZipFile(output) as archive:
        archive.extractall(tmp_path / 'unpacked')
    bundle = tmp_path / 'unpacked' / 'column_dynamic_ipopt_runner'
    provenance = json.loads((bundle / 'bundle_provenance.json').read_text())
    assert provenance['reference_sha256'] == enum.REFERENCE_HASHES
    for line in (bundle / 'RUNNER_SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
    # A separate interpreter proves that neither repository imports nor ignored
    # extracted inputs satisfy the standalone bundle's checks accidentally.
    script = '''
import sys
sys.path.insert(0, sys.argv[1])
import enumerate_process_ipopt as enum
from gdp_models import evaluation, models

def forbidden(*args, **kwargs):
    raise AssertionError('Source preflight must not construct models or call solvers')

evaluation.optimizer_for = forbidden
models.prepare_nlp = forbidden
for case in enum.CASES:
    baseline, changes = enum.verify_sources(case)
    assert baseline['config'] == enum.CONFIG
    assert '5a9e704' in changes['evaluation.py']['reviewed_change']
print('both bundled source profiles verified; no solver called')
'''
    environment = dict(os.environ, RBFOPT_GDP_SOURCES=str(builder.ROOT / 'external'))
    result = subprocess.run([sys.executable, '-I', '-c', script, str(bundle)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'both bundled source profiles verified' in result.stdout
