"""Tests for the automated benchmark runner."""

import csv
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

import benchmark
from case_studies.common import generate_lhc_starting_points


def _write_tiny_grid(path):
    path.write_text(
        "x,y,z_norm\n"
        "0,0,0.0\n"
        "0,1,1.0\n"
        "0,2,2.0\n"
        "1,0,1.0\n"
        "1,1,2.0\n"
        "1,2,3.0\n"
        "2,0,2.0\n"
        "2,1,3.0\n"
        "2,2,4.0\n"
    )


def _write_sparse_grid(path):
    path.write_text(
        "x,y,z_norm\n"
        "0,0,0.0\n"
        "0,1,1.0\n"
        "1,0,1.0\n"
    )


def _fake_rbfopt(captured):
    class FakeBlackBox:
        def __init__(self, dimension, lower_bounds, upper_bounds, var_types, obj_fn):
            self.dimension = dimension
            self.lower_bounds = lower_bounds
            self.upper_bounds = upper_bounds
            self.var_types = var_types
            self.obj_fn = obj_fn

    class FakeSettings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured["settings"] = kwargs

    class FakeAlgorithm:
        def __init__(
            self,
            settings,
            black_box,
            init_node_pos=None,
            init_node_val=None,
            do_init_strategy=None,
        ):
            self.settings = settings
            self.black_box = black_box
            captured["init_node_pos"] = init_node_pos
            captured["init_node_val"] = init_node_val
            captured["do_init_strategy"] = do_init_strategy

        def optimize(self):
            best_value = None
            best_point = None
            for point in captured["init_node_pos"]:
                value = self.black_box.obj_fn(point)
                if best_value is None or value < best_value:
                    best_value = value
                    best_point = point
            return best_value, best_point, 1, len(captured["init_node_pos"]), 0

    return SimpleNamespace(
        RbfoptUserBlackBox=FakeBlackBox,
        RbfoptSettings=FakeSettings,
        RbfoptAlgorithm=FakeAlgorithm,
    )


def _fake_bam(captured):
    def set_license_file(path):
        captured["license_file"] = path

    def minimize(
        objective,
        x0,
        bounds=None,
        integrality=None,
        options=None,
        x_evaluated=None,
        f_evaluated=None,
    ):
        captured["x0"] = np.asarray(x0, dtype=float)
        captured["bounds"] = bounds
        captured["integrality"] = integrality
        captured["options"] = options
        captured["x_evaluated"] = np.asarray(x_evaluated, dtype=float)
        captured["f_evaluated"] = np.asarray(f_evaluated, dtype=float)

        candidate = np.asarray([0.0, 0.0])
        candidate_value = objective(candidate)
        best_index = int(np.argmin(captured["f_evaluated"]))
        best_value = float(captured["f_evaluated"][best_index])
        best_point = captured["x_evaluated"][best_index]
        if candidate_value < best_value:
            best_value = candidate_value
            best_point = candidate

        return SimpleNamespace(
            x=best_point,
            fun=best_value,
            nfev=int(options["max_evals"]),
            nit=1,
            status=35,
            message="fake BAM budget reached",
        )

    return SimpleNamespace(set_license_file=set_license_file, minimize=minimize)


def test_parse_int_sequence_accepts_ranges_and_lists():
    assert benchmark.parse_int_sequence("0-2,5") == [0, 1, 2, 5]
    assert benchmark.parse_int_sequence("10,30,50") == [10, 30, 50]


def test_parse_methods_normalizes_and_validates():
    assert benchmark.parse_methods("DSDA,rbfopt,BAM") == (
        "dsda",
        "rbfopt",
        "bam",
    )
    assert benchmark.normalize_methods(("DSDA", "rbfopt")) == ("dsda", "rbfopt")

    with pytest.raises(Exception, match="Unsupported method"):
        benchmark.parse_methods("dsda,unknown")


