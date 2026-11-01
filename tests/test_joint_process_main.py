"""Protect sample sizes, outcomes, and timing in the main-text display."""

import copy
import json

import pytest

from review_comparison import joint_process_main as j


@pytest.fixture(scope='module')
def data():
    return j.load(j.base.ROOT)[0]


def test_selected_observations_preserve_original_values(data):
    selected = j.select(data)
    assert len(selected) == 450
    assert sum(r['family'] == 'DFO' for r in selected) == 420
    assert len({r['source'] for r in selected if r['family'] == 'algebraic'}) == 25
    for row in selected:
        original = dict(row)
        original.pop('panel_budget')
        assert original in data
    assert any(not r['target_reached'] for r in selected)
    assert any(r['bound_conflict'] for r in selected)


def test_dynamic_reuses_same_single_observations(data):
    selected = j.select(data)
    first = [r for r in selected if r['case'] == 'dynamic' and r['family'] == 'algebraic'
             and r['panel_budget'] == 12]
    second = [r for r in selected if r['case'] == 'dynamic' and r['family'] == 'algebraic'
              and r['panel_budget'] == 30]
    assert len(first) == len(second) == 5
    for a, b in zip(first, second):
        assert {k: v for k, v in a.items() if k != 'panel_budget'} == {
            k: v for k, v in b.items() if k != 'panel_budget'}


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'seed'])
def test_incomplete_panels_rejected(data, mutation):
    rows = copy.deepcopy(data)
    i = next(i for i, r in enumerate(rows) if r['case'] == 'cstr_5' and r['family'] == 'DFO')
    if mutation == 'missing':
        rows.pop(i)
    elif mutation == 'duplicate':
        rows.append(rows[i])
    else:
        rows[i]['seed'] = 20
    with pytest.raises(ValueError, match='Missing|Incomplete'):
        j.select(rows)


def test_time_limit_is_status_not_time_rounding(data):
    selected = j.select(data)
    row = next(r for r in selected if r['case'] == 'cstr_30' and r['method'] == 'bigm')
    assert row['time_limit'] and row['completion_s'] < 1800
    assert row['target_reached']
    small = next(r for r in selected if r['case'] == 'small_batch' and r['method'] == 'bigm')
    assert not small['time_limit'] and small['completion_s'] < 1


def test_checksum_mismatch_stops_load(tmp_path):
    directory = tmp_path / j.INPUT
    directory.mkdir(parents=True)
    (directory / 'manifest.json').write_text(json.dumps({'output_sha256': {'joint_runs.csv': 'bad'}}))
    (directory / 'joint_runs.csv').write_text('changed')
    with pytest.raises(ValueError, match='Input hash mismatch'):
        j.load(tmp_path)
