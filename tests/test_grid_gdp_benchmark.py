"""Process-profile parity and auditable point-budget measurements."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pyomo.environ as pyo
import pytest

import grid_gdp_benchmark as runner
from gdp_models import grid_benchmark as core
from gdp_models.grid import GRID_NAMES, GRID_DIR, _read_reference, build_grid_gdp


def test_profiles_match_selected_process_experiments():
    profile = runner.read(runner.ROOT / "grid_gdp_process_profile.json")
    for name, item in profile["reference_manifests"].items():
        assert runner.sha(runner.ROOT / name) == item["sha256"]
    for method in core.METHODS:
        config = core.method_config({"time_limit": 1800, "relative_gap": 1e-5}, method)
        assert config["time_limit"] == 1800 and config["relative_gap"] == 1e-5
        assert config["nlp_solver"] == "baron" and config["mip_solver"] == "highs"
        assert config["baron_lp_solver"] == (
            "cplex" if method in {"bigm", "hull"} else "clp"
        )


def test_all_21_analytic_models_and_baron_function_inventory():
    supported = []
    for name in GRID_NAMES:
        model = build_grid_gdp(name, verify_csv=False)
        functions = core.baron_unsupported(model)
        if not functions:
            supported.append(name)
        assert set(functions) <= {"sin", "cos"}
    assert set(supported) == {
        "camel3",
        "hosaki",
        "rosenbrock",
        "styblinski_tang",
        "sum_of_squares",
    }
    assert core.point_indices() == list(range(961))
    assert core.point_indices("0,480,960") == [0, 480, 960]
    for invalid in ("961", "0,0", "-1"):
        with pytest.raises(ValueError):
            core.point_indices(invalid)


@pytest.mark.parametrize("invoked", [True, False])
def test_point_calls_original_fixed_model_and_requires_ipopt_evidence(
    tmp_path, monkeypatch, invoked
):
    calls = []

    class FakeGAMS:
        def __init__(self, executable, version=None):
            assert executable == "/configured/gams"

        def solve(self, model, **kwargs):
            calls.append(kwargs)
            assert all(v.fixed for v in model.component_data_objects(pyo.Var))
            assert kwargs["solver"] == "ipopt" and kwargs["mtype"] == "nlp"
            assert "option threads=1;" in kwargs["add_options"]
            text = Path(kwargs["tmpdir"], "ipopt.opt").read_text()
            assert "linear_solver mumps" in text and "max_iter 3000" in text
            assert "warm_start_init_point no" in text
            value = pyo.value(model.obj)
            Path(kwargs["tmpdir"], "resultsstat.dat").write_text(
                f"name value\nMODELSTAT 1\nSOLVESTAT 1\nOBJVAL {value!r}\nETSOLVE 0.01\n"
            )
            Path(kwargs["logfile"]).write_text(
                "--- Executing IPOPT\nTotal seconds in IPOPT = 0.002\n"
                if invoked
                else "no solver invocation\n"
            )
            return SimpleNamespace(
                solution=[],
                solver=SimpleNamespace(status="ok", termination_condition="optimal"),
            )

    monkeypatch.setattr(core, "ExplicitGAMS", FakeGAMS)
    reference, _ = _read_reference(GRID_DIR / "ackley.csv")
    row = core.measure_point(
        "ackley",
        [15, 15],
        {"executable": "/configured/gams", "point_seconds": 60},
        tmp_path / "work",
        tmp_path / "ipopt.log",
        reference,
    )
    assert len(calls) == 1
    assert row["original_free_variables"] == 0
    assert row["accepted"] is invoked
    assert row["csv_abs_error"] <= 1e-12
    assert row["point_wall_s"] >= row["preparation_wall_s"] + row["solver_call_wall_s"]
    assert row["ipopt_reported_s"] == (0.002 if invoked else None)


def test_journal_preserves_complete_rows_and_repairs_only_torn_tail(tmp_path):
    path = tmp_path / "evaluations.jsonl"
    runner.append_record(path, {"point": [1, 2], "cost": 0.03})
    with path.open("ab") as stream:
        stream.write(b'{"record":')
    assert runner.journal(path) == [{"point": [1, 2], "cost": 0.03}]
    assert runner.journal(path, repair=True) == [{"point": [1, 2], "cost": 0.03}]
    runner.append_record(path, {"point": [2, 3], "cost": 0.05})
    assert len(runner.journal(path)) == 2
    path.write_text(path.read_text().replace("0.03", "0.04"))
    with pytest.raises(ValueError, match="checksum"):
        runner.journal(path)


def test_budget_statistics_do_not_double_count_nested_timers():
    records = [
        {
            "accepted": True,
            "point_wall_s": x,
            "solver_call_wall_s": 0.08,
            "preparation_wall_s": 0.01,
            "verification_wall_s": 0.01,
            "gams_solve_s": 0.02,
            "ipopt_reported_s": 0.001,
        }
        for x in (0.1, 0.2, 0.3)
    ]
    stats = core.timing_summary(records, expected=961)
    assert stats["point_wall_s"]["sum"] == pytest.approx(0.6)
    assert stats["point_wall_s"]["median"] == 0.2
    assert stats["projected_961_point_s"] == pytest.approx(192.2)
    assert stats["projection_only"] and not stats["all_points_accepted"]
    assert stats["dfo_evaluation_cost_estimates_s"]["100"] == pytest.approx(20)


def test_point_resume_skips_accepted_and_retries_failed(tmp_path, monkeypatch):
    config = {"cpu": None, "point_indices": [0, 480, 960]}
    runner.save(tmp_path / "run.json", {"config": config})
    reference, _ = _read_reference(GRID_DIR / "ackley.csv")
    job = tmp_path / "points/ackley"
    job.mkdir(parents=True)

    def record(index):
        point = [index // 31, index % 31]
        return {
            "grid_name": "ackley",
            "point": point,
            "flat_index": index,
            "accepted": True,
            "ipopt_invoked": True,
            "threads": 1,
            "objective": reference[tuple(point)],
        }

    runner.append_record(job / "evaluations.jsonl", record(0))
    runner.append_record(job / "failures.jsonl", {**record(480), "accepted": False})
    before = (job / "failures.jsonl").read_bytes()
    visited = []

    def measure(name, point, *args):
        index = point[0] * 31 + point[1]
        visited.append(index)
        return record(index)

    monkeypatch.setattr(core, "measure_point", measure)
    monkeypatch.setattr(core, "prepare_grid", lambda name: (None, {"grid_name": name}))
    runner.point_worker(tmp_path, "ackley")
    assert visited == [480, 960]
    assert len(runner.journal(job / "evaluations.jsonl")) == 3
    assert (job / "failures.jsonl").read_bytes() == before
    assert runner.read(job / "complete.json")["points"] == 3


def test_solution_check_uses_selected_coordinates_and_reference(tmp_path):
    template = core.grid_template("sum_of_squares")
    model = template.model
    from gdp_models.grid import fix_grid_point

    fix_grid_point(model, [15, 15])
    values = {
        v.name: v.value
        for v in model.component_data_objects(
            pyo.Var, descend_into=core.comparison.DESCEND
        )
    }
    runner.save(tmp_path / "solution.json", {"variables": values})
    record = core.check_grid_solution(
        template, tmp_path, {"has_feasible_solution": True}
    )
    assert record["grid_point"] == [15, 15]
    assert record["target_hit"] and record["grid_validation"] == "passed"


def test_bundle_is_standalone_and_includes_all_grid_formulas(tmp_path):
    output = tmp_path / "grid_gdp_runner.zip"
    runner.bundle(output)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert len([n for n in archive.namelist() if "/benchmark_grids/" in n]) == 21
        assert "grid_gdp_runner/gdp_models/grid.py" in archive.namelist()
        for line in archive.read("grid_gdp_runner/SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert (
                hashlib.sha256(archive.read("grid_gdp_runner/" + name)).hexdigest()
                == digest
            )


def test_parallel_resume_is_rejected(tmp_path):
    with runner.locked(tmp_path):
        with pytest.raises(RuntimeError, match="active"):
            with runner.locked(tmp_path):
                pass


def test_gams_available_and_cached_version_do_not_run_hidden_solver(monkeypatch):
    import sys

    solver = core.ExplicitGAMS(sys.executable, (52, 2, 0, 0))
    monkeypatch.setattr(
        solver, "_run_simple_model", lambda *args: pytest.fail("Hidden GAMS call")
    )
    assert solver.available()
    assert solver.version() == (52, 2, 0, 0)


def test_completed_benchmark_checksums_prevent_silent_modification(tmp_path):
    runner.save(tmp_path / "result.json", {"status": "finished"})
    (tmp_path / "run.log").write_text("solver evidence")
    runner.seal_benchmark(tmp_path)
    assert runner.benchmark_complete(tmp_path)
    (tmp_path / "run.log").write_text("modified evidence")
    with pytest.raises(ValueError, match="checksum"):
        runner.benchmark_complete(tmp_path)


def test_resume_recovers_benchmark_interrupted_before_result_creation(
    tmp_path, monkeypatch
):
    import gdp_compare

    job = tmp_path / "benchmark/sum_of_squares/ric"
    job.mkdir(parents=True)
    (job / "run.log").write_text("interrupted before first result")
    config = {
        "phases": ["benchmark"],
        "grids": ["sum_of_squares"],
        "methods": ["ric"],
    }
    calls = []

    def solve(template, method, directory, options, target):
        calls.append(method)
        directory.mkdir(parents=True)
        runner.save(directory / "result.json", {"status": "finished"})

    monkeypatch.setattr(gdp_compare, "run_job", solve)
    monkeypatch.setattr(runner, "source_hashes", lambda: {})
    monkeypatch.setattr(runner, "runtime", lambda config: {})
    monkeypatch.setattr(runner, "summarize", lambda directory: {})
    monkeypatch.setattr(runner, "pack", lambda directory: None)
    run = {"config": config, "source_sha256": {}, "runtime": {}}
    runner.execute(tmp_path, run)
    runner.execute(tmp_path, run)
    assert calls == ["ric"]
    assert runner.benchmark_complete(job)
    old_logs = list(
        (tmp_path / "previous_attempts").glob("sum_of_squares/ric_*/run.log")
    )
    assert len(old_logs) == 1
    assert old_logs[0].read_text() == "interrupted before first result"


def retry_parent(tmp_path):
    directory = tmp_path / "original"
    config = {
        "grids": ["ackley", "camel3", "alpine1"],
        "methods": ["ric", "gloa", "loa"],
        "phases": ["points", "benchmark"], "point_indices": list(range(961)),
        "cpu": 6, "time_limit": 1800, "relative_gap": 1e-5,
    }
    runner.save(directory / "run.json", {
        "kind": runner.KIND, "config": config, "runtime": {}, "source_sha256": {},
    })
    cases = [
        ("ackley", "ric", "error", "RuntimeError: GAMS", "network session\nCurl error: no data"),
        ("ackley", "gloa", "finished", "", ""),
        ("ackley", "loa", "hard_time_limit", "", ""),
        ("camel3", "ric", "finished", "", ""),
        ("camel3", "gloa", "error", "IntervalException: fractional power", ""),
        ("camel3", "loa", "unsupported_expression", "", ""),
        ("alpine1", "ric", "error", "RuntimeError: different failure", ""),
        ("alpine1", "gloa", "finished", "", ""),
        ("alpine1", "loa", "error", "DifferentiationException: abs(0)", ""),
    ]
    for name, method, status, message, log in cases:
        job = directory / "benchmark" / name / method
        runner.save(job / "result.json", {"status": status, "message": message})
        (job / "run.log").write_text(log)
        runner.seal_benchmark(job)
    return directory


def directory_hashes(directory):
    return {str(p.relative_to(directory)): runner.sha(p) for p in directory.rglob("*") if p.is_file()}


def test_retry_selection_uses_error_status_and_log_cause(tmp_path):
    directory = retry_parent(tmp_path)
    before = directory_hashes(directory)
    _, selected = runner.select_error_jobs(directory)
    assert [(r["grid_name"], r["method"]) for r in selected] == [
        ("ackley", "ric"), ("camel3", "gloa"), ("alpine1", "ric"), ("alpine1", "loa"),
    ]
    for kind in ("network", "fbbt", "differentiation", "other"):
        _, selected = runner.select_error_jobs(directory, kind)
        assert len(selected) == 1 and selected[0]["error_kind"] == kind
    assert directory_hashes(directory) == before


def test_retry_rejects_modified_failed_result(tmp_path):
    directory = retry_parent(tmp_path)
    (directory / "benchmark/ackley/ric/run.log").write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        runner.select_error_jobs(directory)


def test_retry_dry_run_does_not_invoke_runtime_or_write(tmp_path, monkeypatch):
    directory = retry_parent(tmp_path)
    before = directory_hashes(directory)
    monkeypatch.setattr(runner, "runtime", lambda *a, **k: pytest.fail("dry run invoked runtime"))
    args = SimpleNamespace(run_dir=directory, error_kind="all", dry_run=True)
    runner.retry_errors(args)
    assert directory_hashes(directory) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["original"]


def test_retry_creates_separate_run_inherits_settings_and_never_runs_points(tmp_path, monkeypatch):
    directory = retry_parent(tmp_path)
    before = directory_hashes(directory)
    calls = []
    monkeypatch.setattr(runner, "source_hashes", lambda: {})
    monkeypatch.setattr(runner, "runtime", lambda *a, **k: {})
    monkeypatch.setattr(runner, "execute", lambda d, r: calls.append((d, r)))
    args = SimpleNamespace(
        run_dir=directory, error_kind="all", dry_run=False,
        grids=None, point_indices=None, cpu=6, output_root=tmp_path / "retries",
    )
    runner.retry_errors(args)
    assert len(calls) == 1
    destination, run = calls[0]
    config = run["config"]
    assert destination.parent == args.output_root and destination != directory
    assert config["phases"] == ["benchmark"] and config["point_indices"] == []
    assert config["cpu"] == 6 and config["time_limit"] == 1800 and config["relative_gap"] == 1e-5
    assert len(runner.benchmark_plan(config)) == 4
    assert runner.read(destination / "retry_plan.json")["planned_points"] == 0
    assert directory_hashes(directory) == before


def test_retry_rejects_changed_solver_source_or_runtime(tmp_path, monkeypatch):
    directory = retry_parent(tmp_path)
    args = SimpleNamespace(
        run_dir=directory, error_kind="network", dry_run=False,
        grids=None, point_indices=None, cpu=6, output_root=tmp_path / "retries",
    )
    monkeypatch.setattr(runner, "source_hashes", lambda: {"gdp_models/comparison.py": "changed"})
    with pytest.raises(ValueError, match="unchanged models"):
        runner.retry_errors(args)
    monkeypatch.setattr(runner, "source_hashes", lambda: {})
    monkeypatch.setattr(runner, "runtime", lambda *a, **k: {"host": "different-host"})
    with pytest.raises(ValueError, match="runtime/CPU/host"):
        runner.retry_errors(args)
    assert not args.output_root.exists()


def test_retry_executes_exact_pairs_and_resume_skips_terminal_errors(tmp_path, monkeypatch):
    import gdp_compare

    config = {
        "phases": ["benchmark"], "grids": ["ackley", "camel3"],
        "methods": ["ric", "gloa"], "point_indices": [],
        "benchmark_jobs": [
            {"grid_name": "ackley", "method": "ric"},
            {"grid_name": "camel3", "method": "gloa"},
        ],
    }
    run = {"config": config, "source_sha256": {}, "runtime": {}}
    runner.save(tmp_path / "run.json", run)
    calls = []

    def solve(template, method, directory, options, target):
        calls.append((directory.parent.name, method))
        runner.save(directory / "result.json", {"status": "error", "message": "still failing"})

    monkeypatch.setattr(gdp_compare, "run_job", solve)
    monkeypatch.setattr(runner, "source_hashes", lambda: {})
    monkeypatch.setattr(runner, "runtime", lambda config: {})
    monkeypatch.setattr(runner, "launch_points", lambda *a: pytest.fail("retry ran points"))
    monkeypatch.setattr(core, "grid_template", lambda name: SimpleNamespace(metadata={
        "grid_preparation": {"unsupported_baron_functions": []},
    }))
    runner.execute(tmp_path, run)
    runner.execute(tmp_path, run)
    assert calls == [("ackley", "ric"), ("camel3", "gloa")]
    report = runner.read(tmp_path / "summary.json")
    assert report["planned_points"] == 0
    assert report["planned_benchmarks"] == report["finished_benchmarks"] == 2
    assert report["error_benchmarks"] == 2 and report["all_jobs_finished"]
    assert not (tmp_path / "benchmark/ackley/gloa").exists()
    assert not (tmp_path / "benchmark/camel3/ric").exists()


def test_retry_plan_rejects_duplicate_pairs():
    pair = {"grid_name": "ackley", "method": "ric"}
    with pytest.raises(ValueError, match="duplicate"):
        runner.benchmark_plan({"grids": ["ackley"], "methods": ["ric"], "benchmark_jobs": [pair, pair]})


def test_dry_run_flag_cannot_accidentally_launch_full_run(monkeypatch):
    monkeypatch.setattr("sys.argv", ["grid_gdp_benchmark.py", "run", "--dry-run"])
    with pytest.raises(SystemExit) as stopped:
        runner.main()
    assert stopped.value.code == 2
