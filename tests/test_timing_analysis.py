"""Checks for completion-time semantics, failure denominators and archived inputs."""

import hashlib
import json
import math
import zipfile

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

import timing_analysis as timing


def _runs():
    rows = []
    for problem, outcomes in {
        "alpha.csv": [(0.0, 4.0), (0.0, 2.0), (1.0, 0.1)],
        "failed.csv": [(1.0, 1.0), (1.0, 3.0), (1.0, 2.0)],
    }.items():
        for method, (value, seconds) in zip(("DSDA", "RBFOpt", "BAM"), outcomes):
            rows.append(
                {
                    "csv_name": problem,
                    "method": method,
                    "seed": 0,
                    "n_starts": 1,
                    "max_evals": 3,
                    "best_value": value,
                    "target_value": 0.0,
                    "wall_time_s": seconds,
                    "total_evals": 3,
                    "solver_iterations": 1 if method == "DSDA" else 2,
                    "found_optimum": value == 0,
                    "incumbent_trajectory": [1, value, value],
                    "best_point": [0, 0],
                }
            )
    return pd.DataFrame(rows)


def test_profiles_use_full_runtime_and_keep_every_failed_instance():
    data = timing.prepare_timing_data(_runs())
    alpha = data[data["csv_name"] == "alpha.csv"].set_index("method")
    assert alpha.loc["DSDA", "successful_run_time_s"] == 4.0
    assert alpha.loc["DSDA", "time_ratio"] == 2.0
    assert alpha.loc["RBFOpt", "time_ratio"] == 1.0
    assert math.isinf(alpha.loc["BAM", "time_ratio"])
    assert np.isinf(data.loc[data["csv_name"] == "failed.csv", "time_ratio"]).all()
    # An early incumbent hit does not scale the recorded run time by eval count.
    assert alpha.loc["DSDA", "successful_run_time_s"] != 4 * 2 / 3
    for relative in (False, True):
        figure = timing.plot_time_profiles(data, "grid", relative=relative)
        axis = figure.axes[0]
        assert axis.get_xscale() == "log"
        assert axis.get_xlim()[0] > 0
        assert axis.get_ylim()[0] == 0
        curves = {line.get_label(): line for line in axis.lines}
        assert curves["DSDA"].get_ydata()[-1] == 0.5
        assert curves["RBFOpt"].get_ydata()[-1] == 0.5
        assert curves["BAM"].get_ydata()[-1] == 0.0
        for line in curves.values():
            assert np.all(np.diff(line.get_ydata()) >= 0)
        timing_plot_close(figure)


def timing_plot_close(figure):
    import matplotlib.pyplot as plt

    plt.close(figure)


def test_profiles_keep_budgets_and_initial_design_counts_separate():
    original = _runs()
    other_budget = original.assign(max_evals=5, wall_time_s=original.wall_time_s * 10)
    other_starts = original.assign(n_starts=2, wall_time_s=original.wall_time_s * 20)
    data = timing.prepare_timing_data(pd.concat([original, other_budget, other_starts]))
    assert len(timing._panels(data, "grid")) == 3
    assert data.loc[
        (data["csv_name"] == "alpha.csv") & (data["method"] == "DSDA"), "time_ratio"
    ].tolist() == [2.0, 2.0, 2.0]


@pytest.mark.parametrize("runtime", [0, -1, math.nan, math.inf])
def test_invalid_runtimes_are_rejected_instead_of_shifted_on_log_axis(runtime):
    runs = _runs()
    runs.loc[0, "wall_time_s"] = runtime
    with pytest.raises(ValueError, match="strictly positive"):
        timing.prepare_timing_data(runs)


def test_missing_methods_and_duplicates_are_rejected():
    with pytest.raises(ValueError, match="same methods"):
        timing.prepare_timing_data(_runs().iloc[:-1])
    with pytest.raises(ValueError, match="Duplicate"):
        timing.prepare_timing_data(pd.concat([_runs(), _runs().iloc[:1]]))


def test_negative_target_uses_absolute_scale_and_detects_invalid_optimum():
    runs = _runs().assign(target_value=-100.0, best_value=-99.9995)
    data = timing.prepare_timing_data(runs, tolerance=1e-5)
    assert data["solved"].all()
    runs.loc[0, "best_value"] = -100.1
    with pytest.raises(ValueError, match="below the recorded optimum"):
        timing.prepare_timing_data(runs)


def test_nonfinite_objectives_remain_unsolved():
    runs = _runs()
    runs.loc[0, "best_value"] = math.inf
    runs.loc[1, "best_value"] = math.nan
    data = timing.prepare_timing_data(runs)
    assert not data["solved"].any()
    assert np.isinf(data["time_ratio"]).all()
    figure = timing.plot_time_profiles(data, "grid")
    assert all(np.all(line.get_ydata() == 0) for line in figure.axes[0].lines)
    timing_plot_close(figure)


def test_work_summary_includes_failed_runs_and_missing_iteration_reports():
    runs = _runs()
    runs.loc[runs["method"] == "DSDA", "solver_iterations"] = math.nan
    data = timing.prepare_timing_data(runs)
    summary = timing.timing_summary(data, "grid").set_index("method")
    assert summary.loc["DSDA", "median_wall_time_s"] == 2.5
    assert summary.loc["DSDA", "solved_fraction"] == 0.5
    assert summary.loc["DSDA", "solver_iteration_runs"] == 0
    assert math.isnan(summary.loc["DSDA", "median_solver_iterations"])
    figure = timing.plot_time_work_tradeoff(summary.reset_index(), "grid")
    assert len(figure.axes[0].collections) == 3
    assert len(figure.axes[1].collections) == 2
    assert "method-specific and not directly comparable" in " ".join(
        text.get_text() for text in figure.texts
    )
    timing_plot_close(figure)


