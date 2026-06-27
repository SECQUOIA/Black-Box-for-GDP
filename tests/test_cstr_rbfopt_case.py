"""Tests for the CSTR RBFOpt runner."""

import os
from types import SimpleNamespace

from case_studies.cstr_rbfopt import resolve_solver_paths, run_cstr_rbfopt


def test_resolve_cstr_solver_paths_from_solver_dir(tmp_path, monkeypatch):
    bonmin = tmp_path / "bonmin"
    ipopt = tmp_path / "ipopt"
    bonmin.write_text("")
    ipopt.write_text("")
    monkeypatch.setenv("PATH", "/usr/bin")

    minlp_solver_path, nlp_solver_path = resolve_solver_paths(solver_dir=tmp_path)

    assert minlp_solver_path == str(bonmin)
    assert nlp_solver_path == str(ipopt)
    assert str(tmp_path) in os.environ["PATH"].split(os.pathsep)


def test_run_cstr_rbfopt_uses_lhc_points_as_explicit_initial_nodes():
    captured = {}

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

    fake_rbfopt = SimpleNamespace(
        RbfoptUserBlackBox=FakeBlackBox,
        RbfoptSettings=FakeSettings,
        RbfoptAlgorithm=FakeAlgorithm,
    )

    result = run_cstr_rbfopt(
        grid_size=7,
        seed=0,
        n_starts=3,
        max_evaluations=10,
        rbfopt_module=fake_rbfopt,
    )

    assert result["starting_points"] == [(2, 2), (7, 7), (3, 3)]
    assert captured["init_node_pos"].tolist() == [
        [2.0, 2.0],
        [7.0, 7.0],
        [3.0, 3.0],
    ]
    assert captured["settings"]["rand_seed"] == 0
    assert captured["init_node_val"] is None
    assert captured["do_init_strategy"] is False
    assert result["best_point"] == [7, 7]
    assert result["best_value"] == 2.965911187241821
    assert result["tracked_evals"] == 3
    assert result["result_record"]["csv_name"] == "compl_enum_cstr_7_baron_hull.csv"
    assert result["result_record"]["method"] == "RBFOpt"
    assert result["result_record"]["seed"] == 0
    assert result["result_record"]["n_starts"] == 3
