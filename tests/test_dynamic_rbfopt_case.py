"""Tests for the dynamic case-study RBFOpt runner."""

import os
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

import case_studies.dynamic_rbfopt as dynamic_rbfopt
from case_studies.common import generate_lhc_starting_points
from case_studies.dynamic_case import PENALTY, dynamic_objective
from case_studies.dynamic_rbfopt import (
    resolve_solver_paths,
    run_dynamic_rbfopt,
)


def test_dynamic_lhc_starting_points_seed_zero():
    points = generate_lhc_starting_points(
        n_dims=2,
        n_points=3,
        lb=np.array([1, 2]),
        ub=np.array([9, 9]),
        seed=0,
    )

    assert points == [(2, 4), (9, 9), (4, 5)]


def test_dynamic_objective_penalizes_infeasible_points():
    assert dynamic_objective((1, 4)) == -212.00878719112268
    assert dynamic_objective((8, 4)) == PENALTY


def test_resolve_solver_paths_from_solver_dir(tmp_path, monkeypatch):
    bonmin = tmp_path / "bonmin"
    ipopt = tmp_path / "ipopt"
    bonmin.write_text("")
    ipopt.write_text("")
    monkeypatch.setenv("PATH", "/usr/bin")

    minlp_solver_path, nlp_solver_path = resolve_solver_paths(solver_dir=tmp_path)

    assert minlp_solver_path == str(bonmin)
    assert nlp_solver_path == str(ipopt)
    assert str(tmp_path) in os.environ["PATH"].split(os.pathsep)


@pytest.mark.parametrize("verbose", [False, True])
def test_run_dynamic_rbfopt_uses_lhc_points_as_explicit_initial_nodes(
    monkeypatch,
    verbose,
):
    captured = {}
    ticks = iter([10.0, 12.5])
    timer_calls = []

    def fake_perf_counter():
        timer_calls.append(True)
        return next(ticks)

    monkeypatch.setattr(dynamic_rbfopt.time, "perf_counter", fake_perf_counter)

    @contextmanager
    def fake_suppress_solver_output():
        captured["suppression_requested"] = True
        captured["suppression_active"] = True
        try:
            yield
        finally:
            captured["suppression_active"] = False

    monkeypatch.setattr(
        dynamic_rbfopt,
        "suppress_solver_output",
        fake_suppress_solver_output,
    )

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
            captured["timer_calls_at_algorithm_init"] = len(timer_calls)
            captured["init_node_pos"] = init_node_pos
            captured["init_node_val"] = init_node_val
            captured["do_init_strategy"] = do_init_strategy

        def optimize(self):
            captured["suppression_active_during_optimize"] = captured.get(
                "suppression_active", False
            )
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

    result = run_dynamic_rbfopt(
        seed=0,
        n_starts=3,
        max_evaluations=12,
        rbfopt_module=fake_rbfopt,
        verbose=verbose,
    )

    assert result["starting_points"] == [(2, 4), (9, 9), (4, 5)]
    assert captured["init_node_pos"].tolist() == [[2.0, 4.0], [9.0, 9.0], [4.0, 5.0]]
    assert captured["settings"]["rand_seed"] == 0
    assert captured["init_node_val"] is None
    assert captured["do_init_strategy"] is False
    assert captured["timer_calls_at_algorithm_init"] == 1
    assert result["tracked_evals"] == 3
    assert result["wall_time_s"] == 2.5
    assert result["result_record"]["wall_time_s"] == 2.5
    assert result["result_record"]["method"] == "RBFOpt"
    assert result["result_record"]["seed"] == 0
    assert result["result_record"]["n_starts"] == 3
    assert captured.get("suppression_requested", False) is not verbose
    assert captured["suppression_active_during_optimize"] is not verbose
