"""Regressions from the real Dantzig return, with optimization blocked."""
import io
import json
import logging
from unittest.mock import patch

import pytest

from scripts import analyze_grid_loa_dnlp_return as audit


@pytest.fixture(scope='module')
def files():
    return audit.members((audit.ROOT / 'results/archives' / audit.ARCHIVE).read_bytes())[0]


def test_real_return_replays_without_solver_and_corrects_missing_sidecar_counts(tmp_path):
    with patch('subprocess.Popen', side_effect=AssertionError('No processes during analysis')):
        first = audit.analyze(tmp_path / 'first')
        second = audit.analyze(tmp_path / 'second')
    assert first == second
    assert first['actual_fixed_solver_calls'] == first['fixed_gates_passed'] == 6
    assert first['actual_full_loa_runs'] == 3 and first['raw_reported_full_loa_runs'] == 0
    assert first['old_target_hits'] == 0 and first['new_target_hits'] == 3
    assert first['full_started_interface_attempts'] == 4876
    assert first['full_confirmed_scip_invocations'] == 4874
    assert first['full_error_interface_attempts'] == first['full_active_unjournaled_attempts'] == 1
    rows = json.loads((tmp_path / 'first/comparison.json').read_text())
    assert [r['grid_name'] for r in rows] == list(audit.GRIDS)
    assert all(r['new_termination'] == 'maxTimeLimit' and not r['global_optimality_certified'] for r in rows)
    assert all(r['actual_options_verified_from_run_log'] and not r['sidecar_actual_config_present'] for r in rows)
    assert rows[0]['first_target_grid_point'] == [3, 29] and rows[0]['final_grid_point'] == [3, 1]
    assert rows[0]['new_reported_lower_bound'] is None and rows[0]['last_discrete_lower_bound'] < 0
    assert rows[0]['first_target_elapsed_s'] < 169
    assert rows[1]['new_wrapper_status'] == rows[2]['new_wrapper_status'] == 'finished'
    assert first['new_total_worker_s'] > first['old_total_worker_s']
    for path in (tmp_path / 'first').rglob('*'):
        if path.is_file():
            assert path.read_bytes() == (tmp_path / 'second' / path.relative_to(tmp_path / 'first')).read_bytes()


def test_actual_options_must_come_from_one_real_loa_header(files):
    log = files['full/holder_table/loa/run.log'].decode()
    settings, _ = audit.effective_options(log)
    assert settings['nlp_solver_args'] == {'solver': 'scip', 'mtype': 'dnlp'}
    for bad in (log.replace('subproblem_presolve: false', 'subproblem_presolve: true'),
                log.replace('  mtype: dnlp', '  mtype: nlp'),
                log.replace('mip_presolve: true', 'mip_presolve: false'),
                log + '\nStarting GDPopt version 22.5.13 using LOA algorithm\n',
                'requested subproblem_presolve=False; nlp_solver_args.mtype=dnlp'):
        with pytest.raises(ValueError):
            audit.effective_options(bad)


def test_target_return_vectors_are_checked_against_original_constraints(files):
    variables = json.loads(files['full/michalewicz/loa/solution.json'])['variables']
    with audit.original_models(files) as (diagnostic, _):
        assert diagnostic.original_check('michalewicz', variables)['target_hit']
        changed = dict(variables, x=variables['x'] + 0.01)
        rejected = diagnostic.original_check('michalewicz', changed)
        assert not rejected['has_feasible_solution'] and not rejected['target_hit']
        assert rejected['max_primal_violation'] > audit.TOLERANCE
        assert diagnostic.original_check('michalewicz', {})['missing_variables']


def test_call_accounting_keeps_failed_and_interrupted_attempts(files):
    prefix = 'full/holder_table/loa/'
    calls = audit.jsonlines(files[prefix + 'solver_calls.jsonl'])
    active = json.loads(files[prefix + 'active_solver_call.json'])
    result = audit.call_accounting(calls, files[prefix + 'run.log'].decode(), active)
    assert result['started_interface_attempts'] == result['confirmed_scip_invocations'] + 1
    with pytest.raises(ValueError, match='Missing/duplicate'):
        audit.call_accounting(calls[1:], files[prefix + 'run.log'].decode(), active)
    prefix = 'full/shubert/loa/'
    result = audit.call_accounting(audit.jsonlines(files[prefix + 'solver_calls.jsonl']), files[prefix + 'run.log'].decode())
    assert result['error_interface_attempts'] == 1
    assert result['completed_dnlp_calls'] == 749
    assert result['confirmed_scip_invocations'] == 1498


def test_real_pyomo_tee_context_removes_external_capture_handler(files):
    """Reproduce the missing sidecar cause without constructing or solving a model."""
    from pyomo.contrib.gdpopt.util import lower_logger_level_to
    logger = logging.getLogger('grid_loa_return_test')
    observed = []

    class Capture(logging.Handler):
        def emit(self, record):
            observed.append(record.getMessage())

    handler = Capture()
    logger.addHandler(handler)
    text = files['full/holder_table/loa/run.log'].decode().split('\nIf you use this software', 1)[0]
    try:
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            with lower_logger_level_to(logger, logging.INFO, tee=True):
                logger.info(text)
            recovered, _ = audit.effective_options(output.getvalue())
        assert not observed and recovered['subproblem_presolve'] == 'false'
        assert handler in logger.handlers
    finally:
        logger.removeHandler(handler)
