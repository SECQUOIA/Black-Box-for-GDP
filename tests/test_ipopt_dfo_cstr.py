"""No process solves: data provenance, budgets, adapters and durable reporting."""
import csv
import json
import shutil
import sys
import types
import zipfile

import pytest

import ipopt_dfo_cstr as r
import build_ipopt_dfo_cstr as builder


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    folder = tmp_path_factory.mktemp('frozen')
    archive = folder / 'runner.zip'
    builder.build(archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(folder)
    return folder / 'ipopt_dfo_cstr_runner'


def spec(method='dsda', budget=5):
    return {'job_id': 'test', 'case': 'cstr_30', 'seed': 0, 'method': method, 'budget': budget,
            'lower': [1, 1], 'upper': [30, 30], 'starts': [[1, 1], [30, 30], [4, 3]],
            'settings': r.SETTINGS[method]}


def test_plan_240_slots_and_shared_original_designs():
    plan = builder.plan()
    assert len(plan) == len({s['job_id'] for s in plan}) == 240
    assert {s['seed'] for s in plan} == set(range(10))
    for case in r.CASES:
        for seed in range(10):
            subset = [s for s in plan if s['case'] == case and s['seed'] == seed]
            assert len({json.dumps(s['starts']) for s in subset}) == 1
            assert all(len(s['starts']) == len({tuple(p) for p in s['starts']}) == 3 for s in subset)
    assert not any('target' in s for s in plan)
    assert {(s['cstr_size'], s['budget']) for s in plan} == set(r.BUDGETS.items())
    for s in plan:
        assert s['lower'] == [1, 1] and s['upper'] == [s['cstr_size']] * 2
    first = next(s for s in plan if s['case'] == 'cstr_5' and s['seed'] == 0)
    assert first['starts'] == [[1, 2], [5, 5], [3, 2]]  # Includes a logical exclusion.


def test_frozen_sources_and_no_executable_process_models(frozen):
    r.verify_inventory(frozen)
    assert not (frozen / 'gdp_models').exists()
    assert not (frozen / 'case_study_data').exists()
    assert not list((frozen / 'case_studies').glob('*_case.py'))
    for case, count in [('cstr_5', 15), ('cstr_10', 54), ('cstr_15', 120), ('cstr_20', 210), ('cstr_25', 325), ('cstr_30', 458)]:
        table, provenance = r.load_table(frozen, case)
        assert sum(row['accepted'] == 'True' for row in table.values()) == count
        assert 'Single original' in provenance['attempt_selection']


def test_incomplete_logical_table_is_not_infeasible(frozen, tmp_path):
    shutil.copytree(frozen / 'inputs', tmp_path / 'inputs')
    p = tmp_path / 'inputs/cstr_30/evaluations.csv'
    p.write_text('\n'.join(p.read_text().splitlines()[:-1]) + '\n')
    info = r.read(p.parent / 'provenance.json')
    info['files_sha256']['evaluations.csv'] = r.sha(p)
    r.write(p.parent / 'provenance.json', info)
    with pytest.raises(ValueError, match='Incomplete'):
        r.load_table(tmp_path, 'cstr_30')


@pytest.mark.parametrize('method,kind', [('rbfopt', '+inf'), ('dsda', '+inf'), ('bam', 'nan'), ('fmqa_sa', '+inf')])
def test_failures_repeats_terminal_callback_and_missing_times(frozen, tmp_path, method, kind):
    table, _ = r.load_table(frozen, 'cstr_30')
    s = spec(method)
    s['starts'] = [[1, 2], [1, 1], [30, 30]]
    oracle = r.Oracle(s, table, tmp_path)
    for p in s['starts']:
        oracle(p)
    oracle([1, 1])
    if method == 'bam':
        assert oracle([1, 1]) == float(table[tuple([1, 1])]['objective'])
    else:
        with pytest.raises(r.BudgetStop):
            oracle([1, 1])
    assert oracle.call_count == 5
    events = r.jsonl(tmp_path / 'callbacks.jsonl')
    assert events[0]['evaluation_state'] == 'logical_exclusion_unmeasured'
    assert events[0]['method_value_kind'] == kind and events[0]['selected_attempt_nlp_s'] is None
    assert events[-1]['callback_exit'] == ('return' if method == 'bam' else 'budget_stop')
    assert events[-1]['value_returned_to_optimizer'] is (method == 'bam')
    assert events[-1]['source_row']['point'] == '[1, 1]'
    assert events[-1]['raw_objective'] == float(table[(1, 1)]['objective'])
    assert events[-1]['selected_attempt_nlp_s'] == float(table[(1, 1)]['total_wall_s'])


def test_unmeasured_allowed_point_is_never_penalized_as_infeasible(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'cstr_30')
    del table[(1, 1)]
    oracle = r.Oracle(spec(), table, tmp_path)
    with pytest.raises(r.MissingEvaluation):
        oracle([1, 1])
    assert oracle.events[0]['evaluation_state'] == 'not_evaluated'
    assert oracle.events[0]['source_row'] is None


def test_invalid_callback_is_preserved_as_execution_error(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'cstr_30')
    oracle = r.Oracle(spec(), table, tmp_path)
    with pytest.raises(ValueError, match='out-of-domain'):
        oracle([31, 4])
    assert oracle.call_count == 1
    assert oracle.events[0]['point'] == [31, 4]
    assert oracle.events[0]['callback_exit'] == 'protocol_error'


def test_dsda_all_unaccepted_starts_keeps_all_three(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'cstr_30')
    s = spec()
    s['starts'] = [[1, 2], [2, 3], [3, 4]]
    oracle = r.Oracle(s, table, tmp_path)
    with pytest.raises(RuntimeError, match='No accepted'):
        r.optimize(s, oracle, {}, tmp_path)
    assert oracle.call_count == 3 and all(not e['accepted'] for e in oracle.events)


def test_real_dsda_search_uses_full_box_and_budget(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'cstr_30')
    s = spec(budget=12)
    s['starts'] = [[30, 30], [29, 29], [28, 28]]
    oracle = r.Oracle(s, table, tmp_path)
    try:
        r.optimize(s, oracle, {}, tmp_path)
    except r.BudgetStop:
        pass
    assert 3 <= oracle.call_count <= 12
    assert [e['point'] for e in oracle.events[:3]] == s['starts']
    assert any(e['evaluation_state'] == 'logical_exclusion_unmeasured' for e in oracle.events)


def test_rbfopt_adapter_exact_settings_and_no_target(frozen, tmp_path, monkeypatch):
    table, _ = r.load_table(frozen, 'cstr_30')
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
            for p in [*self.starts, [1, 1], [1, 5]]:
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
    table, _ = r.load_table(frozen, 'cstr_30')
    s = spec('bam')
    oracle = r.Oracle(s, table, tmp_path)
    def minimize(objective, **kw):
        assert kw['options']['max_evals'] == 2
        assert kw['options']['x_evaluated'].tolist() == s['starts']
        assert oracle.call_count == 3
        objective([1, 1])
        objective([1, 5])
        return types.SimpleNamespace(status=35, success=True, nfev=2, fun=0, x=[1, 5])
    monkeypatch.setitem(sys.modules, 'bam', types.SimpleNamespace(set_license_file=lambda p: None, minimize=minimize))
    result = r.optimize(s, oracle, {'bam_license': '/license'}, tmp_path)
    assert result['status'] == 35 and result['success'] is True
    assert oracle.call_count == 5
    assert oracle.events[-1]['value_returned_to_optimizer']
    assert r.read(tmp_path / 'actual_settings.json')['budget_stop_policy'] == s['settings']['budget_stop_policy']


def test_summary_keeps_240_slots_and_ten_seed_denominators(frozen, tmp_path):
    shutil.copytree(frozen, tmp_path / 'reproduction')
    r.write(tmp_path / 'run.json', {'config': {}})
    plan = r.read(frozen / 'plan.json')
    for s in [p for p in plan if p['case'] == 'cstr_5' and p['method'] == 'dsda']:
        job = tmp_path / 'jobs' / s['job_id']
        job.mkdir(parents=True)
        r.write(job / 'result.json', {'status': 'execution_failed', 'error': 'no accepted start', 'dfo_wall_s': .1})
    rows = r.summarize(tmp_path)
    assert len(rows) == 240
    summary = r.read(tmp_path / 'summary.json')
    group = next(g for g in summary['groups'] if g['case'] == 'cstr_5' and g['method'] == 'dsda')
    assert group['execution_failed'] == 10 and group['success_rate'] == 0 and group['success_rate_denominator'] == 10
    assert summary['counts']['not_run'] == 230


def test_process_import_blocker():
    guard = r.ProcessModelImportBlocker()
    for name in ('gdp_models', 'gdp_models.evaluation', 'case_studies.cstr_case', 'cstr_box_ipopt'):
        with pytest.raises(ImportError):
            guard.find_spec(name)
    assert guard.find_spec('rbfopt') is None


def test_other_experiment_cpu_detection():
    assert r.is_other_experiment_script('/path/cstr_box_ipopt.py')
    assert r.is_other_experiment_script('/path/run_cstr_box_ipopt_dantzig.sh')
    assert r.is_other_experiment_script('/path/ipopt_dfo_non_cstr.py')
    assert r.is_other_experiment_script('/path/run_ipopt_dfo_non_cstr_dantzig.sh')


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
    assert summary['counts'] == {'not_run': 240} and len(calls) == 4
    assert directory.with_suffix('.zip').exists()


def test_actual_rbfopt_initial_callbacks_no_auxiliary_solve(frozen, tmp_path, monkeypatch):
    pytest.importorskip('rbfopt')
    table, _ = r.load_table(frozen, 'cstr_30')
    s = spec('rbfopt', budget=3)
    oracle = r.Oracle(s, table, tmp_path)
    # Exhaust at the third initial callback, before any surrogate solve.
    with pytest.raises(r.BudgetStop):
        r.optimize(s, oracle, {'bonmin': '/not-used', 'ipopt': '/not-used'}, tmp_path)
    assert [e['point'] for e in oracle.events] == s['starts']
    assert not (tmp_path / 'auxiliary_solver_calls.jsonl').exists()


def rewrite_input_csv(root, case, change):
    p = root / 'inputs' / case / 'evaluations.csv'
    with p.open() as stream:
        rows = list(csv.DictReader(stream))
    change(rows)
    with p.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    info = r.read(p.parent / 'provenance.json')
    info['files_sha256']['evaluations.csv'] = r.sha(p)
    r.write(p.parent / 'provenance.json', info)


@pytest.mark.parametrize('corruption', ['wrong_size', 'wrong_init', 'pending', 'duplicate', 'relaxed_acceptance'])
def test_model_procedure_duplicate_and_acceptance_validation(frozen, tmp_path, corruption):
    shutil.copytree(frozen / 'inputs/cstr_10', tmp_path / 'inputs/cstr_10')
    def change(rows):
        if corruption == 'duplicate':
            rows[-1] = rows[0]
        elif corruption == 'relaxed_acceptance':
            row = next(row for row in rows if row['status'] == 'rejected')
            row.update(accepted='True', status='accepted', objective=row['candidate_objective'])
        else:
            key, value = {'wrong_size': ('cstr_size', '30'), 'wrong_init': ('initialization', 'constructor_defaults'),
                          'pending': ('status', 'pending')}[corruption]
            rows[0][key] = value
    rewrite_input_csv(tmp_path, 'cstr_10', change)
    with pytest.raises(ValueError):
        r.load_table(tmp_path, 'cstr_10')


def test_n10_rejection_keeps_candidate_status_and_matching_cost(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'cstr_10')
    s = spec('bam')
    s.update(case='cstr_10', upper=[10, 10], starts=[[10, 1], [1, 1], [10, 10]])
    oracle = r.Oracle(s, table, tmp_path)
    oracle([10, 1])
    e = oracle.events[0]
    assert not e['accepted'] and e['method_value_kind'] == 'nan'
    assert e['raw_objective'] is None and e['raw_candidate_objective'] == 3.4479640316604105
    assert e['source_row']['termination'] == 'feasible' and e['source_row']['gams_solve_status'] == '4.0'
    assert e['selected_attempt_nlp_s'] == e['all_attempts_nlp_s'] == 1.6134287110180594
    assert 'status=rejected' in e['failure_reason'] and 'infeasible' not in e['evaluation_state']


def test_measured_n20_exclusion_does_not_fill_missing_breakdown(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'cstr_20')
    s = spec()
    s.update(case='cstr_20', upper=[20, 20], starts=[[1, 2], [1, 1], [20, 20]])
    oracle = r.Oracle(s, table, tmp_path)
    oracle([1, 2])
    e = oracle.events[0]
    assert e['evaluation_state'] == 'evaluated_unaccepted' and e['selected_attempt_nlp_s'] > 0
    assert e['nlp_times']['solve_wall_s'] == 0 and e['nlp_times']['preprocess_wall_s'] is None
    assert e['nlp_times']['worker_process_wall_s'] > e['selected_attempt_nlp_s']


def test_input_reports_keep_minima_and_all_failures(frozen, tmp_path):
    reports = r.write_input_report(frozen, tmp_path)
    assert all(row['availability'] == 'ready' for row in reports)
    assert all(row['best_points'] == [(row['cstr_size'], row['cstr_size'])] for row in reports)
    n30 = next(row for row in reports if row['cstr_size'] == 30)
    assert set(n30['unaccepted_logical_points']) == {(5, 1), (5, 3), (6, 2), (6, 4), (23, 2), (26, 2), (29, 3)}
    assert n30['unmeasured_logical_exclusions'] == 435
    n25 = next(row for row in reports if row['cstr_size'] == 25)
    assert n25['table_accepted_minimum'] == 2.7814825926752516


def test_swallowed_budget_stop_is_logged_as_protocol_failure(frozen, tmp_path):
    table, _ = r.load_table(frozen, 'cstr_30')
    s = spec(budget=3)
    oracle = r.Oracle(s, table, tmp_path)
    oracle(s['starts'][0])
    oracle(s['starts'][1])
    with pytest.raises(r.BudgetStop):
        oracle(s['starts'][2])
    with pytest.raises(ValueError, match='beyond B'):
        oracle([1, 1])
    assert oracle.call_count == 4 and oracle.events[-1]['budget_overrun']
    assert oracle.events[-1]['callback_exit'] == 'protocol_error' and oracle.events[-1]['source_row'] is None


def test_incomplete_size_stays_not_run_while_ready_size_proceeds(frozen, tmp_path, monkeypatch):
    # A builder with no small-size archive must still deliver the other ready sizes.
    monkeypatch.setattr(builder, 'BOX_ARCHIVES', {(5, 10, 15): tmp_path / 'pending.zip',
                       (20, 25): builder.BOX_ARCHIVES[(20, 25)]})
    archive = tmp_path / 'runner.zip'
    builder.build(archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(tmp_path)
    root = tmp_path / 'ipopt_dfo_cstr_runner'
    r.verify_inventory(root)
    with pytest.raises(ValueError):
        r.load_table(root, 'cstr_5')
    assert len(r.load_table(root, 'cstr_25')[0]) == 625
    assert len(r.read(root / 'plan.json')) == 240


def test_cpu_selection_excludes_non_cstr_and_physical_sibling(tmp_path, monkeypatch):
    import cpu_affinity
    proc = tmp_path / 'proc'
    process = proc / '204'
    (process / 'task/204').mkdir(parents=True)
    (process / 'cmdline').write_bytes(b'python\x00/path/ipopt_dfo_non_cstr.py\x00run\x00')
    actual_path = r.Path
    monkeypatch.setattr(r, 'Path', lambda value: proc if value == '/proc' else actual_path(value))
    monkeypatch.setattr(r, 'own_ancestors', lambda: {999})
    monkeypatch.setattr(r.os, 'sched_getaffinity', lambda pid: {0, 1, 2, 3} if pid == 0 else {0}, raising=False)
    monkeypatch.setattr(cpu_affinity, 'cpu_topology', lambda cpu: {'thread_siblings_list': '0,2'})
    selected = []
    monkeypatch.setattr(cpu_affinity, 'pin_cpu', lambda cpu: selected.append(cpu) or cpu)
    monkeypatch.setattr(cpu_affinity, 'affinity_record', lambda cpu: {'cpu': cpu})
    record = r.select_cpu(None)
    assert selected == [1] and record['excluded_cpus'] == [0, 2]
    assert record['observed_other_experiment_processes'][0]['pid'] == 204
    with pytest.raises(RuntimeError, match='No safe requested CPU'):
        r.select_cpu(2)


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
