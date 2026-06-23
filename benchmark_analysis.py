"""Analysis and plotting helpers for benchmark.py result CSVs."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


RESULTS_DIR = Path("results")
GRIDS_DIR = Path("benchmark_grids")
FIGURE_DIR = Path("results/figures")

METHOD_ORDER = ("DSDA", "RBFOpt")
PRIMARY_TOLERANCE = 1e-5
TOLERANCES = (1e-1, 1e-3, 1e-5, 1e-7)

REQUIRED_COLUMNS = {
    "csv_name",
    "method",
    "seed",
    "n_starts",
    "max_evals",
    "best_value",
    "best_point",
    "total_evals",
    "wall_time_s",
    "found_optimum",
    "incumbent_trajectory",
}


def _pyplot():
    import matplotlib.pyplot as plt

    return plt


def configure_plot_style():
    """Apply the benchmark analysis plotting style."""
    plt = _pyplot()
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "legend.fontsize": 10,
            "font.size": 10,
        }
    )


def parse_float_sequence(value):
    """Parse comma-separated floating-point values."""
    values = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if chunk:
            values.append(float(chunk))
    if not values:
        raise argparse.ArgumentTypeError("At least one float value is required")
    return values


def find_latest_results_csv(results_csv=None, results_dir=RESULTS_DIR):
    """Return an explicit CSV path or the newest benchmark CSV in results_dir."""
    if results_csv is not None:
        path = Path(results_csv)
        if not path.exists():
            raise FileNotFoundError(f"Benchmark results CSV does not exist: {path}")
        return path

    candidates = sorted(Path(results_dir).glob("benchmark_*.csv"))
    if not candidates:
        raise FileNotFoundError(
            "No benchmark CSV found. Run benchmark.py first or pass "
            "--results-csv with an explicit results file."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _json_or_value(value):
    if value is None or isinstance(value, (list, tuple, dict)):
        return value
    if isinstance(value, float) and pd.isna(value):
        return value
    if not isinstance(value, str):
        return value

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def load_benchmark_results(results_csv):
    """Load the unified benchmark CSV written by benchmark.py."""
    df = pd.read_csv(results_csv)
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Results CSV is missing required columns: {missing_text}")

    df = df.copy()
    df["method"] = df["method"].astype(str)
    for column in ("seed", "n_starts", "max_evals", "total_evals"):
        df[column] = pd.to_numeric(df[column], errors="raise").astype(int)
    for column in ("best_value", "wall_time_s"):
        df[column] = pd.to_numeric(df[column], errors="raise")

    df["found_optimum"] = (
        df["found_optimum"].astype(str).str.lower().isin({"true", "1", "yes"})
    )
    df["best_point"] = df["best_point"].apply(_json_or_value)
    df["incumbent_trajectory"] = df["incumbent_trajectory"].apply(_json_or_value)
    return df


def load_grid_metadata(grids_dir=GRIDS_DIR):
    """Load known optima and dimensions from benchmark grid CSV files."""
    rows = []
    for path in sorted(Path(grids_dir).glob("*.csv")):
        grid_df = pd.read_csv(path)
        value_column = "z_norm" if "z_norm" in grid_df.columns else grid_df.columns[-1]
        coordinate_columns = [
            column for column in grid_df.columns if column != value_column
        ]
        rows.append(
            {
                "csv_name": path.name,
                "target_value": float(grid_df[value_column].min()),
                "dimension": len(coordinate_columns),
                "grid_points": len(grid_df),
            }
        )

    if not rows:
        raise FileNotFoundError(f"No grid CSV files found in {grids_dir}")
    return pd.DataFrame(rows)


def attach_grid_metadata(results_df, grids_dir=GRIDS_DIR):
    """Attach known target values and dimensions to benchmark results."""
    metadata = load_grid_metadata(grids_dir)
    merged = results_df.merge(metadata, on="csv_name", how="left")

    missing_target = merged["target_value"].isna()
    if missing_target.any():
        observed_best = merged.groupby("csv_name")["best_value"].transform("min")
        merged.loc[missing_target, "target_value"] = observed_best[missing_target]
        merged.loc[missing_target, "dimension"] = 1
        merged.loc[missing_target, "grid_points"] = np.nan
        print(
            "Warning: some grids were not found in GRIDS_DIR. "
            "Observed best values were used as fallback targets."
        )

    merged["dimension"] = merged["dimension"].fillna(1).astype(int)
    return merged


def tolerance_window(target_value, tolerance):
    """Return the absolute solve window for a target and relative tolerance."""
    return tolerance * max(1.0, abs(float(target_value)))


def first_eval_within_tolerance(trajectory, target_value, tolerance):
    """Return the 1-based first evaluation that reaches the tolerance."""
    if not isinstance(trajectory, (list, tuple)):
        return math.nan

    threshold = float(target_value) + tolerance_window(target_value, tolerance)
    for eval_number, value in enumerate(trajectory, start=1):
        if float(value) <= threshold:
            return eval_number
    return math.nan


def annotate_solve_status(results_df, tolerance=PRIMARY_TOLERANCE):
    """Add solved and evals_to_solve columns for one tolerance level."""
    df = results_df.copy()
    df["tolerance"] = tolerance
    df["evals_to_solve"] = [
        first_eval_within_tolerance(trajectory, target, tolerance)
        for trajectory, target in zip(
            df["incumbent_trajectory"], df["target_value"], strict=True
        )
    ]

    exact_fallback = df["evals_to_solve"].isna() & df["found_optimum"]
    df.loc[exact_fallback, "evals_to_solve"] = df.loc[
        exact_fallback, "total_evals"
    ]
    df["solved"] = df["evals_to_solve"].notna()
    return df


def solved_fraction_summary(results_df, tolerance=PRIMARY_TOLERANCE):
    """Return solved fractions by method and budget."""
    return (
        annotate_solve_status(results_df, tolerance)
        .groupby(["method", "max_evals"])["solved"]
        .mean()
        .unstack("max_evals")
    )


def performance_ratio_table(results_df, tolerance=PRIMARY_TOLERANCE, budget=None):
    """Build a method-by-problem table of Dolan-More performance ratios."""
    data = annotate_solve_status(results_df, tolerance)
    if budget is not None:
        data = data[data["max_evals"] == budget]

    pivot = data.pivot_table(
        index=["csv_name", "seed"],
        columns="method",
        values="evals_to_solve",
        aggfunc="min",
    )
    best = pivot.min(axis=1, skipna=True)
    pivot = pivot.loc[best.notna()]
    if pivot.empty:
        return pivot
    return pivot.div(best.loc[pivot.index], axis=0)


def _finite_profile_grid(ratios):
    finite = ratios.to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return np.array([1.0, 2.0])
    return np.linspace(1.0, max(2.0, float(finite.max())), 200)


def plot_performance_profiles(
    results_df,
    tolerance=PRIMARY_TOLERANCE,
    budgets=None,
    method_order=METHOD_ORDER,
):
    """Plot performance profiles by budget level."""
    plt = _pyplot()
    if budgets is None:
        budgets = sorted(results_df["max_evals"].unique())

    fig, axes = plt.subplots(
        1,
        len(budgets),
        figsize=(4.2 * len(budgets), 3.4),
        sharey=True,
        squeeze=False,
    )

    for ax, budget in zip(axes.ravel(), budgets, strict=True):
        ratios = performance_ratio_table(results_df, tolerance, budget)
        tau_values = _finite_profile_grid(ratios)
        methods = [method for method in method_order if method in ratios.columns]

        if ratios.empty or not methods:
            ax.text(0.5, 0.5, "No solved instances", ha="center", va="center")
        else:
            denominator = len(ratios)
            for method in methods:
                method_ratios = ratios[method].to_numpy(dtype=float)
                fractions = [
                    np.sum(method_ratios <= tau) / denominator
                    for tau in tau_values
                ]
                ax.step(tau_values, fractions, where="post", label=method, lw=2)

        ax.set_title(f"max_evals = {budget}")
        ax.set_xlabel("performance ratio tau")
        ax.set_ylim(0.0, 1.02)
        handles, _ = ax.get_legend_handles_labels()
        if handles:
            ax.legend(loc="lower right")

    axes.ravel()[0].set_ylabel("fraction solved")
    fig.suptitle(f"Performance profiles, tolerance={tolerance:g}")
    fig.tight_layout()
    return fig


def longest_budget_rows(results_df):
    """Keep the row with the largest budget for each grid, seed, and method."""
    idx = results_df.groupby(["csv_name", "seed", "method"])["max_evals"].idxmax()
    return results_df.loc[idx].copy()


def data_profile_frame(results_df, tolerance=PRIMARY_TOLERANCE):
    """Return solve times normalized by dimension for data profiles."""
    data = annotate_solve_status(longest_budget_rows(results_df), tolerance)
    data["normalized_evals_to_solve"] = data["evals_to_solve"] / data["dimension"]
    return data


def plot_data_profiles(
    results_df,
    tolerances=TOLERANCES,
    method_order=METHOD_ORDER,
):
    """Plot More-Wild data profiles for one or more tolerance levels."""
    plt = _pyplot()
    fig, axes = plt.subplots(
        1,
        len(tolerances),
        figsize=(4.2 * len(tolerances), 3.4),
        sharey=True,
        squeeze=False,
    )

    for ax, tolerance in zip(axes.ravel(), tolerances, strict=True):
        data = data_profile_frame(results_df, tolerance)
        methods = [method for method in method_order if method in set(data["method"])]
        finite = data["normalized_evals_to_solve"].dropna()
        max_x = max(1.0, float(finite.max())) if not finite.empty else 1.0
        x_values = np.linspace(0.0, max_x, 200)

        for method in methods:
            method_values = data.loc[
                data["method"] == method,
                "normalized_evals_to_solve",
            ].to_numpy(dtype=float)
            denominator = len(method_values)
            fractions = [
                np.sum(method_values <= x_value) / denominator
                for x_value in x_values
            ]
            ax.step(x_values, fractions, where="post", label=method, lw=2)

        ax.set_title(f"tolerance = {tolerance:g}")
        ax.set_xlabel("evaluations / dimension")
        ax.set_ylim(0.0, 1.02)
        handles, _ = ax.get_legend_handles_labels()
        if handles:
            ax.legend(loc="lower right")

    axes.ravel()[0].set_ylabel("fraction solved")
    fig.suptitle("Data profiles")
    fig.tight_layout()
    return fig


def plot_best_value_boxplots(results_df, method_order=METHOD_ORDER):
    """Box plots of final best_value by method at each budget."""
    plt = _pyplot()
    budgets = sorted(results_df["max_evals"].unique())
    fig, axes = plt.subplots(
        1,
        len(budgets),
        figsize=(4.0 * len(budgets), 3.4),
        sharey=True,
        squeeze=False,
    )

    for ax, budget in zip(axes.ravel(), budgets, strict=True):
        data = results_df[results_df["max_evals"] == budget]
        methods = [method for method in method_order if method in set(data["method"])]
        values = [data.loc[data["method"] == method, "best_value"] for method in methods]
        try:
            ax.boxplot(values, tick_labels=methods, showmeans=True)
        except TypeError:
            ax.boxplot(values, labels=methods, showmeans=True)
        ax.set_title(f"max_evals = {budget}")
        ax.set_xlabel("method")

    axes.ravel()[0].set_ylabel("best_value")
    fig.suptitle("Best value distributions")
    fig.tight_layout()
    return fig


def plot_winner_heatmap(results_df, method_a="DSDA", method_b="RBFOpt"):
    """Heatmap of average winner by grid and budget for two methods."""
    plt = _pyplot()
    pivot = results_df.pivot_table(
        index=["csv_name", "max_evals"],
        columns="method",
        values="best_value",
        aggfunc="mean",
    )
    if method_a not in pivot.columns or method_b not in pivot.columns:
        raise ValueError(f"Expected both {method_a} and {method_b} in results")

    # Positive deltas favor method_a because the benchmark is minimizing.
    delta = (pivot[method_b] - pivot[method_a]).unstack("max_evals")
    if delta.empty:
        raise ValueError("No paired rows found for winner heatmap")

    fig_height = max(4.0, 0.35 * len(delta.index))
    fig, ax = plt.subplots(figsize=(8.0, fig_height))
    image = ax.imshow(delta.to_numpy(), cmap="coolwarm", aspect="auto")
    ax.set_xticks(np.arange(len(delta.columns)), labels=delta.columns)
    ax.set_yticks(np.arange(len(delta.index)), labels=delta.index)
    ax.set_xlabel("max_evals")
    ax.set_ylabel("grid")
    ax.set_title(f"Average winner: positive favors {method_a}")

    for y_index, grid_name in enumerate(delta.index):
        for x_index, budget in enumerate(delta.columns):
            value = delta.loc[grid_name, budget]
            if pd.isna(value):
                label = "missing"
            elif np.isclose(value, 0.0):
                label = "tie"
            else:
                label = method_a if value > 0 else method_b
            ax.text(x_index, y_index, label, ha="center", va="center", fontsize=8)

    fig.colorbar(
        image,
        ax=ax,
        label=f"mean {method_b} best_value - mean {method_a} best_value",
    )
    fig.tight_layout()
    return fig


def plot_wall_time_scatter(results_df, method_a="DSDA", method_b="RBFOpt"):
    """Scatter plot of paired wall time per grid, seed, and budget."""
    plt = _pyplot()
    paired = results_df.pivot_table(
        index=["csv_name", "seed", "max_evals"],
        columns="method",
        values="wall_time_s",
        aggfunc="mean",
    )
    if method_a not in paired.columns or method_b not in paired.columns:
        raise ValueError(f"Expected both {method_a} and {method_b} in results")
    paired = paired.dropna(subset=[method_a, method_b])

    fig, ax = plt.subplots(figsize=(5.0, 4.2))
    if paired.empty:
        ax.text(0.5, 0.5, "No paired wall-time rows", ha="center", va="center")
    else:
        ax.scatter(paired[method_a], paired[method_b], alpha=0.7)
        max_time = float(np.nanmax(paired[[method_a, method_b]].to_numpy()))
        max_time = max(max_time, 1e-12)
        ax.plot([0, max_time], [0, max_time], color="black", ls="--", lw=1)

    ax.set_xlabel(f"{method_a} wall_time_s")
    ax.set_ylabel(f"{method_b} wall_time_s")
    ax.set_title("Paired wall-time comparison")
    fig.tight_layout()
    return fig


def trajectory_mean_frame(results_df, grid_name=None, budget=None):
    """Explode incumbent trajectories and average them over seeds."""
    data = results_df.copy()
    if grid_name is None:
        grid_name = sorted(data["csv_name"].unique())[0]
    if budget is None:
        budget = int(data["max_evals"].max())

    data = data[(data["csv_name"] == grid_name) & (data["max_evals"] == budget)]
    rows = []
    for row in data.itertuples(index=False):
        trajectory = row.incumbent_trajectory
        if not isinstance(trajectory, (list, tuple)):
            continue
        for eval_number, incumbent in enumerate(trajectory, start=1):
            rows.append(
                {
                    "csv_name": row.csv_name,
                    "method": row.method,
                    "seed": row.seed,
                    "max_evals": row.max_evals,
                    "eval_number": eval_number,
                    "incumbent": float(incumbent),
                }
            )

    if not rows:
        raise ValueError(f"No trajectories found for grid={grid_name}, budget={budget}")

    trajectory_df = pd.DataFrame(rows)
    return (
        trajectory_df.groupby(["method", "eval_number"], as_index=False)[
            "incumbent"
        ]
        .mean()
        .sort_values(["method", "eval_number"])
    )


def plot_convergence_curves(
    results_df,
    grid_name=None,
    budget=None,
    method_order=METHOD_ORDER,
):
    """Plot mean incumbent value vs evaluation count for one grid and budget."""
    plt = _pyplot()
    if grid_name is None:
        grid_name = sorted(results_df["csv_name"].unique())[0]
    if budget is None:
        budget = int(results_df["max_evals"].max())

    means = trajectory_mean_frame(results_df, grid_name=grid_name, budget=budget)
    fig, ax = plt.subplots(figsize=(5.5, 4.0))
    for method in method_order:
        method_data = means[means["method"] == method]
        if method_data.empty:
            continue
        ax.plot(
            method_data["eval_number"],
            method_data["incumbent"],
            marker="o",
            linewidth=2,
            label=method,
        )

    ax.set_xlabel("evaluation count")
    ax.set_ylabel("mean incumbent best_value")
    ax.set_title(f"Convergence curves: {grid_name}, max_evals={budget}")
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend()
    fig.tight_layout()
    return fig


def holm_bonferroni(results_df, p_col="p_value", alpha=0.05):
    """Add Holm-Bonferroni adjusted p-values and reject flags."""
    if results_df.empty:
        return results_df.copy()

    adjusted = results_df.copy()
    order = adjusted[p_col].sort_values().index.tolist()
    m_tests = len(order)
    running_max = 0.0
    adjusted["holm_p_value"] = np.nan

    for rank, index in enumerate(order, start=1):
        raw_adjusted = min(1.0, (m_tests - rank + 1) * adjusted.loc[index, p_col])
        running_max = max(running_max, raw_adjusted)
        adjusted.loc[index, "holm_p_value"] = running_max

    adjusted["holm_reject_0.05"] = adjusted["holm_p_value"] <= alpha
    return adjusted.sort_values("max_evals").reset_index(drop=True)


def rank_biserial_from_differences(differences):
    """Return rank-biserial correlation from paired differences."""
    differences = np.asarray(differences, dtype=float)
    differences = differences[~np.isclose(differences, 0.0)]
    if differences.size == 0:
        return 0.0

    ranks = stats.rankdata(np.abs(differences))
    positive = ranks[differences > 0].sum()
    negative = ranks[differences < 0].sum()
    return float((positive - negative) / ranks.sum())


def wilcoxon_by_budget(results_df, method_a="DSDA", method_b="RBFOpt"):
    """Run paired Wilcoxon signed-rank tests at each budget level."""
    aggregated = results_df.groupby(
        ["csv_name", "max_evals", "method"], as_index=False
    )["best_value"].mean()
    rows = []

    for budget, budget_df in aggregated.groupby("max_evals"):
        paired = budget_df.pivot(
            index="csv_name",
            columns="method",
            values="best_value",
        )
        if method_a not in paired.columns or method_b not in paired.columns:
            continue
        paired = paired.dropna(subset=[method_a, method_b])
        if paired.empty:
            continue

        differences = paired[method_b] - paired[method_a]
        if np.allclose(differences, 0.0):
            statistic = 0.0
            p_value = 1.0
        else:
            result = stats.wilcoxon(
                paired[method_a],
                paired[method_b],
                zero_method="wilcox",
                alternative="two-sided",
            )
            statistic = float(result.statistic)
            p_value = float(result.pvalue)

        rows.append(
            {
                "max_evals": int(budget),
                "n_pairs": len(paired),
                "method_a": method_a,
                "method_b": method_b,
                "mean_difference_b_minus_a": float(differences.mean()),
                "wilcoxon_statistic": statistic,
                "p_value": p_value,
                "rank_biserial_effect": rank_biserial_from_differences(
                    differences
                ),
            }
        )

    return holm_bonferroni(pd.DataFrame(rows))


def friedman_by_budget(results_df):
    """Run Friedman tests by budget when three or more methods are present."""
    methods = sorted(results_df["method"].unique())
    if len(methods) < 3:
        raise ValueError("Friedman tests require at least three methods.")

    aggregated = results_df.groupby(
        ["csv_name", "max_evals", "method"], as_index=False
    )["best_value"].mean()
    rows = []

    for budget, budget_df in aggregated.groupby("max_evals"):
        paired = budget_df.pivot(
            index="csv_name",
            columns="method",
            values="best_value",
        )
        paired = paired.dropna(subset=methods)
        if paired.empty:
            continue
        result = stats.friedmanchisquare(
            *(paired[method].to_numpy() for method in methods)
        )
        rows.append(
            {
                "max_evals": int(budget),
                "n_blocks": len(paired),
                "methods": methods,
                "friedman_statistic": float(result.statistic),
                "p_value": float(result.pvalue),
            }
        )

    return pd.DataFrame(rows)


def load_analysis_dataset(results_csv=None, results_dir=RESULTS_DIR, grids_dir=GRIDS_DIR):
    """Load benchmark results and attach grid metadata."""
    results_path = find_latest_results_csv(results_csv, results_dir)
    raw_results = load_benchmark_results(results_path)
    return attach_grid_metadata(raw_results, grids_dir), results_path


def save_default_figures(
    results_df,
    figure_dir=FIGURE_DIR,
    tolerance=PRIMARY_TOLERANCE,
    data_profile_tolerances=TOLERANCES,
):
    """Create and save the standard Issue #10 benchmark figures."""
    plt = _pyplot()
    figure_dir = Path(figure_dir)
    figure_dir.mkdir(parents=True, exist_ok=True)

    figure_factories = [
        (
            "performance_profiles.png",
            lambda: plot_performance_profiles(results_df, tolerance=tolerance),
        ),
        (
            "data_profiles.png",
            lambda: plot_data_profiles(
                results_df,
                tolerances=data_profile_tolerances,
            ),
        ),
        ("best_value_boxplots.png", lambda: plot_best_value_boxplots(results_df)),
        ("convergence_curves.png", lambda: plot_convergence_curves(results_df)),
    ]

    if {"DSDA", "RBFOpt"}.issubset(set(results_df["method"])):
        figure_factories.extend(
            [
                ("winner_heatmap.png", lambda: plot_winner_heatmap(results_df)),
                ("wall_time_scatter.png", lambda: plot_wall_time_scatter(results_df)),
            ]
        )

    saved_paths = []
    for filename, figure_factory in figure_factories:
        fig = figure_factory()
        path = figure_dir / filename
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        saved_paths.append(path)

    return saved_paths


