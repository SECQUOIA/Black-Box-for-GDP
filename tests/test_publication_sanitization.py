"""Publication redaction cannot hide changed or missing completed results."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

import result_archives
from scripts import verify_final_process as verifier


ARCHIVE = "results/archives/gdpopt_baron_highs_20261001_partial.tar.gz"
SIDECAR = ARCHIVE + ".sha256"
INDEX = "results/archives/SHA256SUMS"
COMPLETED = "results/archives/completed.zip"


@pytest.fixture
def publication_tree(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    index_bytes = b"".join(
        line for line in (root / INDEX).read_bytes().splitlines(keepends=True)
        if ARCHIVE.encode() not in line
    )
    index = tmp_path / INDEX
    index.parent.mkdir(parents=True)
    index.write_bytes(index_bytes)
    completed = tmp_path / COMPLETED
    completed.write_bytes(b"unchanged completed experiment\n")
    files = {
        ARCHIVE: {"sha256": "65cdbd4712a8845f88e89db754a2c64b99bd8f3013f94fce2561a71f8c92ad58"},
        SIDECAR: {"sha256": "d8a27c1775d9c76f61a89a9e3279a9c7ac1021f0481e242c7fd7197b65ec4eb4"},
        INDEX: {"sha256": "db099e915b59c8cb06b7caf9f6efd2f808e678c42e0126d32c9cf13a7f42ebbf"},
        COMPLETED: {"sha256": hashlib.sha256(completed.read_bytes()).hexdigest()},
    }
    baseline = tmp_path / "baseline.json.gz"
    with gzip.open(baseline, "wt") as stream:
        json.dump({"files": files}, stream)
    manifest = {
        "before_inventory": {"path": baseline.name, "sha256": verifier.sha(baseline)},
        "documented_nondata_changes": {},
        "additional_files_sha256": {},
    }
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(result_archives, "datasets", lambda: {})
    return tmp_path, manifest, files


def test_only_documented_removals_pass_and_are_reported(publication_tree):
    root, manifest, _ = publication_tree
    baseline_before = (root / "baseline.json.gz").read_bytes()
    report = verifier.verify_preservation(manifest)
    assert report["publication_sanitization_removed_files"] == [ARCHIVE, SIDECAR]
    assert report["publication_sanitization_index_update"] == {
        "path": INDEX,
        "before_sha256": "db099e915b59c8cb06b7caf9f6efd2f808e678c42e0126d32c9cf13a7f42ebbf",
        "after_sha256": "8e709da56e86fb4defd68757d8a578f39230a046bd99e20222fb2834a287cde9",
    }
    assert report["unchanged_original_archives"] == 1
    assert report["unchanged_files_in_tree"] == 1
    assert report["missing_or_changed_experimental_artifacts"] == 0
    assert "Retained completed" in report["experimental_artifact_preservation_scope"]
    assert (root / "baseline.json.gz").read_bytes() == baseline_before


@pytest.mark.parametrize("name", [ARCHIVE, SIDECAR])
def test_removed_private_artifact_cannot_be_restored(publication_tree, name):
    root, manifest, _ = publication_tree
    (root / name).write_bytes(b"restored artifact placeholder, no credential content")
    with pytest.raises(ValueError, match="Removed private publication artifact is present"):
        verifier.verify_preservation(manifest)


def test_dangling_link_cannot_restore_a_removed_path(publication_tree):
    root, manifest, _ = publication_tree
    (root / ARCHIVE).symlink_to("missing-private-copy")
    with pytest.raises(ValueError, match="Removed private publication artifact is present"):
        verifier.verify_preservation(manifest)


@pytest.mark.parametrize("action", ["delete", "change"])
def test_completed_results_remain_protected(publication_tree, action):
    root, manifest, _ = publication_tree
    if action == "delete":
        (root / COMPLETED).unlink()
    else:
        (root / COMPLETED).write_bytes(b"changed completed result")
    with pytest.raises(ValueError, match="Missing original artifacts|Original artifact changed"):
        verifier.verify_preservation(manifest)


def test_checksum_edit_cannot_cover_other_changes(publication_tree):
    root, manifest, _ = publication_tree
    with (root / INDEX).open("ab") as stream:
        stream.write(b"unreviewed checksum entry\n")
    with pytest.raises(ValueError, match="Sanitized publication checksum index changed"):
        verifier.verify_preservation(manifest)


@pytest.mark.parametrize("name", [ARCHIVE, SIDECAR, INDEX])
def test_redaction_requires_exact_original_endpoints(publication_tree, name):
    root, manifest, files = publication_tree
    files[name]["sha256"] = "unexpected-original-hash"
    baseline = root / "baseline.json.gz"
    with gzip.open(baseline, "wt") as stream:
        json.dump({"files": files}, stream)
    manifest["before_inventory"]["sha256"] = verifier.sha(baseline)
    with pytest.raises(ValueError, match="baseline mismatch"):
        verifier.verify_preservation(manifest)


def test_baseline_inventory_itself_remains_protected(publication_tree):
    root, manifest, _ = publication_tree
    with (root / "baseline.json.gz").open("ab") as stream:
        stream.write(b"changed inventory")
    with pytest.raises(ValueError, match="Baseline inventory changed"):
        verifier.verify_preservation(manifest)
