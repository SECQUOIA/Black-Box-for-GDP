"""Budget boundaries must not discard BAM's final value or mask backend errors."""
import copy
import json
import sys
import types

import pytest

import ipopt_dfo_cstr
import ipopt_dfo_non_cstr


@pytest.fixture(params=[ipopt_dfo_cstr, ipopt_dfo_non_cstr])
def setup(request, tmp_path):
    r = request.param
    is_cstr = r is ipopt_dfo_cstr
    s = {'job_id': 'test', 'case': 'cstr_30' if is_cstr else 'dynamic',
         'cstr_size': 30, 'seed': 0, 'method': 'bam', 'budget': 5,
         'lower': [1, 1] if is_cstr else [1, 2], 'upper': [30, 30] if is_cstr else [9, 9],
         'starts': [[1, 2], [2, 3], [3, 4]], 'settings': copy.deepcopy(r.SETTINGS['bam'])}
    table = {}
    for point in s['starts']:
        table[tuple(point)] = {'point': json.dumps(point), 'accepted': 'True',
            'objective': '2.5', 'candidate_objective': '2.5', 'message': '',
            **{k: '0.01' for k in r.TIMES}}
    return r, s, table


def test_legacy_frozen_spec_keeps_original_terminal_exception(setup, tmp_path):
    r, s, table = setup
    s['budget'] = 3
    s['settings'].pop('budget_stop_policy')
    oracle = r.Oracle(s, table, tmp_path)
    oracle(s['starts'][0]); oracle(s['starts'][1])
    with pytest.raises(r.BudgetStop):
        oracle(s['starts'][2])
    assert not oracle.events[-1]['value_returned_to_optimizer']


def test_only_initial_design_does_not_launch_unlimited_native_search(setup, tmp_path, monkeypatch):
    r, s, table = setup
    s['budget'] = 3
    oracle = r.Oracle(s, table, tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('BAM must not start with max_evals=0')
    monkeypatch.setitem(sys.modules, 'bam', types.SimpleNamespace(set_license_file=lambda p: None, minimize=forbidden))
    result = r.optimize(s, oracle, {'bam_license': '/license'}, tmp_path)
    assert oracle.call_count == 3 and all(e['value_returned_to_optimizer'] for e in oracle.events)
    assert result['nfev'] == 0 and result['success']


@pytest.mark.parametrize('mode', ['normal', 'overrun', 'swallowed_overrun', 'returned_error', 'raised_error'])
def test_worker_budget_boundary_and_real_errors(setup, tmp_path, monkeypatch, mode):
    r, s, table = setup
    job = tmp_path / 'jobs' / 'test'; job.mkdir(parents=True)
    r.write(job / 'spec.json', s)
    r.write(tmp_path / 'run.json', {'config': {'bam_license': '/license'}})
    monkeypatch.setattr(r, 'load_table', lambda *a: (table, {}))
    monkeypatch.setattr(r, 'preflight', lambda *a: {})
    monkeypatch.setattr(r.os, 'sched_getaffinity', lambda pid: {0}, raising=False)
    class NoMoreReads(dict):
        def get(self, *args):
            pytest.fail('An extra callback read the process table')
    def minimize(objective, **kwargs):
        assert kwargs['options']['max_evals'] == 2
        assert objective(s['starts'][0]) == 2.5
        assert objective(s['starts'][1]) == 2.5
        if mode == 'raised_error':
            raise RuntimeError('backend error after final evaluation')
        if mode == 'returned_error':
            return types.SimpleNamespace(status=99, success=False, message='backend failed')
        if 'overrun' in mode:
            objective.table = NoMoreReads()
            try:
                objective(s['starts'][0])
            except (ValueError, RuntimeError):
                if mode != 'swallowed_overrun': raise
        return types.SimpleNamespace(status=35, success=True, nfev=2)
    monkeypatch.setitem(sys.modules, 'bam', types.SimpleNamespace(set_license_file=lambda p: None, minimize=minimize))
    r.worker(job)
    result = r.read(job / 'result.json')
    assert result['status'] == ('budget_completed' if mode == 'normal' else 'execution_failed')
    events = r.jsonl(job / 'callbacks.jsonl')
    assert len([e for e in events if e['source_row'] is not None]) == s['budget']
    assert events[s['budget'] - 1]['value_returned_to_optimizer']
    if 'overrun' in mode and r is ipopt_dfo_non_cstr:
        attempted = r.jsonl(job / 'budget_overruns.jsonl')
        assert len(attempted) == 1 and not attempted[0]['csv_read']
    if mode == 'raised_error':
        assert 'backend error' in result['error']


def test_last_rejection_is_returned_as_nan(setup, tmp_path):
    import math
    r, s, table = setup
    oracle = r.Oracle(s, table, tmp_path)
    for point in s['starts']:
        oracle(point)
    oracle(s['starts'][0])
    rejected = [1, 9] if r is ipopt_dfo_cstr else [9, 2]
    assert math.isnan(oracle(rejected))
    assert oracle.events[-1]['callback_exit'] == 'return'
    assert oracle.events[-1]['value_returned_to_optimizer']
    assert oracle.call_count == s['budget']
