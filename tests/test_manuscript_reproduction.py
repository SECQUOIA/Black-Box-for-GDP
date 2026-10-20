"""Solver-free companion checks: no live benchmark execution."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def companion():
    sys.path.insert(0, str(ROOT / "reproduction"))
    from tables import generate, interval, restart_cost
    from verify import verify, verify_figure8

    spec = importlib.util.spec_from_file_location(
        "companion_package", ROOT / "reproduction/package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield generate, interval, restart_cost, verify, verify_figure8, module
    sys.path.remove(str(ROOT / "reproduction"))


def test_all_table_outputs_and_frozen_evidence(companion, tmp_path):
    generate, _, _, verify, _, _ = companion
    tables = generate(tmp_path)
    assert len(tables) == 23
    assert len(list(tmp_path.glob("main_*.csv"))) == 8
    assert len(list(tmp_path.glob("supp_*.csv"))) == 15
    result = verify(tables)
    assert result["process_categories"]["execution_failed"] == 1
    assert result["terminal_only_records"] == 14
    assert result["bound_conflicts"] == 11


def test_exact_intervals_and_infinite_restart_cost(companion):
    _, interval, restart, *_ = companion
    assert interval(0)[0] == 0
    assert interval(10)[1] == 1
    assert interval(5)[0] == pytest.approx(1 - interval(5)[1])
    assert restart(0, list(range(1, 11))) == float("inf")
    assert restart(10, list(range(1, 11))) == 5.5
    assert restart(5, list(range(1, 11))) == 38.5


def test_figure8_rejects_changed_failure_marker_or_cost(companion, tmp_path):
    verify = companion[4]
    reference = json.loads(
        (ROOT / "reproduction/data/figure8_reference.json").read_text()
    )
    path = tmp_path / "figure8.json"
    path.write_text(json.dumps(reference))
    assert verify(path)["execution_failures"] == 1
    failure = next(
        r for r in reference["points"] if r["category"] == "execution_failed"
    )
    failure["marker"] = "x"
    path.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="points/categories/markers"):
        verify(path)
    failure["marker"] = "s"
    failure["completion_s"] += 1
    path.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="points/categories/markers"):
        verify(path)


def test_package_integrity_rejects_tampering_and_traversal(companion, tmp_path):
    import hashlib

    module = companion[5]
    data = b"retained evidence"
    (tmp_path / "input.csv").write_bytes(data)
    manifest = {
        "provider_revision": "test",
        "files": [
            {
                "path": "input.csv",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        ],
    }
    (tmp_path / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest))
    assert module.verify(tmp_path) == 1
    (tmp_path / "input.csv").write_bytes(b"changed")
    with pytest.raises(ValueError, match="missing or modified"):
        module.verify(tmp_path)
    manifest["files"][0]["path"] = "../input.csv"
    (tmp_path / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid or duplicate"):
        module.verify(tmp_path)


def test_packaged_source_requires_pin_and_hashes(tmp_path, monkeypatch):
    import hashlib
    from gdp_models import _sources

    base = tmp_path / "external"
    source = base / "dsda-gdp"
    source.mkdir(parents=True)
    model = source / "model.py"
    model.write_text("# original source\n")
    manifest = {
        "submodules": {"external/dsda-gdp": _sources.PINS["dsda-gdp"]},
        "files": [
            {
                "path": "external/dsda-gdp/model.py",
                "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            }
        ],
    }
    (tmp_path / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest))
    monkeypatch.setenv("RBFOPT_GDP_SOURCES", str(base))
    _sources.source_root.cache_clear()
    try:
        assert _sources.source_root("dsda-gdp") == source
        _sources.source_root.cache_clear()
        model.write_text("# changed\n")
        with pytest.raises(RuntimeError, match="hash mismatch"):
            _sources.source_root("dsda-gdp")
        manifest["submodules"]["external/dsda-gdp"] = "wrong"
        (tmp_path / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest))
        with pytest.raises(RuntimeError, match="pinned revision"):
            _sources.source_root("dsda-gdp")
    finally:
        _sources.source_root.cache_clear()
