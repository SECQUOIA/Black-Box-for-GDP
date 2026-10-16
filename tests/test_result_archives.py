"""Archive-only storage retains evidence and supports the existing readers."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

import result_archives as storage


def make_archive(tmp_path, monkeypatch, *, member="run/jobs/one/result.json", corrupt=False):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    path = tmp_path / "run.zip"
    content = b'{"accepted": false}\n'
    relative = member.removeprefix("run/")
    digest = hashlib.sha256(b"different" if corrupt else content).hexdigest()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, content)
        archive.writestr("run/SHA256SUMS", f"{digest}  {relative}\n")
    entry = {"directory": "retained", "archive": "run.zip", "archive_root": "run",
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "archived_only": [{"directory": "jobs", "files": 1}]}
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"schema": 1, "datasets": {"test": entry}}))
    monkeypatch.setattr(storage, "CATALOG", catalog)
    return entry


def test_summary_directory_uses_verified_temporary_archive(tmp_path, monkeypatch):
    make_archive(tmp_path, monkeypatch)
    with storage.archived_directory(tmp_path / "retained") as directory:
        assert json.loads((directory / "jobs/one/result.json").read_text()) == {"accepted": False}
        extracted = directory
    assert not extracted.exists()
    assert not (tmp_path / "retained").exists()


def test_nonregistered_directory_is_unchanged(tmp_path):
    with storage.archived_directory(tmp_path) as directory:
        assert directory == tmp_path


def test_extract_refuses_existing_output(tmp_path, monkeypatch):
    entry = make_archive(tmp_path, monkeypatch)
    output = tmp_path / "output"
    directory = storage.extract(entry, output)
    assert (directory / "jobs/one/result.json").is_file()
    with pytest.raises(FileExistsError):
        storage.extract(entry, output)


def test_changed_archive_is_rejected_before_extraction(tmp_path, monkeypatch):
    entry = make_archive(tmp_path, monkeypatch)
    (tmp_path / "run.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Archive checksum"):
        storage.extract(entry, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("member,corrupt,message", [
    ("run/../escape", False, "Unsafe"),
    ("run/jobs/one/result.json", True, "Internal checksum"),
])
def test_invalid_archive_contents_are_rejected(tmp_path, monkeypatch, member, corrupt, message):
    entry = make_archive(tmp_path, monkeypatch, member=member, corrupt=corrupt)
    with pytest.raises(ValueError, match=message):
        storage.extract(entry, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("name", list(storage.datasets()))
def test_retained_archives_have_complete_hashes_and_expected_counts(name):
    entry = storage.datasets()[name]
    with storage.verified_zip(entry) as (_, count):
        assert count >= sum(s["files"] for s in entry["archived_only"])


def test_existing_fmqa_reader_accepts_retained_summary_directory():
    from fmqa_compare import audit_fmqa, result_directory
    path = storage.ROOT / storage.datasets()["fmqa-case"]["directory"]
    with result_directory(path) as directory:
        assert directory != path
        assert len(audit_fmqa(directory)["plan"]) == 139


def test_rbfopt_verifier_accepts_archive_only_traces():
    script = storage.ROOT / "results/grid_trace_rbfopt_20261010/verify_archive.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    assert report["saved_trajectory_files"] == 1050
    assert report["evaluation_callbacks"] == 54600


def test_standalone_fmqa_bundle_includes_archive_reader(tmp_path):
    from fmqa_benchmark_runner import bundle
    path = tmp_path / "runner.zip"
    bundle(path)
    with zipfile.ZipFile(path) as archive:
        assert "fmqa_runner/result_archives.py" in archive.namelist()
        assert "fmqa_runner/results/archives/catalog.json" in archive.namelist()
        archive.extractall(tmp_path)
    subprocess.run([sys.executable, "-c", "from fmqa_compare import result_directory"],
                   cwd=Path(tmp_path) / "fmqa_runner", check=True, capture_output=True, text=True)
