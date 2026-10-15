"""Server matrix, partial result recovery, and portable archive contents."""
# ruff: noqa: E402 -- optional GDP dependencies.

import hashlib
import json
import zipfile

import pytest

pytest.importorskip("pyomo.environ")
pytest.importorskip("networkx")

from gdp_models import batch, dantzig


def test_default_matrix_counts():
    cases = ["column", "cstr", "small_batch", "dynamic"]
    sizes = [5, 10, 15, 20, 25, 30]
    jobs = dantzig.make_jobs(cases, sizes, "logical")
    assert len(jobs) == 9
    assert sum(j["candidate_count"] for j in jobs) == 1318
    assert sum(j["candidate_count"] for j in dantzig.make_jobs(cases, sizes, "box")) == 2599
    with pytest.raises(ValueError, match="Duplicate"):
        dantzig.make_jobs(["cstr"], [5, 5], "logical")


def test_three_solver_matrix_and_version_guard():
    jobs = dantzig.make_jobs(["column", "cstr", "small_batch", "dynamic"],
                            [5, 10, 15, 20, 25, 30], "logical", ["gams_ipopt", "ipopth", "conopt"])
    assert len(jobs) == 27 and sum(j["candidate_count"] for j in jobs) == 3954
    assert len({j["name"] for j in jobs}) == 27
    with pytest.raises(ValueError, match="Do not mix"):
        dantzig.make_jobs(["cstr"], [5], "logical", ["ipopt", "ipopth"])
    identities = {j["name"]: {"solver_interface": "gams_shell", "solver_version": [52, 2, 0, 0]} for j in jobs}
    dantzig.check_gams_version(jobs, identities, "52.2")
    with pytest.raises(RuntimeError, match="Expected GAMS 53"):
        dantzig.check_gams_version(jobs, identities, "53")


@pytest.fixture
def protocol(monkeypatch):
    def identity(*args):
        return {"solver_executable": "/fake/ipopt"}

    monkeypatch.setattr(batch, "_runtime_identity", identity)

    def evaluate(case, point, **kwargs):
        return {"case": case, "point": point, "solver": kwargs["solver"],
                "cstr_size": kwargs["cstr_size"] if case == "cstr" else None,
                "status": "accepted", "accepted": True,
                "objective": sum(point), "termination": "optimal", "total_wall_s": 0.25}

    monkeypatch.setattr(batch, "evaluate_point", evaluate)
    jobs = dantzig.make_jobs(["small_batch"], [], "logical")
    config = {"solver": "ipopt", "executable": "/fake/ipopt", "domain": "logical",
              "initialization": "auto", "time_limit": 60}
    return {"kind": dantzig.KIND, "created_utc": "test", "cpu": None,
            "jobs": jobs, "config": config, "runtime": dantzig._identities(jobs, config),
            "runner_sha256": dantzig.runner_hashes()}


def verify_zip(directory):
    archive_path = directory.with_name(directory.name + ".zip")
    expected = archive_path.with_suffix(".zip.sha256").read_text().split()[0]
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == expected
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert not any(name.endswith(".batch.lock") or name.endswith(".tmp") for name in names)
        checksums = archive.read(directory.name + "/SHA256SUMS").decode().splitlines()
        for line in checksums:
            digest, relative = line.split("  ", 1)
            assert hashlib.sha256(archive.read(directory.name + "/" + relative)).hexdigest() == digest
        return json.loads(archive.read(directory.name + "/summary.json"))


def test_resume_updates_archive_and_all_rows(tmp_path, protocol):
    directory = tmp_path / "run"
    result = dantzig.execute_matrix(directory, protocol, max_points=3)
    assert result["status"] == "paused" and result["completed_points"] == 3
    assert verify_zip(directory)["completed_points"] == 3
    result = dantzig.execute_matrix(directory, protocol, resume=True)
    assert result["complete"] and result["completed_points"] == 27
    assert verify_zip(directory)["completed_points"] == 27
    assert (directory / "source/gdp_models/batch.py").is_file()
    assert (directory / "summary.csv").read_text().count("small_batch") == 1


