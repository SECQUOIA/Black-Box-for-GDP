"""Solver-free regression tests for the recorded FBBT and transport failures."""
import importlib
import logging
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest
from pyomo.common.errors import IntervalException
from pyomo.contrib.gdpopt import util
from pyomo.core.expr.numeric_expr import PowExpression

from experiments.grid_scip_recovery import grid_recovery as recovery
from gdp_models.grid import build_grid_gdp


def subproblem(i, j):
    m = build_grid_gdp('bohachevsky2', verify_csv=False)
    m.x.set_value(pyo.value(m.gx[i]))
    m.y.set_value(pyo.value(m.gy[j]))
    m.u = pyo.Block()
    m.u.algebraic_variable_list = [m.x, m.y]
    util.move_nonlinear_objective_to_constraints(m.u, logging.getLogger(__name__))
    for k in m.I:
        m.Xchoice[k].indicator_var.fix(k == i)
        m.Ychoice[k].indicator_var.fix(k == j)
    pyo.TransformationFactory('gdp.fix_disjuncts').apply_to(m)
    return m


def formulation(m):
    return ([(v.name, v.lb, v.ub, v.fixed) for v in m.component_data_objects(pyo.Var)],
            [(c.name, str(c.expr)) for c in m.component_data_objects(pyo.Constraint)],
            [(o.name, str(o.expr), o.sense) for o in m.component_data_objects(pyo.Objective)])


def test_reproduces_archived_failure_then_validates_all_961_points():
    fbbt = importlib.import_module('pyomo.contrib.fbbt.fbbt')
    original = fbbt._prop_bnds_root_to_leaf_map[PowExpression]
    with pytest.raises(IntervalException, match='fractional power'):
        fbbt.fbbt(subproblem(1, 11))
    with recovery.bohachevsky2_fbbt(True) as audit:
        for i in range(31):
            for j in range(31):
                m = subproblem(i, j)
                fbbt.fbbt(m)
                for v, expected in [(m.x, pyo.value(m.gx[i])), (m.y, pyo.value(m.gy[j]))]:
                    assert v.lb - 1e-6 <= expected <= v.ub + 1e-6
                expected = pyo.value(m.obj)
                assert m.u.objective_value.lb <= expected + 1e-6
                assert m.u.objective_value.ub is None or expected <= m.u.objective_value.ub + 1e-6
        assert audit['bohachevsky2_fixed_exponent_bound_resets'] > 0
    assert fbbt._prop_bnds_root_to_leaf_map[PowExpression] is original


def test_patch_preserves_formulation_and_restores_after_exception():
    m = subproblem(1, 11)
    before = formulation(m)
    fbbt = importlib.import_module('pyomo.contrib.fbbt.fbbt')
    original = fbbt._prop_bnds_root_to_leaf_map[PowExpression]
    with pytest.raises(RuntimeError):
        with recovery.bohachevsky2_fbbt(True):
            assert formulation(m) == before
            raise RuntimeError('deliberate')
    assert formulation(m) == before
    assert fbbt._prop_bnds_root_to_leaf_map[PowExpression] is original


def test_real_fractional_domain_error_is_not_suppressed():
    fbbt = importlib.import_module('pyomo.contrib.fbbt.fbbt')
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(-3, -2))
    m.y = pyo.Var(bounds=(.25, .75))
    m.c = pyo.Constraint(expr=m.x ** m.y <= 4)
    with recovery.bohachevsky2_fbbt(True), pytest.raises(IntervalException):
        fbbt.fbbt(m)


@pytest.mark.parametrize('phase', ['start', 'close'])
@pytest.mark.parametrize('failures,remaining,mutate,expected', [
    (1, 500, False, 'interface_returned'), (3, 500, False, 'stop_retry_limit'),
    (1, 30, False, 'stop_insufficient_budget'), (1, 500, True, 'stop_model_changed')])
