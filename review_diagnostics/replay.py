"""Portable saved-vector checks; feasibility decisions and evidence remain exact."""

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPATIBILITY = 'review_diagnostics/replay_compatibility.json'
DEPENDENCIES = ('review_diagnostics/replay.py', COMPATIBILITY)


def equivalent(left, right):
    """Allow only float evaluation roundoff, never changed flags/counts/structure."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equivalent(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    if isinstance(left, float):
        return math.isfinite(left) and math.isfinite(right) and math.isclose(
            left, right, rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def residuals_match(left, right):
    # Rank each record from its own complete rows before allowing tiny residuals
    # to exchange places. No named constraint, bound, or decision is discarded.
    for record in (left, right):
        ranked = sorted(record['constraints'] + record['bounds'],
                        key=lambda r: r['violation'] or 0, reverse=True)[:20]
        if record['largest_residuals'] != ranked:
            return False
    exact = ('tolerance', 'discrete_configuration', 'configuration_matches',
             'logic_valid', 'numerically_feasible_under_stated_residual_test')
    if any(left[k] != right[k] for k in exact):
        return False
    return equivalent({k: v for k, v in left.items() if k != 'largest_residuals'},
                      {k: v for k, v in right.items() if k != 'largest_residuals'})


def sources_match(current, recorded):
    """Accept only the recorded bytes or explicitly pinned verifier-only updates.

    Original execution snapshots are still checked separately against their
    original hashes. This registry never approves model or solver changes.
    """
    if current == recorded:
        return True
    registry = json.loads((ROOT / COMPATIBILITY).read_text())
    for name, digest in registry['dependencies_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            return False
    if set(current) - set(recorded) != set(DEPENDENCIES) - set(recorded):
        return False
    if set(recorded) - set(current):
        return False
    for name, digest in recorded.items():
        if current[name] == digest:
            continue
        update = registry['verifier_updates'].get(name, {})
        if digest not in update.get('recorded_sha256', []) or current[name] != update.get('current_sha256'):
            return False
    return True