def test_three_solvers_keep_separate_results_and_resume(tmp_path, protocol):
    solvers = ["gams_ipopt", "ipopth", "conopt"]
    protocol["jobs"] = dantzig.make_jobs(["small_batch"], [], "logical", solvers)
    protocol["runtime"] = dantzig._identities(protocol["jobs"], protocol["config"])
    directory = tmp_path / "comparison"
    result = dantzig.execute_matrix(directory, protocol, max_points=1)
    assert result["completed_points"] == 3
    for solver in solvers:
        record = json.loads((directory / solver / "small_batch/records/point_000001.json").read_text())
        assert record["solver"] == solver
    result = dantzig.execute_matrix(directory, protocol, resume=True)
    assert result["complete"] and result["completed_points"] == 81
    assert {r["solver"] for r in verify_zip(directory)["cases"]} == set(solvers)


def test_interruption_archives_partial_work(tmp_path, protocol, monkeypatch):
    original = batch.evaluate_point
    count = 0

    def interrupted(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 3:
            raise KeyboardInterrupt
        return original(*args, **kwargs)

    monkeypatch.setattr(batch, "evaluate_point", interrupted)
    directory = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        dantzig.execute_matrix(directory, protocol)
    result = verify_zip(directory)
    assert result["status"] == "interrupted" and result["completed_points"] == 2


def test_case_failure_preserves_other_cases(tmp_path, protocol, monkeypatch):
    protocol["jobs"] += dantzig.make_jobs(["dynamic"], [], "logical")
    original = batch.run_batch

    def failed(case, *args, **kwargs):
        if case == "small_batch":
            raise RuntimeError("solver configuration failure")
        return original(case, *args, **kwargs)

    monkeypatch.setattr(batch, "run_batch", failed)
    directory = tmp_path / "with_failure"
    result = dantzig.execute_matrix(directory, protocol)
    assert not result["complete"] and result["error_count"] == 1
    assert result["completed_points"] == 37
    assert "solver configuration failure" in verify_zip(directory)["cases"][0]["message"]


def test_resume_rejects_runner_change(tmp_path, protocol, monkeypatch):
    directory = tmp_path / "run"
    dantzig.execute_matrix(directory, protocol, max_points=1)
    monkeypatch.setattr(dantzig, "runner_hashes", lambda: {"different": "source"})
    with pytest.raises(ValueError, match="Runner changed"):
        dantzig.execute_matrix(directory, protocol, resume=True)
    assert verify_zip(directory)["completed_points"] == 1


def test_source_bundle_contains_only_runner_and_checksums(tmp_path):
    output = tmp_path / "runner.zip"
    dantzig.bundle_runner(output)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert len(names) < 20
        for name in ("run_gdp_dantzig.sh", "run_gdp_gams_dantzig.sh"):
            assert (name in names) == (dantzig.ROOT / name).is_file()
        assert "requirements-gdp.txt" in names
        assert not any(n.startswith(("external/", "results/", "tests/")) or n.endswith(".lic") for n in names)
        for line in archive.read("GDP_RUNNER_SHA256SUMS").decode().splitlines():
            digest, relative = line.split("  ", 1)
            assert hashlib.sha256(archive.read(relative)).hexdigest() == digest


def test_source_setup_does_not_overwrite_unrelated_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("RBFOPT_GDP_SOURCES", str(tmp_path))
    folder = tmp_path / "dsda-gdp"
    folder.mkdir()
    original = folder / "notes.txt"
    original.write_text("keep")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        dantzig.setup_sources()
    assert original.read_text() == "keep"


def test_dependency_failure_stops_matrix_and_archives_completed_work(tmp_path, protocol, monkeypatch):
    from gdp_models.preflight import SetupError

    protocol["jobs"] += dantzig.make_jobs(["dynamic"], [], "logical")

    def failed(*args, **kwargs):
        raise SetupError("No module named 'sympy'")

    monkeypatch.setattr(batch, "run_batch", failed)
    directory = tmp_path / "setup_failure"
    result = dantzig.execute_matrix(directory, protocol)
    assert result["status"] == "batch_error" and not result["complete"]
    assert result["completed_points"] == 0 and result["error_count"] == 1
    assert verify_zip(directory)["cases"][1]["status"] == "pending"
    assert not (directory / "dynamic").exists()
