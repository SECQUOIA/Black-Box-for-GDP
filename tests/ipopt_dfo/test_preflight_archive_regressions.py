"""Archive-backed bundles and import probes must fail closed without solvers."""
import importlib
import json
from types import SimpleNamespace
import zipfile

import pytest


@pytest.mark.parametrize('module', ['ipopt_dfo_cstr', 'ipopt_dfo_non_cstr'])
@pytest.mark.parametrize('method,missing', [
    ('rbfopt', 'rbfopt'), ('fmqa_sa', 'torch'),
    ('fmqa_sa', 'dwave.samplers'), ('dsda', 'grid_dsda'),
])
def test_preflight_rejects_unimportable_package_even_with_matching_metadata(module, method, missing, monkeypatch):
    runner = importlib.import_module(module)
    monkeypatch.setattr(runner.importlib.metadata, 'version', lambda name: runner.VERSIONS[method][name])

    def probe(name):
        if name == missing:
            raise ImportError(f'broken runtime import: {name}')
        return SimpleNamespace()

    monkeypatch.setattr(runner.importlib, 'import_module', probe)
    with pytest.raises(ImportError, match=f'broken runtime import: {missing}'):
        runner.preflight(method, {})


@pytest.mark.parametrize('module', ['ipopt_dfo_cstr', 'ipopt_dfo_non_cstr'])
def test_preflight_still_requires_sampler_symbol(module, monkeypatch):
    runner = importlib.import_module(module)
    monkeypatch.setattr(runner.importlib.metadata, 'version', lambda name: runner.VERSIONS['fmqa_sa'][name])
    monkeypatch.setattr(runner.importlib, 'import_module', lambda name: SimpleNamespace())
    with pytest.raises(AttributeError, match='SimulatedAnnealingSampler'):
        runner.preflight('fmqa_sa', {})


@pytest.mark.parametrize('module', ['build_ipopt_dfo_cstr', 'build_ipopt_dfo_non_cstr'])
def test_changed_original_archive_is_rejected_before_packaging(module, tmp_path, monkeypatch):
    builder = importlib.import_module(module)
    import result_archives
    entry = dict(builder.ORIGINAL, sha256='0' * 64)
    monkeypatch.setattr(result_archives, 'datasets', lambda: {'original-ipopt-evaluations': entry})
    output = tmp_path / 'must-not-exist.zip'
    with pytest.raises(ValueError, match='Archive checksum mismatch'):
        if module.endswith('non_cstr'):
            builder.build(output)
        else:
            builder.old_input({})
    assert not output.exists()


def test_cstr30_bundle_remains_available_when_small_size_archives_are_absent(tmp_path, monkeypatch):
    import build_ipopt_dfo_cstr as builder
    import ipopt_dfo_cstr as runner
    monkeypatch.setattr(builder, 'BOX_ARCHIVES', {
        (5, 10, 15): tmp_path / 'absent-small.zip',
        (20, 25): tmp_path / 'absent-large.zip',
    })
    output = tmp_path / 'runner.zip'
    builder.build(output)
    with zipfile.ZipFile(output) as archive:
        archive.extractall(tmp_path / 'unpacked')
    root = tmp_path / 'unpacked/ipopt_dfo_cstr_runner'
    runner.verify_inventory(root)
    table, provenance = runner.load_table(root, 'cstr_30')
    assert len(table) == 465
    assert sum(row['accepted'] == 'True' for row in table.values()) == 458
    assert provenance['source_archive_sha256'] == builder.ORIGINAL['sha256']
    assert '!/' in provenance['source_csv_absolute_at_build']
    assert len(runner.read(root / 'plan.json')) == 240
    for size in (5, 10, 15, 20, 25):
        info = json.loads((root / f'inputs/cstr_{size}/provenance.json').read_text())
        assert info['availability'] == 'not_ready'
        with pytest.raises(ValueError):
            runner.load_table(root, f'cstr_{size}')
