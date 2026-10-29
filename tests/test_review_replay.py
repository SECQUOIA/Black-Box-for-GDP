"""Portable replay must retain classifications, provenance, and every named row."""

from copy import deepcopy
import json
import math

import pytest

from review_diagnostics import replay
from review_diagnostics import feasibility_tautology as tautology
from review_diagnostics.common import ROOT, read


def test_float_roundoff_is_distinct_from_flags_counts_and_nonfinite_values():
    assert replay.equivalent(1.0, math.nextafter(1.0, 2.0))
    for a, b in [(True, 1), (10, 11), (1.0, 1.00001),
                 (float('nan'), float('nan')), (float('inf'), float('inf'))]:
        assert not replay.equivalent(a, b)


def test_replay_checks_complete_residuals_and_independent_rankings():
    saved = read(ROOT / 'results/review_feasibility_tautology_20261020/residuals.json')
    current = deepcopy(saved)
    current['constraints'][0]['value'] += 1e-16
    current['constraints'][0]['violation'] = abs(current['constraints'][0]['value'])
    current['largest_residuals'] = sorted(current['constraints'] + current['bounds'],
                                        key=lambda r: r['violation'] or 0, reverse=True)[:20]
    assert replay.residuals_match(saved, current)
    current['largest_residuals'].reverse()
    assert not replay.residuals_match(saved, current)


@pytest.mark.parametrize('defect', ['flag', 'threshold', 'constraint', 'configuration', 'missing'])
def test_replay_does_not_relax_acceptance_or_drop_evidence(defect):
    saved = read(ROOT / 'results/review_feasibility_tautology_20261020/residuals.json')
    current = deepcopy(saved)
    if defect == 'flag':
        current['numerically_feasible_under_stated_residual_test'] = False
    elif defect == 'threshold':
        current['tolerance'] = math.nextafter(current['tolerance'], 1.0)
    elif defect == 'constraint':
        current['constraints'][-1]['value'] += 1e-4
    elif defect == 'configuration':
        current['configuration_matches'] = False
    else:
        current['constraints'].pop()
    assert not replay.residuals_match(saved, current)


def test_only_pinned_verifier_changes_are_accepted(monkeypatch, tmp_path):
    recorded = read(ROOT / 'results/review_feasibility_tautology_20261020/manifest.json')['verification_source_sha256']
    current = tautology.source_hashes()
    assert replay.sources_match(current, recorded)
    for name in ['gdp_models/models.py', 'review_diagnostics/feasibility_tautology.py']:
        assert not replay.sources_match(current | {name: 'unreviewed'}, recorded)
    assert not replay.sources_match(current | {'unexpected.py': 'anything'}, recorded)
    assert not replay.sources_match(current, recorded | {'missing.py': 'anything'})
    # The extra replay dependency is independently pinned as well.
    registry = json.loads((ROOT / replay.COMPATIBILITY).read_text())
    (tmp_path / replay.COMPATIBILITY).parent.mkdir(parents=True)
    (tmp_path / replay.COMPATIBILITY).write_text(json.dumps(registry))
    (tmp_path / 'review_diagnostics/replay.py').write_text('changed helper')
    monkeypatch.setattr(replay, 'ROOT', tmp_path)
    assert not replay.sources_match(current, recorded)
