"""Verify the return and expose incomplete callback logging without optimizer calls."""
import copy
import shutil

import pytest

from scripts import import_ipopt_dfo_non_cstr as audit


@pytest.fixture(scope='module')
def returned(tmp_path_factory):
    archive = audit.ROOT / 'results/archives' / (audit.RETURN_NAME + '.zip')
    return audit.extract_verified(archive, tmp_path_factory.mktemp('non-cstr-return'))


def sample(root, job_id, accepted=True):
    job = root / 'jobs' / job_id
    spec = audit.runner.read(job / 'spec.json')
    table, _ = audit.runner.load_table(root / 'reproduction', spec['case'])
    events = audit.strict_jsonl(job / 'callbacks.jsonl')
    return next(e for e in events if e['accepted'] is accepted), spec, table


def test_archive_audit_keeps_original_categories_and_separate_protocol_failures(returned):
    root, hashes, count = returned
    result, issues, metadata, inputs, reviewed, groups = audit.verify(root)
    assert result['slots'] == len(metadata) == len(reviewed) == 320
    assert len(hashes) == 2679 and count == 184
    assert result['original_categories'] == {'target_reached': 190, 'target_not_reached': 129, 'execution_failed': 1}
    assert result['audit_categories'] == {'target_reached': 184, 'target_not_reached': 127, 'execution_failed': 9}
    assert result['recorded_callbacks'] == 7058 and result['actual_callbacks_lower_bound'] == 7066
    assert result['actual_callbacks_exact'] is None and result['budget_protocol_pass'] is False
    assert len(issues) == 8 and len(groups) == 32 and len(inputs) == 3
    assert result['source_status_counts']['rejected'] == 25
    assert result['nlp_time_complete_recorded_runs'] == 51
    assert result['local_optimizer_or_solver_calls'] == 0


@pytest.mark.parametrize('field,value', [('raw_objective', 1234), ('method_value', 1e6),
                                       ('selected_attempt_nlp_s', 0), ('accepted', False)])
def test_value_acceptance_or_time_tampering_is_detected(returned, field, value):
    event, spec, table = sample(returned[0], 'dynamic_B12_seed0_rbfopt')
    event = copy.deepcopy(event)
    event[field] = value
    with pytest.raises(ValueError):
        audit.validate_callback(event, spec, table, event['index'])


def test_unmeasured_exclusion_is_distinct_from_measured_preprocessing_failure(returned):
    root = returned[0]
    job = root / 'jobs/column_B16_seed0_dsda'
    events = audit.strict_jsonl(job / 'callbacks.jsonl')
    assert events[0]['source_row']['status'] == 'preprocessing_infeasible'
    assert events[0]['selected_attempt_nlp_s'] > 0
    assert events[0]['nlp_times']['preprocess_wall_s'] is None
    assert events[1]['evaluation_state'] == 'logical_exclusion_unmeasured'
    assert events[1]['selected_attempt_nlp_s'] is None
    event, spec, table = sample(root, 'column_B16_seed0_dsda', accepted=False)
    bad = copy.deepcopy(events[1])
    bad['selected_attempt_nlp_s'] = 0
    with pytest.raises(ValueError, match='NLP cost'):
        audit.validate_callback(bad, spec, table, 2)


def test_rejected_status_and_candidate_are_preserved(returned):
    root = returned[0]
    for job in (root / 'jobs').glob('column_*'):
        for event in audit.strict_jsonl(job / 'callbacks.jsonl'):
            if event['source_row'] and event['source_row']['status'] == 'rejected':
                spec = audit.runner.read(job / 'spec.json')
                table, _ = audit.runner.load_table(root / 'reproduction', 'column')
                audit.validate_callback(event, spec, table, event['index'])
                assert event['evaluation_state'] == 'evaluated_unaccepted'
                assert event['raw_objective'] is None and event['selected_attempt_nlp_s'] > 0
                assert event['source_row']['candidate_objective']
                return
    pytest.fail('Original Column rejection was not retained')


def test_proven_overrun_does_not_invent_coordinates_or_erase_target_observation(returned):
    job = returned[0] / 'jobs/dynamic_B30_seed1_bam'
    spec, result = audit.runner.read(job / 'spec.json'), audit.runner.read(job / 'result.json')
    events = audit.strict_jsonl(job / 'callbacks.jsonl')
    issue = audit.budget_issue(spec, result, events)
    assert issue['actual_callbacks_lower_bound'] == 31 and issue['actual_callbacks_exact'] is None
    assert issue['unlogged_callback_coordinates'] is None
    assert issue['overrun_csv_read'] is False and issue['overrun_value_delivered'] is False
    assert result['status'] == 'budget_completed'
    assert any(e['accepted'] and e['point'] == [1, 4] for e in events)


def test_original_guard_raises_before_logging_or_reading_extra_call(returned, tmp_path):
    event, spec, table = sample(returned[0], 'dynamic_B12_seed0_rbfopt')
    spec = {**spec, 'budget': 3}
    oracle = audit.runner.Oracle(spec, table, tmp_path)
    oracle(spec['starts'][0])
    oracle(spec['starts'][1])
    with pytest.raises(audit.runner.BudgetStop):
        oracle(spec['starts'][2])
    # No table access or logged point occurs at B+1 in the preserved runner.
    oracle.table = None
    with pytest.raises(RuntimeError, match='swallowed the hard budget stop'):
        oracle([1, 4])
    assert oracle.call_count == len(audit.strict_jsonl(tmp_path / 'callbacks.jsonl')) == 3


def test_input_checksum_tampering_is_detected(returned, tmp_path):
    shutil.copytree(returned[0] / 'reproduction/inputs/dynamic', tmp_path / 'inputs/dynamic')
    path = tmp_path / 'inputs/dynamic/evaluations.csv'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='checksum mismatch'):
        audit.runner.load_table(tmp_path, 'dynamic')
