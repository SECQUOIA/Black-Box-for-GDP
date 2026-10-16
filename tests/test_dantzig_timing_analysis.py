"""Prevent mixed-host clocks and fabricated NLP totals in the publication."""

import csv
import zipfile

import pytest

import dantzig_timing_analysis as analysis
from nlp_cost_analysis import normalize_run


@pytest.mark.parametrize('host,changed,accepted', [
    ('Linux dantzig.ecn.purdue.edu kernel', False, True),
    ('Darwin local-mac kernel', False, False),
    ('Linux dantzig.ecn.purdue.edu kernel', True, False),
])
def test_reference_requires_dantzig_host_and_exact_archive_bytes(tmp_path, monkeypatch, host, changed, accepted):
    monkeypatch.setattr(analysis, 'REFERENCE', tmp_path)
    (tmp_path / 'original.csv').write_text('original CSV')
    (tmp_path / 'original.manifest.json').write_text('{}')
    path = tmp_path / 'source.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('run/platform.txt', host)
        archive.writestr('run/process_case_studies.csv', 'wrong CSV' if changed else 'original CSV')
        archive.writestr('run/process_case_studies.manifest.json', '{}')
    if accepted:
        assert analysis.verify_dantzig_reference(path, 'original')['host'] == 'dantzig.ecn.purdue.edu'
    else:
        with pytest.raises(ValueError):
            analysis.verify_dantzig_reference(path, 'original')


def test_mac_trace_is_rejected_before_cost_reconstruction():
    with pytest.raises(ValueError, match='original Dantzig trace'):
        normalize_run({}, [], 0, 'local.csv', 'macOS trace rerun')


def test_archived_completion_and_outcome_are_retained_without_inventing_missing_costs(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, 'problem', lambda spec: {'target': 10})
    spec = {'csv_name': 'test.csv', 'case_name': 'column', 'grid_size': None,
            'seed': 1, 'n_starts': 3, 'max_evaluations': 16}
    path = tmp_path / 'combined.csv'
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['csv_name', 'method', 'seed', 'n_starts',
                                'max_evals', 'total_evals', 'best_value', 'wall_time_s'])
        writer.writeheader()
        for i, method in enumerate(analysis.METHODS):
            writer.writerow({'csv_name': 'test.csv', 'method': method, 'seed': 1, 'n_starts': 3,
                             'max_evals': 16, 'total_evals': 16, 'best_value': 10 + i,
                             'wall_time_s': (i + 1) / 100})
    rows = analysis.measured_rows(path, [spec], {m: 'archive.zip' for m in analysis.METHODS})
    assert [r['measured_lookup_completion_s'] for r in rows] == [.01, .02, .03, .04]
    assert [r['lookup_solved'] for r in rows] == [True, False, False, False]
    assert all(r['nlp_inclusive_estimate_s'] is None and r['first_hit_time_s'] is None for r in rows)
    assert all(r['host'] == 'dantzig.ecn.purdue.edu' for r in rows)
