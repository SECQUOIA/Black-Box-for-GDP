"""Differentiate returned incumbents, solver invocations and failed interfaces."""
import json
import subprocess
import sys

import pytest
from scripts import analyze_grid_gdpopt_scip_return as audit


def call(status):
    return dict(index=1,solver='scip',mtype='mip',threads=1,status=status,wall_s=60,
                solver_option_file=['gams/mipstart = 0','timing/clocktype = 2'])


@pytest.mark.parametrize('stage,confirmed',[('start',0),('close',1)])
def test_network_error_is_not_a_successful_interface_return(stage,confirmed):
    result=dict(status='error',termination='error')
    log=f'*** Error: Error when trying to {stage} network session:\n'
    if confirmed:
        log += '--- Executing SCIP (Solvelink=5)\nSCIP version 9.2.4 (a94f778ac8)\n'
        log += '    --- Executing SCIP (Solvelink=5)\n    SCIP version 9.2.4 (a94f778ac8)\n'
    kind=audit.failure_kind(result,log)
    evidence=audit.call_evidence([call('error')],None,log,kind)
    assert evidence['confirmed_scip_invocations']==confirmed
    assert evidence['error_calls']==1 and evidence['returned_calls']==0


def test_watchdog_marker_does_not_prove_solver_was_invoked():
    active=call('running')
    evidence=audit.call_evidence([],active,'','worker_watchdog')
    assert evidence['started_interface_attempts']==1
    assert evidence['confirmed_scip_invocations']==0


def test_missing_call_index_rejected():
    c=call('returned')
    c['index']=2
    with pytest.raises(ValueError,match='call indices'):
        audit.call_evidence([c],None,'','none')


def test_interval_error_is_not_classified_as_network():
    r=dict(status='error',termination='error',message='IntervalException: Cannot raise a negative variable to a fractional power.')
    assert audit.failure_kind(r,'')=='pyomo_fbbt_interval'


def test_full_return_audit_retains_errors_and_all_denominators(tmp_path):
    result=subprocess.run([sys.executable,str(audit.ROOT/'scripts/analyze_grid_gdpopt_scip_return.py'),
        '--output',str(tmp_path)],capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
    summary=json.loads((tmp_path/'summary.json').read_text())
    assert summary['jobs']==summary['returned_solutions_verified']==63
    assert summary['target_hits']==12 and summary['target_hits_without_error']==11
    assert summary['status_counts']['error']==46
    assert summary['benchmark_calls']['confirmed_scip_invocations']==33364
    assert summary['benchmark_calls']['journaled_call_attempts']==33396
    assert summary['benchmark_calls']['active_unjournaled_attempts']==1
    rows=json.loads((tmp_path/'jobs.json').read_text())
    incumbent=next(r for r in rows if (r['grid_name'],r['method'])==('styblinski_tang','ric'))
    assert incumbent['target_hit_verified'] and not incumbent['target_hit_without_error']
    shubert=next(r for r in rows if (r['grid_name'],r['method'])==('shubert','gloa'))
    assert shubert['optimal_but_misses_target'] and shubert['lower_bound_exceeds_known_minimum']
    assert sum(len(r['omitted_sealed_temporary_files']) for r in rows)==2
