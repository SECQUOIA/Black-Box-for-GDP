"""
Tests for grid_dsda and grid_rbfopt.

These tests verify correctness of the search functions, the absence of
module-level side effects, and guard against regressions such as the
``run_id += 1ee`` syntax error that was introduced during refactoring.
"""

import ast
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ------------------------------------------------------------------
# Syntax / import sanity
# ------------------------------------------------------------------

def test_grid_dsda_compiles():
    """grid_dsda.py must be valid Python (guards against syntax regressions)."""
    source = (ROOT / "grid_dsda.py").read_text()
    ast.parse(source, filename="grid_dsda.py")


def test_grid_rbfopt_compiles():
    """grid_rbfopt.py must be valid Python (catches the ``1ee`` literal bug)."""
    source = (ROOT / "grid_rbfopt.py").read_text()
    ast.parse(source, filename="grid_rbfopt.py")


def test_grid_dsda_import_no_side_effects(capsys):
    """Importing grid_dsda must not print or execute batch code."""
    if "grid_dsda" in sys.modules:
        del sys.modules["grid_dsda"]
    import grid_dsda  # noqa: F401
    captured = capsys.readouterr()
    assert captured.out == "", "grid_dsda produced stdout on import"


# ------------------------------------------------------------------
# grid_dsda: load_grid_csv
# ------------------------------------------------------------------

def test_load_grid_csv():
    from grid_dsda import load_grid_csv
    _, grid = load_grid_csv(str(ROOT / "qhdopt" / "ackley.csv"))
    assert len(grid) == 961  # 31x31
    assert (15, 15) in grid
    assert grid[(15, 15)] == 0.0


def _run_dsda_on_grid(grid, start_point, **kwargs):
    from grid_dsda import dsda_from_csv

    return dsda_from_csv(
        csv_path="/nonexistent/path.csv",
        start_point=start_point,
        verbose=False,
        grid=grid,
        **kwargs,
    )


# ------------------------------------------------------------------
# grid_dsda: get_neighbors (n-dimensional)
# ------------------------------------------------------------------

def test_get_neighbors_2d():
    from grid_dsda import get_neighbors
    grid = {(x, y): 0.0 for x in range(3) for y in range(3)}
    nbs = get_neighbors((1, 1), grid, diagonal=False)
    assert set(nbs) == {(0, 1), (2, 1), (1, 0), (1, 2)}


def test_get_neighbors_diagonal():
    from grid_dsda import get_neighbors
    grid = {(x, y): 0.0 for x in range(3) for y in range(3)}
    nbs = get_neighbors((1, 1), grid, diagonal=True)
    assert len(nbs) == 8


def test_get_neighbors_corner():
    from grid_dsda import get_neighbors
    grid = {(x, y): 0.0 for x in range(3) for y in range(3)}
    nbs = get_neighbors((0, 0), grid, diagonal=False)
    assert set(nbs) == {(1, 0), (0, 1)}


# ------------------------------------------------------------------
# grid_dsda: dsda_from_csv with pre-loaded grid
# ------------------------------------------------------------------

def test_dsda_from_csv_with_preloaded_grid():
    """When a grid dict is passed, csv_path should not be read."""
    from grid_dsda import load_grid_csv, dsda_from_csv

    _, grid = load_grid_csv(str(ROOT / "qhdopt" / "ackley.csv"))

    # Pass a bogus csv_path — if the function tries to read it, it will fail
    result = dsda_from_csv(
        csv_path="/nonexistent/path.csv",
        start_point=(14, 14),
        diagonal=True,
        verbose=False,
        grid=grid,
    )
    assert result["best_point"] == (15, 15)
    assert result["best_value"] == 0.0


def test_dsda_finds_optimum():
    from grid_dsda import dsda_from_csv
    csv_path = str(ROOT / "qhdopt" / "ackley.csv")
    result = dsda_from_csv(csv_path, (14, 14), diagonal=True, verbose=False)
    assert result["best_point"] == (15, 15)
    assert result["best_value"] == 0.0
    assert result["wall_time_s"] >= 0.0
    assert len(result["incumbent_trajectory"]) == result["point_evaluations"]
    assert len(result["objective_wall_times"]) == result["point_evaluations"]


def test_dsda_maximize_mode():
    grid = {
        (0, 0): 0.0,
        (0, 1): 1.0,
        (1, 0): 2.0,
        (1, 1): 3.0,
    }
    result = _run_dsda_on_grid(
        grid, start_point=(0, 0), diagonal=True, maximize=True,
    )
    assert result["best_point"] == (1, 1)
    assert result["best_value"] == 3.0


def test_dsda_tie_break_first():
    grid = {
        (0, 0): 10.0,
        (0, 1): 10.0,
        (0, 2): 10.0,
        (1, 0): 10.0,
        (1, 1): 5.0,
        (1, 2): 4.0,
        (2, 0): 10.0,
        (2, 1): 10.0,
        (2, 2): 4.0,
    }
    result = _run_dsda_on_grid(
        grid, start_point=(1, 1), diagonal=True, tie_break="first",
    )
    assert result["path"][1] == (1, 2)


def test_dsda_tie_break_nearest():
    grid = {
        (0, 0): 10.0,
        (0, 1): 10.0,
        (0, 2): 10.0,
        (1, 0): 10.0,
        (1, 1): 5.0,
        (1, 2): 4.0,
        (2, 0): 10.0,
        (2, 1): 10.0,
        (2, 2): 4.0,
    }
    result = _run_dsda_on_grid(
        grid, start_point=(1, 1), diagonal=True, tie_break="nearest",
    )
    assert result["path"][1] == (1, 2)


