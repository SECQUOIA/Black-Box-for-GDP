"""Tests for BAM case-study runners."""

from types import SimpleNamespace

import numpy as np

from case_studies.column_bam import run_column_bam
from case_studies.cstr_bam import run_cstr_bam
from case_studies.small_batch_bam import run_small_batch_bam


def _fake_bam(captured, candidate):
    def set_license_file(path):
        captured["license_file"] = path

    def minimize(
        objective,
        x0,
        bounds=None,
        integrality=None,
        options=None,
    ):
        captured["x0"] = x0
        captured["bounds"] = bounds
        captured["integrality"] = integrality
        captured["options"] = options
        captured["x_evaluated"] = np.asarray(options["x_evaluated"], dtype=float)
        captured["f_evaluated"] = np.asarray(options["f_evaluated"], dtype=float)

        candidate_point = np.asarray(candidate, dtype=float)
        candidate_value = objective(candidate_point)
        best_index = int(np.argmin(captured["f_evaluated"]))
        best_value = float(captured["f_evaluated"][best_index])
        best_point = captured["x_evaluated"][best_index]
        if candidate_value < best_value:
            best_value = candidate_value
            best_point = candidate_point

        return SimpleNamespace(
            x=best_point,
            fun=best_value,
            nfev=int(options["max_evals"]),
            nit=2,
            status=35,
            message="fake BAM budget reached",
        )

    return SimpleNamespace(set_license_file=set_license_file, minimize=minimize)


def test_run_column_bam_uses_shared_lhc_as_warm_start(tmp_path):
    captured = {}

    result = run_column_bam(
        seed=1,
        n_starts=3,
        max_evaluations=16,
        bam_license_file=tmp_path / "bamlice.txt",
        bam_module=_fake_bam(captured, candidate=(15, 9)),
    )

    assert result["starting_points"] == [(14, 4), (12, 1), (9, 8)]
    assert captured["license_file"] == str(tmp_path / "bamlice.txt")
    assert captured["x0"] is None
    assert captured["bounds"] == [(7.0, 15.0), (1.0, 9.0)]
    assert captured["integrality"] == [1, 1]
    assert captured["options"]["max_evals"] == 13
    assert captured["x_evaluated"].tolist() == [
        [14.0, 4.0],
        [12.0, 1.0],
        [9.0, 8.0],
    ]
    assert result["tracked_evals"] == 4
    assert result["initial_evals"] == 3
    assert result["adaptive_evals"] == 1
    assert result["result_record"]["method"] == "BAM"
    assert result["result_record"]["csv_name"] == "compl_enum_column_17_baron.csv"
    assert result["result_record"]["solver_evalcount"] == 13
    assert result["result_record"]["solver_status"] == 35


def test_run_cstr_bam_uses_case_grid_bounds_and_metadata():
    captured = {}

    result = run_cstr_bam(
        grid_size=7,
        seed=0,
        n_starts=3,
        max_evaluations=10,
        bam_module=_fake_bam(captured, candidate=(1, 1)),
    )

    assert result["starting_points"] == [(2, 2), (7, 7), (3, 3)]
    assert captured["x0"] is None
    assert captured["bounds"] == [(1.0, 7.0), (1.0, 7.0)]
    assert captured["integrality"] == [1, 1]
    assert captured["options"]["max_evals"] == 7
    assert result["grid_size"] == 7
    assert result["result_record"]["csv_name"] == "compl_enum_cstr_7_baron_hull.csv"
    assert result["result_record"]["initial_evals"] == 3
    assert result["result_record"]["adaptive_evals"] == 1
    assert result["result_record"]["unique_evals"] == 4


def test_run_small_batch_bam_uses_three_integer_variables():
    captured = {}

    result = run_small_batch_bam(
        seed=0,
        n_starts=3,
        max_evaluations=10,
        bam_module=_fake_bam(captured, candidate=(3, 3, 3)),
    )

    assert result["starting_points"] == [(2, 3, 2), (3, 2, 2), (2, 2, 1)]
    assert captured["x0"] is None
    assert captured["bounds"] == [(2.0, 3.0), (2.0, 3.0), (1.0, 3.0)]
    assert captured["integrality"] == [1, 1, 1]
    assert captured["options"]["max_evals"] == 7
    assert captured["x_evaluated"].tolist() == [
        [2.0, 3.0, 2.0],
        [3.0, 2.0, 2.0],
        [2.0, 2.0, 1.0],
    ]
    assert result["case_name"] == "small_batch"
    assert result["result_record"]["method"] == "BAM"
    assert result["result_record"]["solver_message"] == "fake BAM budget reached"
