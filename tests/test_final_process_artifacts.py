"""Final comparison can be reconstructed without process or DFO solvers."""

import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import verify_final_process as verifier


def test_final_process_sources_selection_and_cost_replay(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "replay"
    result = subprocess.run([sys.executable, str(root / "scripts/verify_final_process.py"),
                             "--output", str(output)], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "verification.json").read_text())
    assert report["replay"]["runs"] == 560
    assert report["replay"]["selected_bam"]["identical_bam_callbacks"] == 3430
    assert report["preservation"]["missing_or_changed_experimental_artifacts"] == 0
    assert not report["new_optimization_or_nlp_experiments"]


def test_legacy_roundoff_is_reported_without_rewriting(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier.sys, "version_info", (3, 11))
    actual = tmp_path / "run_results.csv"
    expected = tmp_path / "expected.csv"
    expected.write_text("reconstructed_total_s,category\n1.0,target_reached\n")
    raw = f"reconstructed_total_s,category\n{math.nextafter(1.0, 2.0)},target_reached\n"
    actual.write_text(raw)
    differences = verifier.compare_table(actual, expected)
    assert differences[0]["ulps"] == 1
    assert actual.read_text() == raw
    actual.write_text(raw.replace("target_reached", "target_not_reached"))
    with pytest.raises(ValueError, match="Non-time cell"):
        verifier.compare_table(actual, expected)
    actual.write_text("reconstructed_total_s,category\n1.001,target_reached\n")
    with pytest.raises(ValueError, match="exceeds sum roundoff"):
        verifier.compare_table(actual, expected)


def test_derived_refresh_requires_exact_before_and_after_hashes(tmp_path, monkeypatch):
    import gzip
    import hashlib
    import result_archives

    monkeypatch.setattr(verifier, 'ROOT', tmp_path)
    monkeypatch.setattr(result_archives, 'datasets', lambda: {})
    name = 'results/gdp_comparison_current/analysis/comparison.csv'
    artifact = tmp_path / name
    artifact.parent.mkdir(parents=True)
    artifact.write_text('verified bound flags\n')
    old_hash = hashlib.sha256(b'original bound flags\n').hexdigest()
    baseline = tmp_path / 'baseline.json.gz'
    with gzip.open(baseline, 'wt') as stream:
        json.dump({'files': {name: {'sha256': old_hash}}}, stream)
    update = {'before_sha256': old_hash, 'after_sha256': verifier.sha(artifact),
              'reason': 'Recomputed bound flags', 'verification_report': 'audit.json'}
    manifest = {'before_inventory': {'path': baseline.name, 'sha256': verifier.sha(baseline)},
                'documented_nondata_changes': {}, 'additional_files_sha256': {},
                'derived_artifact_updates': {name: update}}
    report = verifier.verify_preservation(manifest)
    assert report['verified_derived_artifact_updates'] == [name]
    assert report['missing_or_changed_experimental_artifacts'] == 0
    update['before_sha256'] = 'wrong'
    with pytest.raises(ValueError, match='baseline mismatch'):
        verifier.verify_preservation(manifest)
    update['before_sha256'] = old_hash
    artifact.write_text('unexpected objective change\n')
    with pytest.raises(ValueError, match='changed after verified regeneration'):
        verifier.verify_preservation(manifest)
    manifest['derived_artifact_updates'] = {}
    with pytest.raises(ValueError, match='Original artifact changed'):
        verifier.verify_preservation(manifest)
    manifest['derived_artifact_updates'] = {'results/raw/solution.json': update}
    with pytest.raises(ValueError, match='Not a derived comparison artifact'):
        verifier.verify_preservation(manifest)


def test_documentation_update_requires_reviewed_before_and_after_bytes(tmp_path, monkeypatch):
    import gzip
    import result_archives

    monkeypatch.setattr(verifier, 'ROOT', tmp_path)
    monkeypatch.setattr(result_archives, 'datasets', lambda: {})
    name = 'results/grid_gdp_20261009/README.md'
    artifact = tmp_path / name
    artifact.parent.mkdir(parents=True)
    artifact.write_text('reviewed clarification')
    baseline = tmp_path / 'baseline.json.gz'
    with gzip.open(baseline, 'wt') as stream:
        json.dump({'files': {name: {'sha256': 'old-hash'}}}, stream)
    manifest = {'before_inventory': {'path': baseline.name, 'sha256': verifier.sha(baseline)},
                'documented_nondata_changes': {}, 'additional_files_sha256': {}}
    monkeypatch.setattr(verifier, 'DOCUMENTATION_UPDATES', {name: ('old-hash', verifier.sha(artifact))})
    assert verifier.verify_preservation(manifest)['missing_or_changed_experimental_artifacts'] == 0
    artifact.write_text('unreviewed documentation')
    with pytest.raises(ValueError, match='Reviewed documentation changed'):
        verifier.verify_preservation(manifest)