def test_dsda_tie_break_farthest():
    grid = {
        (0, 0): 10.0,
        (0, 1): 10.0,
        (0, 2): 10.0,
        (1, 0): 10.0,
        (1, 1): 5.0,
        (1, 2): 4.0,
        (2, 0): 10.0,
        (2, 1): 10.0,
        (2, 2): 4.0,
    }
    result = _run_dsda_on_grid(
        grid, start_point=(1, 1), diagonal=True, tie_break="farthest",
    )
    assert result["path"][1] == (2, 2)


def test_dsda_handles_three_dimensional_grid():
    grid = {
        (x, y, z): float(x + y + z)
        for x in range(2)
        for y in range(2)
        for z in range(2)
    }
    result = _run_dsda_on_grid(grid, start_point=(1, 1, 1), diagonal=True)
    assert result["best_point"] == (0, 0, 0)
    assert result["best_value"] == 0.0
    assert all(len(point) == 3 for point in result["path"])


def test_dsda_max_points_budget():
    from grid_dsda import dsda_from_csv
    csv_path = str(ROOT / "qhdopt" / "ackley.csv")
    result = dsda_from_csv(
        csv_path, (0, 0), diagonal=True, verbose=False, max_points_explored=3,
    )
    assert result["stopped_early"]
    assert result["point_evaluations"] <= 3


# ------------------------------------------------------------------
# grid_rbfopt: make_obj_funct, grid_bounds
# ------------------------------------------------------------------

def _exec_grid_rbfopt():
    """Compile grid_rbfopt.py in a namespace with rbfopt mocked out."""
    source = (ROOT / "grid_rbfopt.py").read_text()
    ns = {"__file__": str(ROOT / "grid_rbfopt.py")}
    mock_rbfopt = type(sys)("rbfopt")
    with patch.dict(sys.modules, {"rbfopt": mock_rbfopt}):
        exec(compile(source, "grid_rbfopt.py", "exec"), ns)
    return ns


def test_make_obj_funct():
    """Factory function returns a callable bound to the given grid."""
    ns = _exec_grid_rbfopt()
    make_obj = ns["make_obj_funct"]
    grid = {(0, 0): 0.1, (1, 1): 0.9}
    fn = make_obj(grid)
    assert fn([0.0, 0.0]) == 0.1
    assert fn([1.4, 0.6]) == 0.9  # rounds to (1, 1)
    assert fn([99.0, 99.0]) == ns["PENALTY"]  # out of grid


def test_grid_bounds():
    ns = _exec_grid_rbfopt()
    grid = {(0, 0): 0.0, (5, 10): 1.0, (3, 7): 0.5}
    lb, ub = ns["grid_bounds"](grid)
    assert list(lb) == [0, 0]
    assert list(ub) == [5, 10]


def test_grid_rbfopt_main_smoke():
    ns = _exec_grid_rbfopt()
    fake_grid = {(0, 0): 0.0, (1, 1): 1.0}
    optimize_counter = {"count": 0}

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
            self.init_node_pos = init_node_pos
            self.init_node_val = init_node_val
            self.do_init_strategy = do_init_strategy

        def optimize(self):
            optimize_counter["count"] += 1
            return 0.0, [0.0, 0.0], 1, 2, 0

    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        data_dir = tmp_path / "qhdopt"
        data_dir.mkdir()
        (data_dir / "ackley.csv").write_text("x,y,z_norm\n0,0,0.0\n")

        coin_bin = tmp_path / "coin_bin"
        coin_bin.mkdir()
        (coin_bin / "bonmin").write_text("")
        (coin_bin / "ipopt").write_text("")

        log_dir = tmp_path / "logs"

        ns["DATA_DIR"] = data_dir
        ns["LOG_DIR"] = log_dir
        ns["load_grid"] = lambda _filename: fake_grid
        ns["rbfopt"] = SimpleNamespace(
            RbfoptUserBlackBox=FakeBlackBox,
            RbfoptSettings=FakeSettings,
            RbfoptAlgorithm=FakeAlgorithm,
        )

        with patch.dict(ns["os"].environ, {"COIN_BIN": str(coin_bin)}):
            ns["main"]()

        log_files = sorted(log_dir.glob("*.log"))
        assert len(log_files) == 25
        assert optimize_counter["count"] == 25
        assert log_files[0].name == "run_0001__ackley__E10__R1.log"
        assert "Optimization completed." in log_files[0].read_text()


# ------------------------------------------------------------------
# grid_dsda: multi-start search
# ------------------------------------------------------------------

def test_run_dsda_multi_start():
    from grid_dsda import run_dsda_from_best_starting_points
    csv_path = str(ROOT / "qhdopt" / "ackley.csv")
    result = run_dsda_from_best_starting_points(
        csv_path=csv_path,
        starting_points=[(14, 14), (0, 0)],
        diagonal=True,
        target_value=0.0,
        verbose=False,
    )
    assert result["best_value"] == 0.0
    assert result["best_point"] == (15, 15)
    assert result["wall_time_s"] >= 0.0
    total_evals = result["total_point_evaluations_including_initial_ranking"]
    assert len(result["incumbent_trajectory"]) == total_evals
    assert len(result["objective_wall_times"]) == total_evals
    # Should stop after 1 run since (14,14) leads directly to 0.0
    assert len(result["runs"]) == 1


def test_backward_compatible_aliases():
    from grid_dsda import (
        dsda_from_csv,
        ldsda_from_csv,
        run_dsda_from_best_starting_points,
        run_ldsda_from_best_starting_points,
    )

    assert ldsda_from_csv is dsda_from_csv
    assert run_ldsda_from_best_starting_points is run_dsda_from_best_starting_points