def test_benchmark_output_path_uses_unique_timestamp_for_directory(tmp_path):
    first = benchmark.benchmark_output_path(
        tmp_path / "results",
        now=datetime(2026, 6, 21, 12, 34, 56, 123456),
    )
    second = benchmark.benchmark_output_path(
        tmp_path / "results",
        now=datetime(2026, 6, 21, 12, 34, 56, 123457),
    )

    assert first.name == "benchmark_20260621_123456_123456.csv"
    assert second.name == "benchmark_20260621_123456_123457.csv"
    assert first != second


def test_benchmark_output_path_preserves_explicit_csv_path(tmp_path):
    output = tmp_path / "custom.csv"

    assert benchmark.benchmark_output_path(output) == output


def test_run_benchmark_writes_dsda_and_rbfopt_rows_with_shared_lhc(tmp_path):
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    csv_path = grids_dir / "tiny.csv"
    _write_tiny_grid(csv_path)

    captured = {}
    fake_rbfopt = _fake_rbfopt(captured)

    result_records, results_path = benchmark.run_benchmark(
        methods=("dsda", "rbfopt"),
        seeds=[0],
        n_starts=2,
        max_evals=[2],
        grids_dir=grids_dir,
        output=tmp_path / "results",
        global_search_method="sampling",
        rbfopt_module=fake_rbfopt,
    )

    expected_starts = generate_lhc_starting_points(
        n_dims=2,
        n_points=2,
        lb=np.array([0, 0]),
        ub=np.array([2, 2]),
        seed=0,
    )

    assert len(result_records) == 2
    assert [record["method"] for record in result_records] == ["DSDA", "RBFOpt"]
    assert captured["init_node_pos"].tolist() == [
        [float(value) for value in point] for point in expected_starts
    ]
    assert captured["init_node_val"] is None
    assert captured["do_init_strategy"] is False
    assert captured["settings"]["max_evaluations"] == 2
    assert captured["settings"]["global_search_method"] == "sampling"
    assert captured["settings"]["rand_seed"] == 0

    for record in result_records:
        assert record["csv_name"] == "tiny.csv"
        assert record["seed"] == 0
        assert record["n_starts"] == 2
        assert record["max_evals"] == 2
        assert record["total_evals"] == 2

    assert results_path.exists()
    assert results_path.name.startswith("benchmark_")
    assert results_path.name.endswith(".csv")

    with results_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert rows[0]["method"] == "DSDA"
    assert rows[1]["method"] == "RBFOpt"


def test_run_benchmark_writes_bam_rows_with_shared_lhc(tmp_path):
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    csv_path = grids_dir / "tiny.csv"
    _write_tiny_grid(csv_path)

    captured = {}
    fake_bam = _fake_bam(captured)

    result_records, results_path = benchmark.run_benchmark(
        methods=("bam",),
        seeds=[0],
        n_starts=2,
        max_evals=[3],
        grids_dir=grids_dir,
        output=tmp_path / "results",
        bam_license_file=tmp_path / "bamlice.txt",
        bam_module=fake_bam,
    )

    expected_starts = generate_lhc_starting_points(
        n_dims=2,
        n_points=2,
        lb=np.array([0, 0]),
        ub=np.array([2, 2]),
        seed=0,
    )

    assert len(result_records) == 1
    assert result_records[0]["method"] == "BAM"
    assert result_records[0]["total_evals"] == 3
    assert captured["license_file"] == str(tmp_path / "bamlice.txt")
    assert captured["x_evaluated"].tolist() == [
        [float(value) for value in point] for point in expected_starts
    ]
    _, grid = benchmark.load_grid_csv(csv_path)
    grid_objective = benchmark.make_grid_objective(grid)
    assert captured["f_evaluated"].tolist() == [
        float(grid_objective(point)) for point in expected_starts
    ]
    assert captured["options"]["max_evals"] == 1
    assert captured["integrality"] == [0, 1]
    assert captured["bounds"] == [(0.0, 2.0), (0.0, 2.0)]
    assert results_path.exists()


