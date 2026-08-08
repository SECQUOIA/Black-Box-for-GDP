"""Tests for benchmark analysis helpers."""

import math

import matplotlib
import pandas as pd
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
            "csv_name": "alpha.csv",
            "method": "BAM",
            "seed": 0,
            "n_starts": 2,
            "max_evals": 3,
            "best_value": 0.0,
            "best_point": [0, 0],
            "total_evals": 3,
            "wall_time_s": 0.015,
            "found_optimum": True,
            "incumbent_trajectory": [2.0, 0.0, 0.0],
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
        {
            "csv_name": "beta.csv",
            "method": "BAM",
            "seed": 0,
            "n_starts": 2,
            "max_evals": 3,
            "best_value": 1.0,
            "best_point": [0, 0],
            "total_evals": 3,
            "wall_time_s": 0.025,
            "found_optimum": True,
            "incumbent_trajectory": [4.0, 2.0, 1.0],
        },
    ]
    for record in records:
        record.update(
            {
                "initial_evals": record["n_starts"],
                "adaptive_evals": record["total_evals"] - record["n_starts"],
                "unique_evals": record["total_evals"],
                "solver_evalcount": None,
                "solver_iterations": None,
                "solver_status": None,
                "solver_message": None,
            }
        )
    save_results_csv(records, path)


def test_first_eval_within_tolerance_uses_one_based_eval_count():
    assert (
        benchmark_analysis.first_eval_within_tolerance([2.0, 0.001], 0.0, 1e-3)
        == 2
    )
    assert pytest.approx(
        benchmark_analysis.tolerance_window(target_value=10.0, tolerance=1e-3)
    ) == 0.01


def test_runs_to_target_probability_handles_tts99_edge_cases():
    assert benchmark_analysis.runs_to_target_probability(0.0) == float("inf")
    assert benchmark_analysis.runs_to_target_probability(1.0) == 1
    assert benchmark_analysis.runs_to_target_probability(0.5) == 7


def test_tts99_summary_uses_hit_rate_and_median_wall_time_across_seeds():
    results = pd.DataFrame(
        [
            {
                "csv_name": grid_name,
                "method": "DSDA",
                "seed": seed,
                "n_starts": 2,
                "max_evals": 10,
                "found_optimum": found_optimum,
                "wall_time_s": wall_time_s,
            }
            for grid_name, outcomes in {
                "never.csv": ((False, 1.0), (False, 3.0)),
                "always.csv": ((True, 1.0), (True, 3.0)),
                "sometimes.csv": ((True, 2.0), (False, 4.0)),
            }.items()
            for seed, (found_optimum, wall_time_s) in enumerate(outcomes)
        ]
    )

    summary = benchmark_analysis.tts99_summary(results).set_index("csv_name")

    assert summary.loc["never.csv", "hit_rate"] == 0.0
    assert summary.loc["never.csv", "runs_99"] == float("inf")
    assert summary.loc["never.csv", "tts99_s"] == float("inf")
    assert summary.loc["always.csv", "hit_rate"] == 1.0
    assert summary.loc["always.csv", "runs_99"] == 1
    assert summary.loc["always.csv", "median_wall_time_s"] == 2.0
    assert summary.loc["always.csv", "tts99_s"] == 2.0
    assert summary.loc["sometimes.csv", "hit_rate"] == 0.5
    assert summary.loc["sometimes.csv", "runs_99"] == 7
    assert summary.loc["sometimes.csv", "median_wall_time_s"] == 3.0
    assert summary.loc["sometimes.csv", "tts99_s"] == 21.0


def test_tts99_plot_includes_failures_in_median_and_labels_run_count():
    results = pd.DataFrame(
        [
            {
                "csv_name": grid_name,
                "method": method,
                "seed": seed,
                "n_starts": 2,
                "max_evals": 10,
                "found_optimum": found_optimum,
                "wall_time_s": 1.0,
            }
            for method in ("DSDA", "RBFOpt", "BAM")
            for grid_name, outcomes in {
                "solved.csv": (True, True),
                "failed_a.csv": (False, False),
                "failed_b.csv": (False, False),
            }.items()
            for seed, found_optimum in enumerate(outcomes)
        ]
    )

    figure = benchmark_analysis.plot_tts99_comparison(results)
    axis = figure.axes[0]
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    median_labels = [
        text for text in axis.texts if text.get_text() == "median=∞"
    ]
    left_median_label = min(
        median_labels,
        key=lambda text: text.xy[0],
    )
    axes_bounds = axis.get_window_extent(renderer)
    label_bounds = left_median_label.get_window_extent(renderer)

    assert label_bounds.x0 >= axes_bounds.x0
    assert label_bounds.x1 <= axes_bounds.x1
    assert [tick.get_text() for tick in axis.get_xticklabels()] == [
        "DSDA\nn=2",
        "RBFOpt\nn=2",
        "BAM\nn=2",
    ]
    assert len(axis.lines) == 0


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


