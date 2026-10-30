"""Main and supplement must partition conditions without dropping saved runs."""

import copy

import pytest

from review_comparison import joint_process_supplement as j


@pytest.fixture(scope='module')
def data():
    return j.main.load(j.base.ROOT)[0]


def test_conditions_partition_all_fourteen():
    assert len(j.CONDITIONS) == 8
    assert set(j.CONDITIONS).isdisjoint(j.main.CONDITIONS)
    assert set(j.CONDITIONS) | set(j.main.CONDITIONS) == set(j.base.CONDITIONS)


def test_all_original_dfo_rows_retained_once(data):
    combined = j.select(data) + j.main.select(data)
    dfo = [r for r in combined if r['family'] == 'DFO']
    assert len(dfo) == 700
    assert len({j.base.key(r) for r in dfo}) == 700
    for row in dfo:
        original = dict(row)
        original.pop('panel_budget')
        assert original in data


def test_conventional_repetitions_are_identical(data):
    selected = j.select(data)
    assert len(selected) == 440
    conventional = [r for r in selected if r['family'] == 'algebraic']
    assert len(conventional) == 40
    assert len({r['source'] for r in conventional}) == 25
    dynamic = [r for r in conventional if r['case'] == 'dynamic']
    assert len(dynamic) == 20
    for row in conventional:
        original = dict(row)
        original.pop('panel_budget')
        assert original in data


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'seed'])
def test_missing_or_duplicate_remaining_panel_rejected(data, mutation):
    rows = copy.deepcopy(data)
    i = next(i for i, r in enumerate(rows) if r['case'] == 'cstr_10' and r['family'] == 'DFO')
    if mutation == 'missing':
        rows.pop(i)
    elif mutation == 'duplicate':
        rows.append(rows[i])
    else:
        rows[i]['seed'] = 20
    with pytest.raises(ValueError, match='Missing|Incomplete'):
        j.select(rows)
