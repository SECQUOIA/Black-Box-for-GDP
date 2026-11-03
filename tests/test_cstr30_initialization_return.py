"""Reject mixed-attempt results, silent target changes and missing vectors."""
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from scripts import analyze_cstr30_initialization_return as audit


@pytest.fixture
def trace():
    ev = [dict(index=i+1,point=p,accepted=True,raw_objective=v,lookup_wall_s=.01)
          for i,(p,v) in enumerate([([1,1],2.),([1,1],2.),([2,1],1.)])]
    costs = {(1,1):dict(accepted='True',objective='2',total_wall_s='4'),
             (2,1):dict(accepted='True',objective='1',total_wall_s='1')}
    return ev,dict(status='budget_completed',recorded_search_wall_s=.5),costs


def test_repeated_costs_and_last_observation_remain_charged(trace):
    computed = audit.recompute_search(*trace,3,1.)
    assert computed['hit'] and computed['callbacks'] == 3
    assert computed['cost_s'] == 9
    assert computed['completion_s'] == pytest.approx(9.47)


def test_better_final_value_does_not_silently_change_absolute_target(trace):
    computed = audit.recompute_search(*trace,3,2.)
    assert not computed['hit'] and computed['any_hit']


@pytest.mark.parametrize('field,value', [('objective','3'),('accepted','False')])
def test_mixed_attempt_objective_or_status_rejected(trace,field,value):
    trace[2][1,1][field] = value
    with pytest.raises(ValueError,match='Callback .*table mismatch'):
        audit.recompute_search(*trace,3,1.)


def test_failed_run_not_reclassified_from_its_best_value(trace):
    trace[1]['status'] = 'execution_failed'
    computed = audit.recompute_search(*trace,3,1.)
    assert computed['failed'] and not computed['hit'] and not computed['any_hit']


def test_missing_vector_value_never_uses_initialization():
    pyo = pytest.importorskip('pyomo.environ')
    model = pyo.ConcreteModel()
    model.x = pyo.Var(initialize=1,bounds=(0,2))
    model.c = pyo.Constraint(expr=model.x >= .5)
    model.obj = pyo.Objective(expr=model.x)
    prepared = SimpleNamespace(model=model,constraints=[model.c])
    with pytest.raises(ValueError,match='Undefined original constraint'):
        audit.check_vector(prepared,{})
    assert model.x.value is None


def test_archive_identity_checked_before_executing_reproduction(tmp_path):
    path = tmp_path / 'wrong.zip'
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='archive identity'):
        audit.extract_verified(path,tmp_path / 'out')


def test_full_record_audit_distinguishes_interface_attempts_from_solves(tmp_path):
    output = tmp_path / 'audit'
    result = subprocess.run([sys.executable,str(audit.ROOT / 'scripts/analyze_cstr30_initialization_return.py'),
        '--output',str(output),'--skip-models'],text=True,capture_output=True,timeout=120)
    assert result.returncode == 0,result.stdout+result.stderr
    summary = json.loads((output / 'audit_summary.json').read_text())
    assert summary['coordinates'] == 900 and summary['logical'] == 465 and summary['structural'] == 435
    assert summary['interface_attempts'] == 465
    assert summary['confirmed_cstr_ipopt_invocations'] == 464
    assert summary['failed_before_cstr_ipopt'] == [[27,10]]
    assert summary['old_accepted'] == 458 and summary['new_accepted'] == 464
    assert summary['cstr30_old_hits'] == 16 and summary['cstr30_new_hits'] == 15
    assert summary['all_cstr_old_hits'] == 98 and summary['all_cstr_new_hits'] == 97
    assert summary['all_cstr_runs'] == 300 and summary['total_search_attempts'] == 50
    assert summary['failed_point_search_visits'] == 0
    assert not summary['model_audit_completed']
    assert summary['new_optimization_calls_during_analysis'] == 0
