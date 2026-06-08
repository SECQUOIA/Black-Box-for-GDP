"""Tests for the distillation column RBFOpt runner."""

import os
from types import SimpleNamespace

from case_studies.column_rbfopt import resolve_solver_paths, run_column_rbfopt


def test_resolve_column_solver_paths_from_solver_dir(tmp_path, monkeypatch):
    bonmin = tmp_path / "bonmin"
    ipopt = tmp_path / "ipopt"
    bonmin.write_text("")
    ipopt.write_text("")
    monkeypatch.setenv("PATH", "/usr/bin")

    minlp_solver_path, nlp_solver_path = resolve_solver_paths(solver_dir=tmp_path)

    assert minlp_solver_path == str(bonmin)
    assert nlp_solver_path == str(ipopt)
    assert str(tmp_path) in os.environ["PATH"].split(os.pathsep)


def test_run_column_rbfopt_uses_lhc_points_as_explicit_initial_nodes():
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

    result = run_column_rbfopt(
        seed=1,
        n_starts=3,
        max_evaluations=16,
        rbfopt_module=fake_rbfopt,
    )

    assert result["starting_points"] == [(14, 4), (12, 1), (9, 8)]
    assert captured["init_node_pos"].tolist() == [
        [14.0, 4.0],
        [12.0, 1.0],
        [9.0, 8.0],
    ]
    assert captured["init_node_val"] is None
    assert captured["do_init_strategy"] is False
    assert result["best_point"] == [14, 4]
    assert result["best_value"] == 19740.33791404187
    assert result["tracked_evals"] == 3
    assert result["result_record"]["csv_name"] == "compl_enum_column_17_baron.csv"
    assert result["result_record"]["method"] == "RBFOpt"
    assert result["result_record"]["seed"] == 1
    assert result["result_record"]["n_starts"] == 3