def test_attach_grid_metadata_rejects_missing_grids(tmp_path):
    grids_dir = tmp_path / "grids"
    grids_dir.mkdir()
    _write_grid(grids_dir / "alpha.csv")
    results_path = tmp_path / "benchmark.csv"
    _write_results(results_path)
    raw_results = benchmark_analysis.load_benchmark_results(results_path)

    with pytest.raises(ValueError, match=r"Missing grid metadata.*beta\.csv"):
        benchmark_analysis.attach_grid_metadata(raw_results, grids_dir)


def test_performance_ratios_keep_problems_unsolved_by_every_method():
    rows = []
    for method in benchmark_analysis.METHOD_ORDER:
        rows.extend(
            [
                {
                    "csv_name": "solved.csv",
                    "seed": 0,
                    "method": method,
                    "max_evals": 3,
                    "target_value": 0.0,
                    "found_optimum": True,
                    "total_evals": 2,
                    "incumbent_trajectory": [1.0, 0.0],
                },
                {
                    "csv_name": "unsolved.csv",
                    "seed": 0,
                    "method": method,
                    "max_evals": 3,
                    "target_value": 0.0,
                    "found_optimum": False,
                    "total_evals": 3,
                    "incumbent_trajectory": [3.0, 2.0, 1.0],
                },
            ]
        )

    ratios = benchmark_analysis.performance_ratio_table(
        pd.DataFrame(rows),
        tolerance=1e-5,
        budget=3,
    )

    assert len(ratios) == 2
    assert ratios.loc[("unsolved.csv", 0)].isna().all()


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
    assert summary.loc["BAM", 3] == 1.0
    assert wilcoxon.loc[0, "max_evals"] == 3
    assert wilcoxon.loc[0, "n_pairs"] == 2
    assert "holm_p_value" in wilcoxon.columns


def test_three_method_comparisons_include_bam(tmp_path):
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

    comparisons = benchmark_analysis.pairwise_wilcoxon_by_budget(results)
    friedman = benchmark_analysis.friedman_by_budget(results)
    nemenyi = benchmark_analysis.nemenyi_by_budget(results)

    assert set(zip(comparisons["method_a"], comparisons["method_b"], strict=True)) == {
        ("DSDA", "RBFOpt"),
        ("DSDA", "BAM"),
        ("RBFOpt", "BAM"),
    }
    assert friedman.loc[0, "methods"] == ["DSDA", "RBFOpt", "BAM"]
    assert len(nemenyi) == 3
    assert set(nemenyi["method_a"]).union(nemenyi["method_b"]) == {
        "DSDA",
        "RBFOpt",
        "BAM",
    }

    winner_input = results.copy()
    alpha = winner_input["csv_name"] == "alpha.csv"
    winner_input.loc[alpha & (winner_input["method"] == "DSDA"), "best_value"] = 0.2
    winner_input.loc[alpha & (winner_input["method"] == "RBFOpt"), "best_value"] = 0.1
    labels, margins = benchmark_analysis.winner_heatmap_frames(winner_input)
    assert labels.loc["alpha.csv", 3] == "BAM"
    assert margins.loc["alpha.csv", 3] == pytest.approx(0.1)

    incomplete = winner_input[
        ~(
            (winner_input["csv_name"] == "alpha.csv")
            & (winner_input["method"] == "RBFOpt")
        )
    ]
    incomplete_labels, incomplete_margins = (
        benchmark_analysis.winner_heatmap_frames(incomplete)
    )
    assert incomplete_labels.loc["alpha.csv", 3] == "incomplete"
    assert pd.isna(incomplete_margins.loc["alpha.csv", 3])

    wall_time_figure = benchmark_analysis.plot_wall_time_scatter(results)
    assert len(wall_time_figure.axes) == 2

    performance_figure = benchmark_analysis.plot_performance_profiles(results)
    assert {
        text.get_text() for text in performance_figure.axes[0].get_legend().get_texts()
    } == {"DSDA", "RBFOpt", "BAM"}

    data_profile_figure = benchmark_analysis.plot_data_profiles(results)
    assert all(axis.get_legend()._loc == 2 for axis in data_profile_figure.axes)

    convergence_figure = benchmark_analysis.plot_convergence_curves(
        results,
        grid_name="alpha.csv",
        budget=3,
    )
    assert {line.get_label() for line in convergence_figure.axes[0].lines} == {
        "DSDA",
        "RBFOpt",
        "BAM",
    }


