"""Guard the cohort replacement, solver evidence and figure/table semantics."""

import copy
import json

import pytest

from review_comparison import joint_process_ipopt as j


@pytest.fixture(scope='module')
def data():
    return j.load(j.ROOT)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'wrong_method'])
def test_reject_incomplete_new_cohort(mutation):
    rows = [dict(instance_id=c, method=m) for c in {c for c, _ in j.old.CONDITIONS} for m in j.GDPOPT]
    if mutation == 'missing':
        rows.pop()
    elif mutation == 'duplicate':
        rows.append(rows[0])
    else:
        rows[0]['method'] = 'hull'
    with pytest.raises(ValueError, match='Missing, duplicate'):
        j.validate_new(rows)


def test_nlp_counts_require_actual_execution():
    calls = [dict(solver='ipopt', mtype='nlp', observed=dict(solver_starts=['IPOPT']), status='error'),
             dict(solver='ipopt', mtype='nlp', observed=dict(solver_starts=[])),
             dict(solver='scip', mtype='mip', observed=dict(solver_starts=['SCIP']))]
    assert j.call_counts(calls, 1) == (1, 1)
    with pytest.raises(ValueError, match='disagrees'):
        j.call_counts(calls, 2)


def test_new_witness_can_flag_an_unchanged_direct_result():
    rows = [dict(case='x', method='hull', objective=110, feasible=True, lower_bound=105),
            dict(case='x', method='ric', objective=100, feasible=True, lower_bound=None)]
    flags = j.bound_flags(rows)
    assert flags[0]['bound_conflict'] and flags[0]['witness_method'] == 'ric'
    assert flags[1]['rho'] is None and not flags[1]['bound_conflict']
    rows[1]['feasible'] = False
    assert not j.bound_flags(rows)[0]['bound_conflict']


def test_current_cohort_and_target_changes(data):
    rows, flags, _ = data
    assert len(rows) == 745
    assert sum(r['family'] == 'DFO' for r in rows) == 700
    assert sum(r['method'] in j.GDPOPT for r in rows) == 27
    assert sum(r['bound_conflict'] for r in flags) == 21
    by_key = {(r['case'], r['method']): r for r in rows if r['family'] == 'algebraic'}
    for method in ('loa', 'ric'):
        assert by_key['dynamic', method]['target_reached']
        assert not by_key['cstr_10', method]['target_reached']
        assert not by_key['cstr_25', method]['target_reached']
    assert sum(r['nlp_calls'] for r in rows if r['method'] in j.GDPOPT) == 2373
    assert all(r['nlp_calls'] == '' for r in rows if r['method'] in ('bigm', 'hull'))


def test_dfo_and_direct_numeric_records_preserved(data):
    old_rows = [j.typed(r) for r in j.old.csv_rows((j.ROOT / j.PREVIOUS / 'joint_runs.csv').read_bytes())]
    for after, before in zip(data[0], old_rows):
        if before['family'] == 'DFO':
            assert after == before
        elif before['method'] in ('bigm', 'hull'):
            for name in before:
                if name != 'bound_conflict':
                    assert after[name] == before[name]


def test_single_dynamic_records_and_full_completion_cost(data):
    rows = data[0]
    assert len([r for r in rows if r['case'] == 'dynamic' and r['family'] == 'algebraic']) == 5
    jobs = json.loads((j.ROOT / j.NEW / 'jobs.json').read_text())
    jobs = {(r['instance_id'], r['method']): r for r in jobs if r['scope'] == 'process'}
    for row in rows:
        if row['method'] in j.GDPOPT:
            job = jobs[row['case'], row['method']]
            assert row['completion_s'] == job['completion_with_preparation_seconds']
            assert row['target_reached'] == job['target_attained']
    summary = j.old.summaries(rows)
    assert all(r['runs'] == 1 and r['completion_q25_s'] == r['completion_q75_s'] == ''
               for r in summary if r['family'] == 'algebraic')


def test_fragment_uses_current_counts_and_explains_differences(data):
    text = j.supplement(j.old.summaries(data[0]))
    assert 'confirmed IPOPT NLP interface calls' in text
    assert 'confirmed SCIP NLP interface calls' not in text
    assert text.count('Dynamic &') == 6
    assert 'not first-target time' in text
    assert 'not additional runs' in text
    assert 'equally costly subproblems' in text
    assert 'conventional GDP target' not in text  # legend belongs to the figure


def test_checksum_failure_is_fatal(tmp_path):
    # Fail before any archive work if a previously published input was changed.
    dest = tmp_path / j.PREVIOUS
    dest.mkdir(parents=True)
    manifest = copy.deepcopy(json.loads((j.ROOT / j.PREVIOUS / 'manifest.json').read_text()))
    (dest / 'manifest.json').write_text(json.dumps(manifest))
    (dest / 'joint_runs.csv').write_text('changed\n')
    with pytest.raises(ValueError, match='Input hash mismatch'):
        j.load(tmp_path)
