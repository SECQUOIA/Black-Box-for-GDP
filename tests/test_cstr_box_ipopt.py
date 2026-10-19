"""Full-coordinate coverage, unchanged formulations and failure-safe exports."""

import csv
import hashlib
import subprocess
import zipfile

import pytest

import cstr_box_ipopt as runner


def protocol(sizes=runner.SIZES):
    return {"kind": runner.protocol_kind(sizes), "sizes": list(sizes),
            "coordinates": runner.coordinates(sizes), "config": {}}


def test_all_box_coordinates_are_present_once():
    rows = runner.coordinates()
    assert len(rows) == len({runner.key(r) for r in rows}) == 350
    for n in (5, 10, 15):
        subset = [r for r in rows if r["cstr_size"] == n]
        assert {tuple(r["point"]) for r in subset} == {
            (x, y) for x in range(1, n + 1) for y in range(1, n + 1)}
        assert [r["point_index"] for r in subset] == list(range(1, n * n + 1))
    assert sum(r["logical_allowed"] for r in rows) == 190


def test_20_25_plan_has_all_1025_coordinates_and_no_smaller_models():
    rows = runner.coordinates((20, 25))
    assert len(rows) == len({runner.key(r) for r in rows}) == 1025
    assert {r["cstr_size"] for r in rows} == {20, 25}
    for n in (20, 25):
        subset = [r for r in rows if r["cstr_size"] == n]
        assert {tuple(r["point"]) for r in subset} == {
            (x, y) for x in range(1, n + 1) for y in range(1, n + 1)}
        assert [r["point_index"] for r in subset] == list(range(1, n * n + 1))
    assert sum(r["logical_allowed"] for r in rows) == 535


def test_protocol_validation_preserves_legacy_and_rejects_mismatched_size():
    legacy = {"kind": runner.KIND, "coordinates": runner.coordinates()}
    assert runner.manifest_sizes(legacy) == (5, 10, 15)
    invalid = protocol((20, 25))
    invalid["sizes"] = [5, 10, 15]
    with pytest.raises(ValueError, match="Unexpected"):
        runner.manifest_sizes(invalid)
    with pytest.raises(ValueError):
        runner.coordinates((20, 20))


def test_audited_upstream_hashes_match_local_models():
    from gdp_models._sources import provenance
    assert provenance("dsda-gdp", runner.UPSTREAM_SHA256)["files_sha256"] == runner.UPSTREAM_SHA256


@pytest.mark.parametrize("size", (5, 10, 15, 20, 25))
@pytest.mark.parametrize("location", ("first", "middle", "last", "last_recycle_first"))
def test_feasible_start_preserves_model_and_satisfies_original_constraints(size, location):
    pytest.importorskip("pyomo.environ")
    from gdp_models.models import prepare_nlp
    from gdp_models.evaluation import primal_violation

    point = {"first": (1, 1), "middle": (3, 2), "last": (size, size),
             "last_recycle_first": (size, 1)}[location]
    prepared = prepare_nlp("cstr", point, cstr_size=size, initialization="default")
    before = runner.formulation_fingerprint(prepared)
    runner.initialize_feasible(prepared)
    assert runner.formulation_fingerprint(prepared) == before
    assert primal_violation(prepared) <= 1e-8
    assert prepared.metadata["initialization"] == runner.INITIALIZATION
    if location == "first":
        assert prepared.metadata["initial_objective"] == pytest.approx(0.94 / 0.095)


@pytest.mark.parametrize("size", (5, 10, 15, 20, 25))
def test_logically_impossible_point_is_measured_without_solver(size, monkeypatch):
    from gdp_models import evaluation

    def forbidden(*args, **kwargs):
        pytest.fail("A logical rejection must not invoke a solver")

    monkeypatch.setattr(evaluation, "optimizer_for", forbidden)
    result = evaluation.evaluate_point("cstr", (1, size), cstr_size=size,
                                       solver="gams_ipopt", initialization="default")
    assert result["status"] == "preprocessing_infeasible"
    assert result["accepted"] is False
    assert result["solve_wall_s"] == 0
    assert result["total_wall_s"] > 0


