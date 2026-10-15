"""Read-only checks against the archived Dantzig return; no optimizer is run."""
import copy
import json
from pathlib import Path

import pytest

from scripts import import_ipopt_dfo_cstr as audit


@pytest.fixture(scope='module')
def returned(tmp_path_factory):
    archive = audit.ROOT / 'results/archives' / (audit.RETURN_NAME + '.zip')
    root, hashes, count = audit.extract_verified(archive, tmp_path_factory.mktemp('return'))
    return root, hashes, count


def test_all_returned_callbacks_verified_without_hiding_budget_failures(returned):
    root, hashes, count = returned
    result, issues, metadata = audit.verify(root)
    assert result['slots'] == len(metadata) == 240
    assert result['callbacks'] == 5783 and result['callbacks_within_budget'] == 5764
    assert result['categories'] == {'target_reached': 97, 'target_not_reached': 124, 'execution_failed': 19}
    assert result['budget_protocol_pass'] is False and len(issues) == 19
    assert all(not i['overrun_csv_read'] and not i['overrun_value_delivered'] for i in issues)
    assert len(hashes) == 3816 and count == 1939
    assert result['local_optimizer_or_solver_calls'] == 0


def sample(root, job_id, index):
    job = root / 'jobs' / job_id
    spec = audit.runner.read(job / 'spec.json')
    table, _ = audit.runner.load_table(root / 'reproduction', spec['case'])
    event = audit.strict_jsonl(job / 'callbacks.jsonl')[index - 1]
    return event, spec, table


@pytest.mark.parametrize('field,value', [('raw_objective', 1234), ('selected_attempt_nlp_s', 0),
                                         ('accepted', False), ('cstr_size', 30)])
def test_changed_objective_acceptance_size_or_time_is_rejected(returned, field, value):
    event, spec, table = sample(returned[0], 'cstr_5_B8_seed0_bam', 2)
    event = copy.deepcopy(event)
    event[field] = value
    with pytest.raises(ValueError):
        audit.validate_callback(event, spec, table, 2)


def test_bam_extra_request_is_kept_separate_from_ipopt_failure(returned):
    event, spec, table = sample(returned[0], 'cstr_25_B36_seed0_bam', 37)
    audit.validate_callback(event, spec, table, 37)
    assert event['source_row'] is None and event['raw_objective'] is None
    assert event['evaluation_state'] == 'invalid_callback' and event['budget_overrun']
    assert table[tuple(event['point'])]['accepted'] == 'True'
    assert event['selected_attempt_nlp_s'] is None
    event = copy.deepcopy(event)
    event['source_row'] = table[tuple(event['point'])]
    with pytest.raises(ValueError, match='source differs'):
        audit.validate_callback(event, spec, table, 37)


def test_recorded_rejection_keeps_original_status_and_candidate(returned):
    root = returned[0]
    for job in (root / 'jobs').glob('cstr_10_*'):
        events = audit.strict_jsonl(job / 'callbacks.jsonl')
        for event in events:
            if event['source_row'] and event['source_row']['status'] == 'rejected':
                spec = audit.runner.read(job / 'spec.json')
                table, _ = audit.runner.load_table(root / 'reproduction', spec['case'])
                audit.validate_callback(event, spec, table, event['index'])
                assert event['point'] == [10, 1] and event['evaluation_state'] == 'evaluated_unaccepted'
                assert event['raw_objective'] is None and event['raw_candidate_objective'] == 3.4479640316604105
                assert event['source_row']['termination'] == 'feasible'
                return
    pytest.fail('Expected the original N10 rejection to remain in the callback ledger')


def test_input_checksum_change_is_rejected(returned, tmp_path):
    import shutil
    original = returned[0] / 'reproduction/inputs/cstr_5'
    copied = tmp_path / 'inputs/cstr_5'
    shutil.copytree(original, copied)
    (copied / 'evaluations.csv').write_bytes((copied / 'evaluations.csv').read_bytes() + b'\n')
    with pytest.raises(ValueError, match='checksum mismatch'):
        audit.runner.load_table(tmp_path, 'cstr_5')