def test_trajectory_means_carry_terminal_incumbents_to_budget():
    results = pd.DataFrame(
        [
            {
                "csv_name": "alpha.csv",
                "method": "DSDA",
                "seed": 0,
                "max_evals": 3,
                "incumbent_trajectory": [5.0, 0.0],
            },
            {
                "csv_name": "alpha.csv",
                "method": "DSDA",
                "seed": 1,
                "max_evals": 3,
                "incumbent_trajectory": [5.0, 4.0, 3.0],
            },
        ]
    )

    means = benchmark_analysis.trajectory_mean_frame(
        results,
        grid_name="alpha.csv",
        budget=3,
    )

    assert means["incumbent"].tolist() == [5.0, 2.0, 1.5]


def test_trajectory_helpers_skip_leading_nonfinite_incumbents():
    trajectory = [None, math.inf, 5.0, 0.0]

    assert benchmark_analysis.first_eval_within_tolerance(trajectory, 0.0, 1e-5) == 4

    results = pd.DataFrame(
        [
            {
                "csv_name": "alpha.csv",
                "method": "BAM",
                "seed": 0,
                "max_evals": 4,
                "incumbent_trajectory": trajectory,
            }
        ]
    )
    means = benchmark_analysis.trajectory_mean_frame(
        results,
        grid_name="alpha.csv",
        budget=4,
    )

    assert means["incumbent"].isna().tolist() == [True, True, False, False]
    assert means["incumbent"].iloc[2:].tolist() == [5.0, 0.0]


def test_holm_and_friedman_report_correction_threshold(tmp_path):
    raw_tests = pd.DataFrame(
        {
            "max_evals": [3, 5],
            "p_value": [0.04, 0.20],
        }
    )
    corrected = benchmark_analysis.holm_bonferroni(raw_tests, alpha=0.10)

    assert set(corrected["holm_alpha"]) == {0.10}
    assert corrected["holm_reject"].tolist() == [True, False]
    assert "holm_reject_0.05" not in corrected

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
    second_budget = results.copy()
    second_budget["max_evals"] = 5
    multi_budget = pd.concat([results, second_budget], ignore_index=True)

    friedman = benchmark_analysis.friedman_by_budget(multi_budget)

    assert len(friedman) == 2
    assert {"holm_p_value", "holm_alpha", "holm_reject"}.issubset(friedman)
    assert (friedman["holm_p_value"] >= friedman["p_value"]).all()


def test_nonsignificant_rank_groups_are_maximal():
    nemenyi = pd.DataFrame(
        [
            {"method_a": "A", "method_b": "B", "significant": False},
            {"method_a": "A", "method_b": "C", "significant": True},
            {"method_a": "B", "method_b": "C", "significant": False},
        ]
    )

    groups = benchmark_analysis.nonsignificant_rank_groups(
        nemenyi,
        ["A", "B", "C"],
    )

    assert groups == [("A", "B"), ("B", "C")]


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
        "tts99_comparison.png",
        "winner_heatmap.png",
        "wall_time_scatter.png",
        "critical_difference_diagrams.png",
    }
    assert {path.name for path in outputs["table_paths"]} == {
        "solved_fraction_summary.csv",
        "tts99_summary.csv",
        "wilcoxon_by_budget.csv",
        "friedman_by_budget.csv",
        "nemenyi_by_budget.csv",
    }
    for path in [*outputs["figure_paths"], *outputs["table_paths"]]:
        assert path.exists()
