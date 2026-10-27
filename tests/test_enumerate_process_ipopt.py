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
    assert set(changes) == {'_sources.py', 'models.py', 'evaluation.py', 'solvers.py', 'preflight.py'}
    for name in ('models.py', 'evaluation.py'):
        assert changes[name]['current_sha256'] == enum.REJECTION_PHASE_ADAPTERS[name]
        assert 'rejection_phase' in changes[name]['reviewed_change']


@pytest.mark.parametrize('name', ['models.py', 'evaluation.py', 'solvers.py'])
def test_main_routing_profile_does_not_allow_other_adapter_changes(name):
    adapters = {p.name: p.read_bytes() for p in (enum.ROOT / 'gdp_models').glob('*.py')}
    adapters[name] += b'\n# unreviewed source change\n'
    with pytest.raises(ValueError, match='Unreviewed adapter change'):
        enum.verify_sources('column', adapter_files=adapters)


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
