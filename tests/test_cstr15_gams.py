"""Single-allocation GAMS export, complete-vector gates and replay; no solver."""

from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

from review_diagnostics import cstr15_gams as g
from review_diagnostics.common import read, save, sha


@pytest.fixture(scope='module')
def model_inputs():
    pytest.importorskip('pyomo.environ')
    pytest.importorskip('sympy')
    pytest.importorskip('networkx')
    if not (g.ROOT / 'external/dsda-gdp/gdp/cstr/gdp_reactor.py').exists():
        pytest.skip('Pinned CSTR source required')
    return g.inputs(g.INPUT)


@pytest.fixture
def prepared(tmp_path, monkeypatch, model_inputs):
    monkeypatch.setattr(g, 'inspect_environment', lambda *a: {'gams_executable': sys.executable, 'mock_for_test_only': True})
    output = tmp_path / 'prepared'
    g.prepare(g.INPUT, output, Path(sys.executable), tmp_path / 'one_call.json')
    return output


def log_text(history):
    options = '\n'.join(f'{key} = {value} yes' for key, value in g.OPTIONS.items())
    return (f'--- Executing IPOPT (Solvelink=5)\n{options}\n'
            f"This is Ipopt version {history['ipopt_version']}, running with linear solver MUMPS {history['mumps_version']}.\n"
            'Number of Iterations....: 4\nEXIT: Optimal Solution Found.\n')


def test_historical_environment_is_from_archive():
    history = g.historical_environment()
    assert history['runtime']['solver_version'] == [52, 2, 0, 0]
    assert history['ipopt_version'] == '3.14.19'
    assert history['mumps_version'] == '5.8.1'
    assert history['runtime']['solver_executable'] == '/package/gams/52.2/gams'


def test_model_starts_bounds_and_rows_preserved(model_inputs, tmp_path):
    reference, nlp, before, proof, evidence = model_inputs
    assert g.f.vector(reference)['variables'] != read(g.LOCAL / 'solution.json')['variables']
    assert evidence['counts'] == {
        'before': {'variables': 156, 'constraints': 306, 'equalities': 158},
        'after': {'variables': 156, 'constraints': 303, 'equalities': 155},
    }
    assert before['objective'] == pytest.approx(2.82935061823614, abs=1e-12)
    assert before['maximum_unscaled_primal_violation'] == pytest.approx(5.634494497502862e-7, abs=1e-12)
    assert proof['original_GDP_unchanged'] and proof['variables_bounds_starts_fixing_and_objective_identical']
    before_inventory = g.identities.inventory(nlp)
    mapping = g.write_gams(nlp, tmp_path / 'gams')
    assert g.identities.inventory(nlp) == before_inventory
    assert mapping['exported_free_variables'] == 156
    assert len(mapping['constraints']) == 303
    assert mapping['gams_equations_including_objective'] == 304
    assert (tmp_path / 'gams/ipopt.opt').read_text() == ''.join(f'{k} {v}\n' for k, v in g.OPTIONS.items())
    source = (tmp_path / 'gams/model.gms').read_text()
    assert source.count('SOLVE GAMS_MODEL') == 1
    assert 'GAMS_MODEL.optfile=1;' in source
    for label, row in mapping['variables'].items():
        assert row['start'] == reference.find_component(row['name']).value
        original = reference.find_component(row['name'])
        assert (row['lower'], row['upper']) == (original.lb, original.ub)
        assert label + '.l =' in source


@pytest.mark.parametrize('defect', ['free', 'false', 'near', 'continuous'])
def test_no_tolerance_based_or_unfixed_identity_removal(model_inputs, defect):
    import pyomo.environ as pyo
    nlp = g.f.prepare_fixed_nlp(model_inputs[0])
    c = nlp.find_component(g.identities.CANDIDATES[0])
    if defect == 'free':
        nlp.YF_asbinary[1].unfix()
    elif defect == 'continuous':
        nlp.extra = pyo.Var(initialize=0)
        c.set_value((1, c.body + nlp.extra, 1))
    else:
        c.set_value((1, c.body + (1 if defect == 'false' else 1e-12), 1))
    with pytest.raises(ValueError):
        g.identities.prove_identities(nlp)
    assert c.active


@pytest.mark.parametrize('content', ['v1 1\n', 'v1 1\nv2 nan\n', 'v1 1\nv2 UNDF\n', 'v1 1\nv2 2\nv2 3\n'])
def test_incomplete_nonfinite_or_duplicate_free_values_rejected(tmp_path, content):
    (tmp_path / 'solver_input').mkdir()
    (tmp_path / 'solver_input/results.dat').write_text('SYMBOL LEVEL MARGINAL\n' + content)
    mapping = {'variables': {'v1': {'name': 'x'}, 'v2': {'name': 'y'}}, 'fixed_values_substituted': {'z': 1}}
    with pytest.raises(ValueError):
        g.returned_vector(tmp_path, mapping, {'MODELSTAT': 2, 'SOLVESTAT': 1}, {'iterations': ['1'], 'exit_messages': ['EXIT: done'], 'too_few_dof': False})