def test_case_profiles_do_not_pool_cases_or_budgets():
    runs = _runs()
    runs["case_name"] = runs["csv_name"].map(
        {"alpha.csv": "column", "failed.csv": "dynamic"}
    )
    runs["problem_label"] = runs["case_name"].str.title()
    data = timing.prepare_timing_data(runs)
    summary = timing.timing_summary(data, "case")
    assert len(summary) == 6
    figure = timing.plot_time_profiles(data, "case")
    assert len(figure.axes) == 2
    assert all("1 paired instances" in ax.get_title() for ax in figure.axes)
    timing_plot_close(figure)


def test_zip_cli_reproduces_profiles_without_extracting_into_workspace(tmp_path):
    grids = tmp_path / "grids"
    grids.mkdir()
    for name in ("alpha.csv", "failed.csv"):
        (grids / name).write_text("x,y,z_norm\n0,0,0\n0,1,1\n")
    raw = _runs().drop(columns="target_value")
    for column in ("best_point", "incumbent_trajectory"):
        raw[column] = raw[column].apply(json.dumps)
    csv_bytes = raw.to_csv(index=False).encode()
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("original/benchmark.csv", csv_bytes)
    output = tmp_path / "analysis"
    timing.main(
        [
            "--dataset",
            "grid",
            "--archive",
            str(archive),
            "--grids-dir",
            str(grids),
            "--output-dir",
            str(output),
            "--dpi",
            "50",
        ]
    )
    assert not (tmp_path / "original").exists()
    assert {p.name for p in output.iterdir()} == {
        "time_performance_profiles.png",
        "completion_time_profiles.png",
        "time_work_tradeoff.png",
        "time_profile_runs.csv",
        "time_work_summary.csv",
        "timing_analysis.manifest.json",
    }
    manifest = json.loads((output / "timing_analysis.manifest.json").read_text())
    assert manifest["csv_sha256"] == hashlib.sha256(csv_bytes).hexdigest()
    assert manifest["n_runs"] == 6
    assert manifest["first_hit_timestamps_available"] is False
    assert set(manifest["grid_sha256"]) == {"alpha.csv", "failed.csv"}
    exported = pd.read_csv(output / "time_profile_runs.csv")
    assert np.isinf(exported.loc[~exported["solved"], "time_ratio"]).all()


def test_case_archive_checks_paired_manifest_and_serializes_provenance(tmp_path):
    from case_studies.column_case import COLUMN_CSV_NAME, KNOWN_BEST_VALUE
    from case_study_analysis import EXPECTED_RESULT_SCHEMA
    from instrumentation import save_results_csv

    runs = _runs()
    runs["seed"] = (runs["csv_name"] == "failed.csv").astype(int)
    runs["csv_name"] = COLUMN_CSV_NAME
    runs["best_value"] = KNOWN_BEST_VALUE * (1 + runs["best_value"] / 10)
    runs["incumbent_trajectory"] = runs["best_value"].apply(
        lambda value: [KNOWN_BEST_VALUE * 1.2, value, value]
    )
    runs = runs.assign(
        initial_evals=1,
        adaptive_evals=2,
        unique_evals=3,
        solver_evalcount=3,
        solver_status=0,
        solver_message="test",
    )
    csv_path = tmp_path / "process_case_studies.csv"
    save_results_csv(runs.to_dict("records"), csv_path)
    csv_bytes = csv_path.read_bytes()
    manifest = {
        "schema": EXPECTED_RESULT_SCHEMA,
        "run": {"status": "completed", "expected_rows": 6, "completed_rows": 6},
        "output": {
            "csv_bytes": len(csv_bytes),
            "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        },
    }
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("original/process_case_studies.csv", csv_bytes)
        target.writestr(
            "original/process_case_studies.manifest.json", json.dumps(manifest)
        )
    output = tmp_path / "analysis"
    timing.create_timing_outputs("case", output, archive=archive, dpi=50)
    provenance = json.loads((output / "timing_analysis.manifest.json").read_text())
    assert provenance["input_validation"]["verified"] is True
    assert (
        provenance["input_validation"]["manifest_filename"]
        == "process_case_studies.manifest.json"
    )
    assert provenance["csv_member"] == "original/process_case_studies.csv"


def test_nearby_budget_labels_remain_separate_and_readable():
    from matplotlib.text import Text

    data = timing.prepare_timing_data(_runs())
    summaries = [
        timing.timing_summary(data, "grid").assign(max_evals=budget)
        for budget in (3, 5, 10)
    ]
    figure = timing.plot_time_work_tradeoff(pd.concat(summaries), "grid")
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    for axis in figure.axes:
        boxes = [
            Text.get_window_extent(text, renderer)
            for text in axis.texts
            if text.get_text().startswith("B")
        ]
        assert len(boxes) == 9
        assert not any(
            left.overlaps(right)
            for i, left in enumerate(boxes)
            for right in boxes[i + 1 :]
        )
    timing_plot_close(figure)