def save_statistics_tables(
    results_df,
    output_dir=FIGURE_DIR,
    tolerance=PRIMARY_TOLERANCE,
):
    """Save solved-summary and Wilcoxon result CSV tables."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    summary_path = output_dir / "solved_fraction_summary.csv"
    solved_fraction_summary(results_df, tolerance).to_csv(summary_path)
    saved_paths.append(summary_path)

    if {"DSDA", "RBFOpt"}.issubset(set(results_df["method"])):
        wilcoxon_path = output_dir / "wilcoxon_by_budget.csv"
        wilcoxon_by_budget(results_df).to_csv(wilcoxon_path, index=False)
        saved_paths.append(wilcoxon_path)

    return saved_paths


def create_analysis_outputs(
    results_csv=None,
    results_dir=RESULTS_DIR,
    grids_dir=GRIDS_DIR,
    figure_dir=FIGURE_DIR,
    tolerance=PRIMARY_TOLERANCE,
    data_profile_tolerances=TOLERANCES,
):
    """Load results, save standard figures, and save statistics tables."""
    configure_plot_style()
    results_df, results_path = load_analysis_dataset(results_csv, results_dir, grids_dir)
    figure_paths = save_default_figures(
        results_df,
        figure_dir=figure_dir,
        tolerance=tolerance,
        data_profile_tolerances=data_profile_tolerances,
    )
    table_paths = save_statistics_tables(
        results_df,
        output_dir=figure_dir,
        tolerance=tolerance,
    )
    return {
        "results_path": results_path,
        "figure_paths": figure_paths,
        "table_paths": table_paths,
    }


def build_parser():
    """Build the benchmark analysis CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-csv",
        type=Path,
        default=None,
        help="Explicit benchmark results CSV. Defaults to newest results CSV.",
    )
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--grids-dir", type=Path, default=GRIDS_DIR)
    parser.add_argument("--figure-dir", type=Path, default=FIGURE_DIR)
    parser.add_argument("--tolerance", type=float, default=PRIMARY_TOLERANCE)
    parser.add_argument(
        "--data-profile-tolerances",
        type=parse_float_sequence,
        default=list(TOLERANCES),
        help="Comma-separated data-profile tolerances.",
    )
    return parser


def main(argv=None):
    """CLI entry point for benchmark analysis outputs."""
    args = build_parser().parse_args(argv)
    outputs = create_analysis_outputs(
        results_csv=args.results_csv,
        results_dir=args.results_dir,
        grids_dir=args.grids_dir,
        figure_dir=args.figure_dir,
        tolerance=args.tolerance,
        data_profile_tolerances=args.data_profile_tolerances,
    )

    print(f"Loaded benchmark results from: {outputs['results_path']}")
    print("Saved figures:")
    for path in outputs["figure_paths"]:
        print(f"  {path}")
    print("Saved tables:")
    for path in outputs["table_paths"]:
        print(f"  {path}")
    return outputs


if __name__ == "__main__":
    main()