def test_bam_budget_equal_to_initial_design_skips_solver_call(tmp_path):
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    csv_path = grids_dir / "tiny.csv"
    _write_tiny_grid(csv_path)
    _, grid = benchmark.load_grid_csv(csv_path)
    lower_bounds, upper_bounds = benchmark.grid_bounds(grid)
    captured = {}

    result = benchmark.run_bam_benchmark_case(
        csv_path=csv_path,
        grid=grid,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        starting_points=[(1, 1), (0, 1)],
        seed=0,
        n_starts=2,
        max_evals=2,
        target_value=0.0,
        bam_module=_fake_bam(captured),
    )

    assert "x_evaluated" not in captured
    assert result["best_point"] == [0, 1]
    assert result["best_value"] == 1.0
    assert result["tracked_evals"] == 2


def test_run_benchmark_rejects_budget_smaller_than_initial_design(tmp_path):
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    _write_tiny_grid(grids_dir / "tiny.csv")

    with pytest.raises(ValueError, match="greater than or equal to n_starts"):
        benchmark.run_benchmark(
            methods=("dsda", "rbfopt"),
            seeds=[0],
            n_starts=3,
            max_evals=[2],
            grids_dir=grids_dir,
            output=tmp_path / "benchmark.csv",
            global_search_method="sampling",
            rbfopt_module=_fake_rbfopt({}),
        )


def test_run_benchmark_rejects_sparse_grid(tmp_path):
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    _write_sparse_grid(grids_dir / "sparse.csv")

    with pytest.raises(
        ValueError,
        match=(
            r"Benchmark grid sparse\.csv must contain a complete integer lattice; "
            r"found 3 points, expected 4"
        ),
    ):
        benchmark.run_benchmark(
            methods=("dsda",),
            seeds=[0],
            n_starts=1,
            max_evals=[1],
            grids_dir=grids_dir,
            output=tmp_path / "benchmark.csv",
        )


def test_resolve_solver_paths_empty_solver_dir_ignores_coin_bin(monkeypatch, tmp_path):
    monkeypatch.setenv("COIN_BIN", str(tmp_path / "missing_coin"))

    minlp_solver_path, nlp_solver_path = benchmark.resolve_solver_paths(solver_dir="")

    assert minlp_solver_path == ""
    assert nlp_solver_path == ""


def test_solver_rbfopt_fails_early_without_required_executables(monkeypatch, tmp_path):
    monkeypatch.delenv("COIN_BIN", raising=False)
    monkeypatch.setattr(benchmark.shutil, "which", lambda _name: None)
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    csv_path = grids_dir / "tiny.csv"
    _write_tiny_grid(csv_path)
    _, grid = benchmark.load_grid_csv(csv_path)
    lower_bounds, upper_bounds = benchmark.grid_bounds(grid)
    captured = {}

    with pytest.raises(
        FileNotFoundError,
        match=r"RBFOpt solver mode requires BONMIN and IPOPT",
    ):
        benchmark.run_rbfopt_benchmark_case(
            csv_path=csv_path,
            grid=grid,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            starting_points=[(0, 0), (1, 1)],
            seed=0,
            n_starts=2,
            max_evals=2,
            target_value=0.0,
            rbfopt_module=_fake_rbfopt(captured),
        )

    assert "settings" not in captured