@pytest.mark.parametrize("sizes", ((5, 10, 15), (20, 25)))
def test_partial_run_exports_pending_and_failed_coordinates_and_resumes(tmp_path, monkeypatch, sizes):
    expected = sum(n * n for n in sizes)
    calls = []

    def fake(directory, row, config):
        calls.append(runner.key(row))
        result = {**row, "solver": "gams_ipopt", "status": "rejected", "accepted": False,
                  "candidate_objective": 9.0, "total_wall_s": 0.2}
        runner.write_json(directory / "records" / (runner.key(row) + ".json"), result)
        return result

    monkeypatch.setattr(runner, "run_point", fake)
    first = runner.run_points(tmp_path, protocol(sizes), max_points=2)
    assert first["completed_points"] == 2 and first["pending_points"] == expected - 2
    with (tmp_path / "evaluations.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == expected
    assert rows[0]["status"] == "rejected" and rows[0]["objective"] == ""
    assert rows[2]["status"] == "pending" and rows[2]["accepted"] == ""
    runner.run_points(tmp_path, protocol(sizes), max_points=1)
    assert len(calls) == len(set(calls)) == 3
    for size in sizes:
        with (tmp_path / f"cstr_{size}" / "evaluations.csv").open() as f:
            assert len(list(csv.DictReader(f))) == size * size
    archive = tmp_path.with_name(tmp_path.name + ".zip")
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for line in z.read(tmp_path.name + "/SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(z.read(tmp_path.name + "/" + name)).hexdigest() == digest


def test_failed_worker_keeps_coordinate_and_unknown_time(tmp_path, monkeypatch):
    (tmp_path / "records").mkdir()
    (tmp_path / "logs").mkdir()
    row = runner.coordinates()[0]
    monkeypatch.setattr(runner, "run_child", lambda *a: {
        "worker_pid": 123, "worker_returncode": -15,
        "worker_timed_out": True, "worker_process_wall_s": 180.5})
    report = runner.run_point(tmp_path, row, {"executable": "/gams", "time_limit": 60,
                                             "worker_timeout": 180})
    assert report["status"] == "worker_timeout" and report["point"] == [1, 1]
    assert "total_wall_s" not in report
    runner.write_json(tmp_path / "run.json", protocol())
    summary, _ = runner.summarize(tmp_path)
    assert summary["unknown_evaluation_times"] == 1
    assert summary["completed_points"] == 1


@pytest.mark.parametrize("sizes", ((5, 10, 15), (20, 25)))
def test_bundle_contains_verified_sources_and_selected_plan(tmp_path, sizes):
    archive = tmp_path / "runner.zip"
    runner.bundle(archive, sizes)
    with zipfile.ZipFile(archive) as z:
        prefix = runner.BUNDLE_NAME + "/"
        assert all(name.startswith(prefix) for name in z.namelist())
        assert not any("/results/" in name or "/.git/" in name for name in z.namelist())
        for line in z.read(prefix + "RUNNER_SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(z.read(prefix + name)).hexdigest() == digest
        import io
        rows = list(csv.DictReader(io.StringIO(z.read(prefix + "coordinates.csv").decode())))
        assert len(rows) == sum(n * n for n in sizes)
        assert {int(r["cstr_size"]) for r in rows} == set(sizes)
        launcher = tmp_path / "run.sh"
        launcher.write_bytes(z.read(prefix + "run.sh"))
        # Capture arguments without starting Python, model preparation or a solver.
        (tmp_path / "run_cstr_box_ipopt_dantzig.sh").write_text('printf "%s\\n" "$@"\n')
        result = subprocess.run(["bash", str(launcher), "run", "--cpu", "4"],
                                capture_output=True, text=True, check=True)
        assert result.stdout.splitlines() == ["run", "--sizes", *map(str, sizes), "--cpu", "4"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive.with_suffix(".zip.sha256").read_text().split()[0]


def test_worker_command_uses_the_requested_large_model(tmp_path, monkeypatch):
    (tmp_path / "records").mkdir()
    row = runner.coordinates((25,))[-1]
    commands = []

    def fake(command, log, timeout):
        commands.append(command)
        return {"worker_returncode": -15, "worker_timed_out": True, "worker_process_wall_s": 181}

    monkeypatch.setattr(runner, "run_child", fake)
    result = runner.run_point(tmp_path, row, {"executable": "/gams", "time_limit": 60,
                                             "worker_timeout": 180})
    command = commands[0]
    assert command[command.index("--sizes") + 1] == "25"
    assert command[command.index("--point-key") + 1] == "cstr_25_25_25"
    assert result["cstr_size"] == 25 and result["point"] == [25, 25]