def test_initial_levels_are_not_a_returned_solution(tmp_path):
    with pytest.raises(ValueError, match='No completed'):
        g.returned_vector(tmp_path, {}, {'MODELSTAT': 2, 'SOLVESTAT': 1}, {'iterations': [], 'exit_messages': [], 'too_few_dof': True})


def test_option_version_and_call_count_audit():
    history = g.historical_environment()
    text = log_text(history)
    assert g.log_evidence(text, history)['environment_and_options_confirmed']
    for altered in [text + text, text.replace('linear_solver = mumps', 'linear_solver = ma27'),
                    text.replace('tol = 1e-10', 'tol = 1e-8'), text.replace('3.14.19', '3.12.13')]:
        assert not g.log_evidence(altered, history)['environment_and_options_confirmed']


def test_two_bounds_have_correct_direction_and_gate(model_inputs):
    bounds = model_inputs[-1]['bounds']
    result = g.bound_comparisons({'objective': 3.0}, bounds, True)
    assert result['gloa']['delta'] > 0 and result['hull']['delta'] < 0
    assert result['gloa']['tightened_bound_discrepancy_persists'] is True
    assert result['hull']['tightened_bound_discrepancy_persists'] is False
    for row in g.bound_comparisons({'objective': 2.8}, bounds, False).values():
        assert row['tightened_bound_discrepancy_persists'] is None
    for row in g.bound_comparisons(None, bounds, False).values():
        assert row['objective'] is None and row['rho'] is None


def synthetic_return(directory, vector):
    mapping = read(directory / 'gams_mapping.json')
    lines = ['SYMBOL LEVEL MARGINAL']
    for label, row in mapping['variables'].items():
        lines.append(f"{label} {vector[row['name']]:.17g} 0")
    (directory / 'solver_input/results.dat').write_text('\n'.join(lines) + '\n')
    (directory / 'solver_input/resultsstat.dat').write_text('SYMBOL VALUE\nMODELSTAT 2\nSOLVESTAT 1\nOBJEST NA\n')
    (directory / 'solver_input/gams.log').write_text(log_text(read(directory / 'historical_environment.json')))
    save(directory / 'execution.json', {'timed_out': False})
    save(directory / 'worker_result.json', {'returncode': 0, 'error': None})
    save(directory / 'solver_call.json', {'mock_only': True})


def test_actual_saved_vector_rechecks_and_residual_failure_is_not_optimal(prepared):
    # Replay fixture only: no fabricated vector is published as new evidence.
    vector = read(g.LOCAL / 'solution.json')['variables']
    synthetic_return(prepared, vector)
    summary, solution, check = g.assess(prepared)
    assert summary['tightened_feasibility_passed'] and summary['execution_protocol_confirmed']
    assert summary['bounds']['gloa']['tightened_bound_discrepancy_persists'] is True
    assert summary['bounds']['hull']['tightened_bound_discrepancy_persists'] is False
    assert all(r['independently_checked'] for r in check['omitted_identities_rechecked_on_original_GDP'])
    vector = dict(vector)
    vector['Q[1]'] = 20
    synthetic_return(prepared, vector)
    summary, solution, check = g.assess(prepared)
    assert summary['returned_solution'] and not summary['tightened_feasibility_passed']
    assert summary['bounds']['gloa']['tightened_bound_discrepancy_persists'] is None
    assert summary['raw_gams_statistics']['MODELSTAT'] == 2


def test_worker_single_call_options_and_no_retry(prepared, monkeypatch):
    calls = []
    before = sha(prepared / 'solver_input/ipopt.opt')
    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(g.subprocess, 'run', fake_run)
    g.worker(prepared)
    assert len(calls) == 1
    assert 'reslim=290' in calls[0] and 'threads=1' in calls[0]
    assert sha(prepared / 'solver_input/ipopt.opt') == before
    with pytest.raises(FileExistsError):
        g.worker(prepared)
    assert len(calls) == 1
    # A second directory cannot reuse the global allocation.
    other = prepared.parent / 'other'
    other.mkdir()
    with pytest.raises(FileExistsError):
        g.claim_call(other, read(prepared / 'selection.json')['allocation_ledger'])


def test_changed_options_rejected_before_call(prepared):
    (prepared / 'solver_input/ipopt.opt').write_text('tol 1e-4\n')
    with pytest.raises(ValueError, match='Prepared input changed'):
        g.worker(prepared)
    assert not (prepared / 'solver_call.json').exists()


def test_prepare_refuses_used_output(prepared):
    with pytest.raises(FileExistsError):
        g.prepare(g.INPUT, prepared, Path(sys.executable), prepared.parent / 'ledger')


