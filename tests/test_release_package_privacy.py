"""Committed private solver paths cannot be reintroduced through packaging."""

import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

import pytest


REMOVED_ARCHIVE = "results/archives/gdpopt_baron_highs_20261001_partial.tar.gz"


def run_git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.PIPE)


def commit_files(repo, files):
    for name, data in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    run_git(repo, "add", "--", ".")
    run_git(repo, "-c", "user.name=Publication Test", "-c",
            "user.email=publication-test@example.invalid", "commit", "-m", "Fixture")
    return run_git(repo, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def package_repo(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "reproduction"))
    spec = importlib.util.spec_from_file_location(
        "publication_package", root / "reproduction/package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "source"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(
        module, "git", lambda *args, cwd=None: run_git(cwd or repo, *args)
    )
    return module, repo


@pytest.mark.parametrize("name", [
    REMOVED_ARCHIVE,
    "external/source/" + REMOVED_ARCHIVE,
    "gamslice.dat",
    "nested/GAMSlice.dat",
    "nested/gamslice.txt",
    "nested/bamlice.txt",
])
def test_known_private_paths_fail_before_any_package_is_created(package_repo, tmp_path, name):
    module, repo = package_repo
    revision = commit_files(repo, {name: b"synthetic private artifact placeholder"})
    output = tmp_path / "candidate.zip"
    with pytest.raises(ValueError, match="Private solver-license artifact"):
        module.build(revision, output)
    assert not output.exists()
    assert not output.with_suffix(".zip.sha256").exists()
    assert not output.with_suffix(".package.json").exists()


def test_pinned_submodule_is_checked_before_zip_creation(package_repo, tmp_path):
    module, repo = package_repo
    sub = repo / "external/source"
    sub.mkdir(parents=True)
    run_git(sub, "init", "--initial-branch=main")
    sub_revision = commit_files(sub, {"gamslice.dat": b"synthetic private placeholder"})
    run_git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sub_revision},external/source")
    run_git(repo, "-c", "user.name=Publication Test", "-c",
            "user.email=publication-test@example.invalid", "commit", "-m", "Pin fixture source")
    output = tmp_path / "candidate.zip"
    with pytest.raises(ValueError, match="external/source/gamslice.dat"):
        module.build("HEAD", output)
    assert not output.exists()


def test_normal_package_retains_notices_manuscript_and_integrity(package_repo, tmp_path):
    module, repo = package_repo
    files = {
        "LICENSE": b"Original project MIT notice\n",
        "vendor/source/LICENSE.md": b"Upstream open-source notice\n",
        "external/source/.env": b"PYTHONPATH=.\n",
        "manuscript/main.tex": b"Committed manuscript source\n",
        "results/completed.csv": b"case,objective\nfixture,1\n",
    }
    revision = commit_files(repo, files)
    (repo / "gamslice.dat").write_bytes(b"untracked local placeholder")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    module.build(revision, first)
    module.build(revision, second)
    assert first.read_bytes() == second.read_bytes()
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == set(files) | {"PACKAGE_MANIFEST.json"}
        for name, data in files.items():
            assert archive.read(name) == data
        archive.extractall(extracted)
    assert module.verify(extracted) == len(files)
    metadata = json.loads(first.with_suffix(".package.json").read_text())
    assert metadata["provider_revision"] == revision
    assert metadata["sha256"] == module.sha(first)
    (extracted / "results/completed.csv").write_bytes(b"changed scientific data\n")
    with pytest.raises(ValueError, match="missing or modified"):
        module.verify(extracted)