def test_solver_rbfopt_resolves_required_executables_from_path(monkeypatch, tmp_path):
    monkeypatch.delenv("COIN_BIN", raising=False)
    solver_dir = tmp_path / "bin"
    solver_dir.mkdir()
    (solver_dir / "bonmin").touch()
    (solver_dir / "ipopt").touch()
    solver_paths = {
        "bonmin": str(solver_dir / "bonmin"),
        "ipopt": str(solver_dir / "ipopt"),
    }
    monkeypatch.setattr(benchmark.shutil, "which", solver_paths.get)
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    csv_path = grids_dir / "tiny.csv"
    _write_tiny_grid(csv_path)
    _, grid = benchmark.load_grid_csv(csv_path)
    lower_bounds, upper_bounds = benchmark.grid_bounds(grid)
    captured = {}

    result = benchmark.run_rbfopt_benchmark_case(
        csv_path=csv_path,
        grid=grid,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        starting_points=[(0, 0), (1, 1)],
        seed=0,
        n_starts=2,
        max_evals=2,
        target_value=0.0,
        rbfopt_module=_fake_rbfopt(captured),
    )

    assert result["minlp_solver_path"] == solver_paths["bonmin"]
    assert result["nlp_solver_path"] == solver_paths["ipopt"]
    assert captured["settings"]["minlp_solver_path"] == solver_paths["bonmin"]
    assert captured["settings"]["nlp_solver_path"] == solver_paths["ipopt"]


def test_sampling_rbfopt_does_not_validate_coin_bin(monkeypatch, tmp_path):
    monkeypatch.setenv("COIN_BIN", str(tmp_path / "missing_coin"))
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    csv_path = grids_dir / "tiny.csv"
    _write_tiny_grid(csv_path)
    _, grid = benchmark.load_grid_csv(csv_path)
    lower_bounds, upper_bounds = benchmark.grid_bounds(grid)
    captured = {}

    result = benchmark.run_rbfopt_benchmark_case(
        csv_path=csv_path,
        grid=grid,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        starting_points=[(0, 0), (1, 1)],
        seed=0,
        n_starts=2,
        max_evals=2,
        target_value=0.0,
        global_search_method="sampling",
        rbfopt_module=_fake_rbfopt(captured),
    )

    assert result["minlp_solver_path"] == ""
    assert result["nlp_solver_path"] == ""
    assert captured["settings"]["minlp_solver_path"] == ""
    assert captured["settings"]["nlp_solver_path"] == ""


def test_real_rbfopt_sampling_smoke(monkeypatch, tmp_path):
    monkeypatch.setenv("COIN_BIN", str(tmp_path / "missing_coin"))
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    csv_path = grids_dir / "tiny.csv"
    _write_tiny_grid(csv_path)
    _, grid = benchmark.load_grid_csv(csv_path)
    lower_bounds, upper_bounds = benchmark.grid_bounds(grid)

    result = benchmark.run_rbfopt_benchmark_case(
        csv_path=csv_path,
        grid=grid,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        starting_points=[(0, 0), (0, 2), (2, 0)],
        seed=0,
        n_starts=3,
        max_evals=4,
        target_value=0.0,
        global_search_method="sampling",
    )

    assert result["best_value"] == pytest.approx(0.0)
    assert result["best_point"] == [0, 0]
    assert result["tracked_evals"] == 4
    assert result["result_record"]["total_evals"] == 4
    assert result["minlp_solver_path"] == ""
    assert result["nlp_solver_path"] == ""


def test_main_accepts_cli_arguments_and_returns_output_path(tmp_path):
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    _write_tiny_grid(grids_dir / "tiny.csv")

    result_records, results_path = benchmark.main(
        [
            "--methods",
            "dsda",
            "--seeds",
            "0-1",
            "--n-starts",
            "2",
            "--max-evals",
            "2",
            "--grids-dir",
            str(grids_dir),
            "--output",
            str(tmp_path / "benchmark.csv"),
        ]
    )

    assert len(result_records) == 2
    assert results_path == tmp_path / "benchmark.csv"
    assert results_path.exists()


def test_run_benchmark_accepts_programmatic_string_sequences(tmp_path):
    grids_dir = tmp_path / "benchmark_grids"
    grids_dir.mkdir()
    _write_tiny_grid(grids_dir / "tiny.csv")

    result_records, results_path = benchmark.run_benchmark(
        methods="dsda",
        seeds="0-1",
        n_starts=2,
        max_evals="2",
        grids_dir=grids_dir,
        output=tmp_path / "benchmark.csv",
    )

    assert len(result_records) == 2
    assert [record["seed"] for record in result_records] == [0, 1]
    assert results_path.exists()