def test_timeout_kills_worker_group_and_children_once(tmp_path, monkeypatch):
    calls = []
    killed = []
    class Child:
        pid = 12345
        def wait(self, timeout=None):
            if timeout is not None:
                assert timeout == 300
                raise subprocess.TimeoutExpired('mock', timeout)
            return -9
    def popen(*args, **kwargs):
        calls.append(kwargs)
        return Child()
    monkeypatch.setattr(g.subprocess, 'Popen', popen)
    monkeypatch.setattr(g.os, 'killpg', lambda pid, sig: killed.append((pid, sig)))
    result = g.bounded_worker(['mock'], tmp_path)
    assert len(calls) == 1 and calls[0]['start_new_session'] is True
    assert killed == [(12345, signal.SIGKILL)]
    assert result['timed_out'] and result['returncode'] == -9


def test_failed_run_and_saved_recheck_never_solve(prepared, monkeypatch):
    calls = []
    def fake_worker(command, directory):
        calls.append(command)
        g.claim_call(directory, read(directory / 'selection.json')['allocation_ledger'])
        save(directory / 'worker_result.json', {'returncode': 1, 'error': 'mock option failure'})
        return {'timed_out': False, 'returncode': 0}
    monkeypatch.setattr(g, 'bounded_worker', fake_worker)
    summary = g.run(prepared)
    assert summary['actual_new_NLP_calls'] == 1 and not summary['returned_solution']
    assert summary['objective'] is None
    assert not (prepared / 'solution.json').exists()
    with pytest.raises(FileExistsError):
        g.run(prepared)
    report = g.verify(prepared)
    assert report['new_solver_calls'] == 0 and len(calls) == 1
    modified = read(prepared / 'summary.json')
    modified['tightened_feasibility_passed'] = True
    save(prepared / 'summary.json', modified)
    g.seal(prepared, 'passed')
    with pytest.raises(ValueError, match='summary disagrees'):
        g.verify(prepared)


def test_unknown_auxiliary_statistic_does_not_hide_returned_point(prepared):
    synthetic_return(prepared, read(g.LOCAL / 'solution.json')['variables'])
    summary, solution, _ = g.assess(prepared)
    assert summary['raw_gams_statistics']['OBJEST'] is None
    assert solution is not None and summary['tightened_feasibility_passed']
    (prepared / 'solver_input/resultsstat.dat').write_text('SYMBOL VALUE\nMODELSTAT NA\nSOLVESTAT 1\n')
    summary, solution, _ = g.assess(prepared)
    assert summary['raw_gams_statistics']['MODELSTAT'] is None
    assert solution is None


def test_preparation_blocker_is_preserved_without_solver_call(tmp_path, monkeypatch, model_inputs):
    def unavailable(*args):
        raise ValueError('Historical environment absent')
    monkeypatch.setattr(g, 'inspect_environment', unavailable)
    output = tmp_path / 'blocked'
    with pytest.raises(ValueError, match='environment absent'):
        g.prepare(g.INPUT, output, Path('/missing/gams'), tmp_path / 'ledger')
    assert read(output / 'preparation_failure.json')['actual_new_NLP_calls'] == 0
    assert g.verify(output)['blocked_before_solver']
    assert not (tmp_path / 'ledger').exists()
    assert not (output / 'solver_call.json').exists()


def test_complete_return_replay_and_archive_include_verification(prepared):
    import hashlib
    import json
    import zipfile
    synthetic_return(prepared, read(g.LOCAL / 'solution.json')['variables'])
    summary, solution, residuals = g.assess(prepared)
    save(prepared / 'summary.json', summary)
    save(prepared / 'solution.json', solution)
    save(prepared / 'residuals.json', residuals)
    g.report(prepared, summary)
    g.seal(prepared, summary['status'])
    save(prepared / 'verification.json', g.verify(prepared))
    archive = g.pack(prepared)
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read(prepared.name + '/RETURN_MANIFEST.json'))
        assert 'verification.json' in manifest['files_sha256']
        for name, digest in manifest['files_sha256'].items():
            assert hashlib.sha256(z.read(prepared.name + '/' + name)).hexdigest() == digest


def test_interruption_does_not_leave_worker_group_running(tmp_path, monkeypatch):
    killed = []
    class Child:
        pid = 12346
        def wait(self, timeout=None):
            if timeout is not None:
                raise KeyboardInterrupt
            return -9
    monkeypatch.setattr(g.subprocess, 'Popen', lambda *a, **kw: Child())
    monkeypatch.setattr(g.os, 'killpg', lambda pid, sig: killed.append((pid, sig)))
    with pytest.raises(KeyboardInterrupt):
        g.bounded_worker(['mock'], tmp_path)
    assert killed == [(12346, signal.SIGKILL)]
