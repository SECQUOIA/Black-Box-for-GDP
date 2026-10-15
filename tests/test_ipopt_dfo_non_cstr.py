"""No process solves: data provenance, budgets, adapters and durable reporting."""
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import types
import zipfile

import pytest

import ipopt_dfo_non_cstr as r
import build_ipopt_dfo_non_cstr as builder


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    folder = tmp_path_factory.mktemp('frozen')
    archive = folder / 'runner.zip'
    builder.build(archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(folder)
    return folder / 'ipopt_dfo_non_cstr_runner'


def spec(method='dsda', budget=5):
    return {'job_id': 'test', 'case': 'dynamic', 'seed': 0, 'method': method, 'budget': budget,
            'lower': [1, 2], 'upper': [9, 9], 'starts': [[1, 4], [9, 9], [4, 5]],
            'settings': r.SETTINGS[method]}


def test_plan_320_slots_and_shared_original_designs():
    plan = builder.plan()
    assert len(plan) == len({s['job_id'] for s in plan}) == 320
    assert {s['seed'] for s in plan} == set(range(10))
    for case in r.CASES:
        for seed in range(10):
            subset = [s for s in plan if s['case'] == case and s['seed'] == seed]
            assert len({json.dumps(s['starts']) for s in subset}) == 1
            assert all(len(s['starts']) == len({tuple(p) for p in s['starts']}) == 3 for s in subset)
    assert not any('target' in s for s in plan)
    column0 = next(s for s in plan if s['case'] == 'column' and s['seed'] == 0)
    assert column0['starts'] != [[10, 3], [13, 6], [8, 9]]  # Never substituted seed10.


def test_frozen_sources_and_no_executable_process_models(frozen):
    r.verify_inventory(frozen)
    assert not (frozen / 'gdp_models').exists()
    assert not (frozen / 'case_study_data').exists()
    assert not list((frozen / 'case_studies').glob('*_case.py'))
    for case, count in [('column', 29), ('dynamic', 37), ('small_batch', 12)]:
        table, provenance = r.load_table(frozen, case)
        assert sum(row['accepted'] == 'True' for row in table.values()) == count
        assert 'Original single' in provenance['attempt_selection']


def test_incomplete_logical_table_is_not_infeasible(frozen, tmp_path):
    shutil.copytree(frozen / 'inputs', tmp_path / 'inputs')
    p = tmp_path / 'inputs/dynamic/evaluations.csv'
    p.write_text('\n'.join(p.read_text().splitlines()[:-1]) + '\n')
    info = r.read(p.parent / 'provenance.json')
    info['files_sha256']['evaluations.csv'] = r.sha(p)
    r.write(p.parent / 'provenance.json', info)
    with pytest.raises(ValueError, match='Incomplete'):
        r.load_table(tmp_path, 'dynamic')


@pytest.mark.parametrize('method,kind', [('rbfopt', 'finite'), ('dsda', 'finite'), ('bam', 'nan'), ('fmqa_sa', '+inf')])
def test_failures_repeats_terminal_callback_and_missing_times(frozen, tmp_path, method, kind):
    table, _ = r.load_table(frozen, 'dynamic')
    s = spec(method)
    s['starts'] = [[2, 2], [1, 4], [9, 9]]
    oracle = r.Oracle(s, table, tmp_path)
    for p in s['starts']:
        oracle(p)
    oracle([1, 4])
    if method == 'bam':
        assert oracle([1, 4]) == float(table[tuple([1, 4])]['objective'])
    else:
        with pytest.raises(r.BudgetStop):
            oracle([1, 4])
    assert oracle.call_count == 5
    events = r.jsonl(tmp_path / 'callbacks.jsonl')
    assert events[0]['evaluation_state'] == 'logical_exclusion_unmeasured'
    assert events[0]['method_value_kind'] == kind and events[0]['selected_attempt_nlp_s'] is None
    assert events[-1]['callback_exit'] == ('return' if method == 'bam' else 'budget_stop')
    assert events[-1]['value_returned_to_optimizer'] is (method == 'bam')
    assert events[-1]['source_row']['point'] == '[1, 4]'
    assert events[-1]['raw_objective'] == float(table[(1, 4)]['objective'])
    assert events[-1]['selected_attempt_nlp_s'] == float(table[(1, 4)]['total_wall_s'])


def test_unmeasured_allowed_point_is_never_penalized_as_infeasible(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'dynamic')
    del table[(1, 4)]
    oracle = r.Oracle(spec(), table, tmp_path)
    with pytest.raises(r.MissingEvaluation):
        oracle([1, 4])
    assert oracle.events[0]['evaluation_state'] == 'not_evaluated'
    assert oracle.events[0]['source_row'] is None


def test_invalid_callback_is_preserved_as_execution_error(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'dynamic')
    oracle = r.Oracle(spec(), table, tmp_path)
    with pytest.raises(ValueError, match='out-of-domain'):
        oracle([10, 4])
    assert oracle.call_count == 1
    assert oracle.events[0]['point'] == [10, 4]
    assert oracle.events[0]['callback_exit'] == 'protocol_error'


def test_dsda_all_unaccepted_starts_keeps_all_three(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'dynamic')
    s = spec()
    s['starts'] = [[2, 2], [3, 2], [4, 3]]
    oracle = r.Oracle(s, table, tmp_path)
    with pytest.raises(RuntimeError, match='No accepted'):
        r.optimize(s, oracle, {}, tmp_path)
    assert oracle.call_count == 3 and all(not e['accepted'] for e in oracle.events)


def test_real_dsda_search_uses_full_box_and_budget(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'dynamic')
    s = spec(budget=12)
    s['starts'] = [[9, 9], [8, 9], [7, 8]]
    oracle = r.Oracle(s, table, tmp_path)
    try:
        r.optimize(s, oracle, {}, tmp_path)
    except r.BudgetStop:
        pass
    assert 3 <= oracle.call_count <= 12
    assert [e['point'] for e in oracle.events[:3]] == s['starts']
    assert any(e['evaluation_state'] == 'logical_exclusion_unmeasured' for e in oracle.events)


def test_rbfopt_adapter_exact_settings_and_no_target(frozen, tmp_path, monkeypatch):
    table, _ = r.load_table(frozen, 'dynamic')
    s = spec('rbfopt')
    oracle = r.Oracle(s, table, tmp_path)
    class FakeAlgorithm:
        def __init__(self, settings, bb, **kwargs):
            self.l_settings = settings
            self.bb = bb
            self.starts = kwargs['init_node_pos']
            assert kwargs['init_node_val'] is None and kwargs['do_init_strategy'] is False
            assert 'target_objval' not in vars(settings)
        def optimize(self):
            for p in [*self.starts, [1, 4], [1, 5]]:
                self.bb(p)
    module = types.SimpleNamespace(RbfoptSettings=lambda **kw: types.SimpleNamespace(**kw),
             RbfoptUserBlackBox=lambda n, lo, hi, types, objective: objective, RbfoptAlgorithm=FakeAlgorithm)
    monkeypatch.setitem(sys.modules, 'rbfopt', module)
    from contextlib import nullcontext
    monkeypatch.setattr(r, 'audit_surrogate_solvers', lambda d: nullcontext())
    with pytest.raises(r.BudgetStop):
        r.optimize(s, oracle, {'bonmin': '/bonmin', 'ipopt': '/ipopt'}, tmp_path)
    assert oracle.call_count == 5
    settings = r.read(tmp_path / 'actual_settings.json')
    assert settings['global_search_method'] == 'solver' and settings['max_evaluations'] == 5


def test_bam_three_ordered_starts_and_remaining_budget(frozen, tmp_path, monkeypatch):
    table, _ = r.load_table(frozen, 'dynamic')
    s = spec('bam')
    oracle = r.Oracle(s, table, tmp_path)
    def minimize(objective, **kw):
        assert kw['options']['max_evals'] == 2
        assert kw['options']['x_evaluated'].tolist() == s['starts']
        assert oracle.call_count == 3
        objective([1, 4]); objective([1, 5])
        return types.SimpleNamespace(status=35, success=True, nfev=2, fun=0, x=[1, 5])
    monkeypatch.setitem(sys.modules, 'bam', types.SimpleNamespace(set_license_file=lambda p: None, minimize=minimize))
    result = r.optimize(s, oracle, {'bam_license': '/license'}, tmp_path)
    assert result['status'] == 35 and result['success'] is True
    assert oracle.call_count == 5
    assert oracle.events[-1]['value_returned_to_optimizer']
    assert r.read(tmp_path / 'actual_settings.json')['budget_stop_policy'] == s['settings']['budget_stop_policy']


def test_summary_keeps_320_slots_and_ten_seed_denominators(frozen, tmp_path):
    shutil.copytree(frozen, tmp_path / 'reproduction')
    r.write(tmp_path / 'run.json', {'config': {}})
    plan = r.read(frozen / 'plan.json')
    for s in [p for p in plan if p['case'] == 'column' and p['method'] == 'dsda']:
        job = tmp_path / 'jobs' / s['job_id']
        job.mkdir(parents=True)
        r.write(job / 'result.json', {'status': 'execution_failed', 'error': 'no accepted start', 'dfo_wall_s': .1})
    rows = r.summarize(tmp_path)
    assert len(rows) == 320
    summary = r.read(tmp_path / 'summary.json')
    group = next(g for g in summary['groups'] if g['case'] == 'column' and g['method'] == 'dsda')
    assert group['execution_failed'] == 10 and group['success_rate'] == 0 and group['success_rate_denominator'] == 10
    assert summary['counts']['not_run'] == 310


def test_process_import_blocker():
    guard = r.ProcessModelImportBlocker()
    for name in ('gdp_models', 'gdp_models.evaluation', 'case_studies.column_case', 'cstr_box_ipopt'):
        with pytest.raises(ImportError):
            guard.find_spec(name)
    assert guard.find_spec('rbfopt') is None


def test_cstr_cpu_detection_excludes_this_non_cstr_runner():
    assert r.is_cstr_script('/path/cstr_box_ipopt.py')
    assert r.is_cstr_script('/path/run_cstr_box_ipopt_dantzig.sh')
    assert not r.is_cstr_script('/path/ipopt_dfo_non_cstr.py')
    assert not r.is_cstr_script('/path/run_ipopt_dfo_non_cstr_dantzig.sh')


def test_controller_check_reports_all_slots_without_optimizer_calls(frozen, tmp_path, monkeypatch):
    monkeypatch.setattr(r, 'ROOT', frozen)
    monkeypatch.setattr(r, 'select_cpu', lambda cpu: {'selected': cpu})
    calls = []
    def fake_launch(command, log, seconds):
        calls.append(command)
        assert '_preflight' in command
        log.write_text('Missing environment test')
        return 1, .01, False
    monkeypatch.setattr(r, 'launch', fake_launch)
    args = types.SimpleNamespace(mode='check', run_dir=None, output_root=tmp_path,
             dfo_python='/not-installed', fmqa_python='/not-installed', conda='',
             bonmin='/not-installed', ipopt='/not-installed', bam_license='/not-installed', cpu=4)
    r.controller(args)
    directory = next(p for p in tmp_path.iterdir() if p.is_dir())
    summary = r.read(directory / 'summary.json')
    assert summary['counts'] == {'not_run': 320} and len(calls) == 4
    assert directory.with_suffix('.zip').exists()


def test_actual_rbfopt_initial_callbacks_no_auxiliary_solve(frozen, tmp_path, monkeypatch):
    pytest.importorskip('rbfopt')
    table, _ = r.load_table(frozen, 'dynamic')
    s = spec('rbfopt', budget=3)
    oracle = r.Oracle(s, table, tmp_path)
    # Exhaust at the third initial callback, before any surrogate solve.
    with pytest.raises(r.BudgetStop):
        r.optimize(s, oracle, {'bonmin': '/not-used', 'ipopt': '/not-used'}, tmp_path)
    assert [e['point'] for e in oracle.events] == s['starts']
    assert not (tmp_path / 'auxiliary_solver_calls.jsonl').exists()


def test_bam_only_bundle_keeps_every_seed_and_preflights_only_bam(tmp_path, monkeypatch):
    archive = tmp_path / 'bam_runner.zip'
    builder.build(archive, methods=['bam'])
    with zipfile.ZipFile(archive) as z:
        z.extractall(tmp_path)
    frozen = tmp_path / ('ipopt_dfo_cstr_runner' if r.__name__.endswith('_cstr') and not r.__name__.endswith('non_cstr') else 'ipopt_dfo_non_cstr_runner')
    r.verify_inventory(frozen)
    plan = r.read(frozen / 'plan.json')
    expected = [s for s in builder.plan() if s['method'] == 'bam']
    assert plan == expected and {s['seed'] for s in plan} == set(range(10))
    assert all(r.bam_native_budget(s) for s in plan)
    monkeypatch.setattr(r, 'ROOT', frozen)
    monkeypatch.setattr(r, 'select_cpu', lambda cpu: {'selected': cpu})
    calls = []
    def fake_launch(command, log, seconds):
        calls.append(command)
        assert command[command.index('--method') + 1] == 'bam'
        return 1, .01, False
    monkeypatch.setattr(r, 'launch', fake_launch)
    args = types.SimpleNamespace(mode='check', run_dir=None, output_root=tmp_path / 'checks',
             dfo_python='/not-installed', fmqa_python='/not-installed', conda='',
             bonmin='/not-installed', ipopt='/not-installed', bam_license='/not-installed', cpu=4)
    r.controller(args)
    assert len(calls) == 1