def test_network_retries_are_bounded_journaled_and_share_deadline(tmp_path, monkeypatch, phase, failures, remaining, mutate, expected):
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(0, 1), initialize=0)
    context = SimpleNamespace(directory=tmp_path, calls=[], deadline=999.0, remaining=lambda: remaining)
    events, delays = [], []
    monkeypatch.setattr(recovery, 'emit', lambda path, event: events.append(event))

    def original(self, model, **kwargs):
        index = len(context.calls) + 1
        assert context.deadline == 999.0 and kwargs == {'solver': 'scip', 'mtype': 'mip'}
        if index <= failures:
            with (tmp_path / 'run.log').open('a') as stream:
                stream.write(f'*** Error: Error when trying to {phase} network session:\n'
                             'Curl error: Server returned nothing (no headers, no data).\n')
            context.calls.append({'index': index, 'status': 'error'})
            if mutate:
                model.x.set_value(1)
            raise RuntimeError('GAMS failed')
        context.calls.append({'index': index, 'status': 'returned'})
        return 'result'

    def call():
        return recovery.retry_solve(original, None, m, {'solver': 'scip', 'mtype': 'mip'}, context, sleep=delays.append)
    if expected == 'interface_returned':
        assert call() == 'result' and delays == [5.0]
    else:
        with pytest.raises(RuntimeError, match='GAMS failed'):
            call()
    assert events[-1]['decision'] == expected
    assert all(e['original_deadline'] == 999.0 for e in events)
    assert len(context.calls) <= 3 and sum(delays) <= 20
    if failures == 3:
        assert len(context.calls) == 3 and delays == [5.0, 15.0]


def test_old_network_log_cannot_trigger_retry_of_unrelated_error(tmp_path, monkeypatch):
    (tmp_path / 'run.log').write_text('Error when trying to start network session\n'
                                    'Curl error: Server returned nothing (no headers, no data).\n')
    m = pyo.ConcreteModel()
    context = SimpleNamespace(directory=tmp_path, calls=[], deadline=999.0, remaining=lambda: 500)
    monkeypatch.setattr(recovery, 'emit', lambda *a: pytest.fail('Unexpected retry'))

    def original(*args, **kwargs):
        context.calls.append({'index': 1, 'status': 'error'})
        raise RuntimeError('unrelated error')

    with pytest.raises(RuntimeError, match='unrelated error'):
        recovery.retry_solve(original, None, m, {}, context, sleep=lambda _: pytest.fail('Unexpected delay'))
    assert len(context.calls) == 1


def test_failed_call_cost_and_backoff_reduce_same_budget(tmp_path, monkeypatch):
    now, delays, events = [0], [], []
    context = SimpleNamespace(directory=tmp_path, calls=[], deadline=150, remaining=lambda: 150 - now[0])
    monkeypatch.setattr(recovery, 'emit', lambda path, event: events.append(event))

    def original(*args, **kwargs):
        now[0] += 60
        context.calls.append({'index': len(context.calls) + 1, 'status': 'error'})
        with (tmp_path / 'run.log').open('a') as stream:
            stream.write('Error when trying to start network session\n'
                         'Curl error: Server returned nothing (no headers, no data).\n')
        raise RuntimeError('network')

    def sleep(delay):
        delays.append(delay)
        now[0] += delay

    with pytest.raises(RuntimeError, match='network'):
        recovery.retry_solve(original, None, pyo.ConcreteModel(), {}, context, sleep=sleep)
    assert len(context.calls) == 2 and delays == [5.0]
    assert events[-1]['decision'] == 'stop_insufficient_budget'
    assert events[-1]['remaining_s'] == 25 and context.deadline == 150


def test_installed_worker_preserves_solver_keyword_and_records_policy(tmp_path, monkeypatch):
    import json
    from gdp_models import comparison as impl

    def original_solve(self, model, **kwargs):
        assert kwargs['solver'] == 'scip' and kwargs['mtype'] == 'mip'
        return 'returned'

    monkeypatch.setattr(impl.TimedGAMS, 'solve', original_solve)

    def worker(template, method, directory, config, deadline):
        monkeypatch.setattr(impl, 'CONTEXT', SimpleNamespace(directory=directory, calls=[], deadline=deadline))
        assert impl.TimedGAMS.solve(None, pyo.ConcreteModel(), solver='scip', mtype='mip') == 'returned'
        impl.save_json(directory / 'result.json', {'status': 'finished'})

    experiment = SimpleNamespace(worker=worker)
    recovery.install_worker(experiment)
    experiment.worker(SimpleNamespace(metadata={'grid_name': 'ackley'}), 'ric', tmp_path, {'time_limit': 1800}, 2000)
    assert impl.TimedGAMS.solve is original_solve
    assert json.loads((tmp_path / 'result.json').read_text())['recovery_policy'] == recovery.POLICY
    assert json.loads((tmp_path / 'recovery_policy.json').read_text())['shared_original_deadline'] == 2000
