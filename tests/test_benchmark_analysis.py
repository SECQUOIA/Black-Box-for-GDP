"""Tests for benchmark analysis helpers."""

import matplotlib
import pytest

matplotlib.use("Agg")

import benchmark_analysis
from instrumentation import save_results_csv


def _write_grid(path, offset=0.0):
    path.write_text(
        "x,y,z_norm\n"
        f"0,0,{0.0 + offset}\n"
        f"0,1,{1.0 + offset}\n"
        f"1,0,{2.0 + offset}\n"
        f"1,1,{3.0 + offset}\n"
    )


def _write_results(path):
    records = [
        {
            "csv_name": "alpha.csv",
            "method": "DSDA",
            "seed": 0,
            "n_starts": 2,
            "max_evals": 3,
            "best_value": 0.0,
            "best_point": [0, 0],
            "total_evals": 2,
            "wall_time_s": 0.01,
            "found_optimum": True,
            "incumbent_trajectory": [2.0, 0.0],
        },
        {
            "csv_name": "alpha.csv",
            "method": "RBFOpt",
            "seed": 0,
            "n_starts": 2,
            "max_evals": 3,
            "best_value": 0.0,
            "best_point": [0, 0],
            "total_evals": 3,
            "wall_time_s": 0.02,
            "found_optimum": True,
            "incumbent_trajectory": [2.0, 1.0, 0.0],
        },
        {
            "csv_name": "beta.csv",
            "method": "DSDA",
            "seed": 0,
            "n_starts": 2,
            "max_evals": 3,
            "best_value": 2.0,
            "best_point": [1, 0],
            "total_evals": 3,
            "wall_time_s": 0.03,
            "found_optimum": False,
            "incumbent_trajectory": [4.0, 3.0, 2.0],
        },
        {
            "csv_name": "beta.csv",
            "method": "RBFOpt",
            "seed": 0,
            "n_starts": 2,
            "max_evals": 3,
            "best_value": 1.0,
            "best_point": [0, 0],
            "total_evals": 2,
            "wall_time_s": 0.04,
            "found_optimum": True,
            "incumbent_trajectory": [3.0, 1.0],
        },
    ]
    save_results_csv(records, path)


def test_first_eval_within_tolerance_uses_one_based_eval_count():
    assert (
        benchmark_analysis.first_eval_within_tolerance([2.0, 0.001], 0.0, 1e-3)
        == 2
    )
    assert pytest.approx(
        benchmark_analysis.tolerance_window(target_value=10.0, tolerance=1e-3)
    ) == 0.01


def test_load_results_and_attach_grid_metadata(tmp_path):
    grids_dir = tmp_path / "grids"
    grids_dir.mkdir()
    _write_grid(grids_dir / "alpha.csv")
    _write_grid(grids_dir / "beta.csv", offset=1.0)
    results_path = tmp_path / "benchmark.csv"
    _write_results(results_path)

    raw_results = benchmark_analysis.load_benchmark_results(results_path)
    results = benchmark_analysis.attach_grid_metadata(raw_results, grids_dir)

    assert results["best_point"].iloc[0] == [0, 0]
    assert results["incumbent_trajectory"].iloc[0] == [2.0, 0.0]
    assert set(results["dimension"]) == {2}
    alpha_target = results.loc[
        results["csv_name"] == "alpha.csv",
        "target_value",
    ].iloc[0]
    beta_target = results.loc[
        results["csv_name"] == "beta.csv",
        "target_value",
    ].iloc[0]

    assert alpha_target == 0
    assert beta_target == 1


def test_solve_summary_and_wilcoxon_tables(tmp_path):
    grids_dir = tmp_path / "grids"
    grids_dir.mkdir()
    _write_grid(grids_dir / "alpha.csv")
    _write_grid(grids_dir / "beta.csv", offset=1.0)
    results_path = tmp_path / "benchmark.csv"
    _write_results(results_path)
    results, _ = benchmark_analysis.load_analysis_dataset(
        results_path,
        grids_dir=grids_dir,
    )

    annotated = benchmark_analysis.annotate_solve_status(results, tolerance=1e-5)
    summary = benchmark_analysis.solved_fraction_summary(results, tolerance=1e-5)
    wilcoxon = benchmark_analysis.wilcoxon_by_budget(results)

    dsda_beta = annotated[
        (annotated["csv_name"] == "beta.csv") & (annotated["method"] == "DSDA")
    ].iloc[0]
    assert not dsda_beta["solved"]
    assert summary.loc["DSDA", 3] == 0.5
    assert summary.loc["RBFOpt", 3] == 1.0
    assert wilcoxon.loc[0, "max_evals"] == 3
    assert wilcoxon.loc[0, "n_pairs"] == 2
    assert "holm_p_value" in wilcoxon.columns


def test_create_analysis_outputs_writes_figures_and_tables(tmp_path):
    grids_dir = tmp_path / "grids"
    grids_dir.mkdir()
    _write_grid(grids_dir / "alpha.csv")
    _write_grid(grids_dir / "beta.csv", offset=1.0)
    results_path = tmp_path / "benchmark.csv"
    figure_dir = tmp_path / "figures"
    _write_results(results_path)

    outputs = benchmark_analysis.create_analysis_outputs(
        results_csv=results_path,
        grids_dir=grids_dir,
        figure_dir=figure_dir,
        data_profile_tolerances=(1e-1, 1e-3),
    )

    assert outputs["results_path"] == results_path
    assert {path.name for path in outputs["figure_paths"]} == {
        "performance_profiles.png",
        "data_profiles.png",
        "best_value_boxplots.png",
        "convergence_curves.png",
        "winner_heatmap.png",
        "wall_time_scatter.png",
    }
    assert {path.name for path in outputs["table_paths"]} == {
        "solved_fraction_summary.csv",
        "wilcoxon_by_budget.csv",
    }
    for path in [*outputs["figure_paths"], *outputs["table_paths"]]:
        assert path.exists()
