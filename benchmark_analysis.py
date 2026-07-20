"""Analysis and plotting helpers for benchmark.py result CSVs."""

import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


RESULTS_DIR = Path("results")
GRIDS_DIR = Path("benchmark_grids")
FIGURE_DIR = Path("results/figures")

METHOD_ORDER = ("DSDA", "RBFOpt", "BAM")
METHOD_COLORS = {
    "DSDA": "#1f77b4",
    "RBFOpt": "#ff7f0e",
    "BAM": "#2ca02c",
}
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


def ordered_method_names(methods, method_order=METHOD_ORDER):
    """Return preferred methods followed by any additional observed methods."""
    observed = {str(method) for method in methods if pd.notna(method)}
    preferred = [method for method in method_order if method in observed]
    return preferred + sorted(observed.difference(preferred))


def ordered_methods(results_df, method_order=METHOD_ORDER):
    """Return method names from a benchmark results frame in display order."""
    return ordered_method_names(results_df["method"], method_order)


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
        missing_names = sorted(merged.loc[missing_target, "csv_name"].unique())
        missing_text = ", ".join(missing_names)
        raise ValueError(
            "Missing grid metadata for result CSV(s): "
            f"{missing_text}. Ensure every csv_name exists in {grids_dir}."
        )

    merged["dimension"] = merged["dimension"].astype(int)
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


def runs_to_target_probability(hit_rate, target_probability=0.99):
    """Return independent runs needed to reach the target probability."""
    hit_rate = float(hit_rate)
    target_probability = float(target_probability)
    if not 0.0 <= hit_rate <= 1.0:
        raise ValueError("hit_rate must be between 0 and 1")
    if not 0.0 < target_probability < 1.0:
        raise ValueError("target_probability must be between 0 and 1")
    if hit_rate == 0.0:
        return math.inf
    if hit_rate == 1.0:
        return 1
    return math.ceil(math.log1p(-target_probability) / math.log1p(-hit_rate))


def tts99_summary(results_df):
    """Summarize exact-optimum hit rates and median-time TTS99 across seeds."""
    group_columns = ["csv_name", "method", "n_starts", "max_evals"]
    missing = set(group_columns + ["seed", "found_optimum", "wall_time_s"]).difference(
        results_df.columns
    )
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"TTS99 input is missing required columns: {missing_text}")
    if (results_df["wall_time_s"] < 0).any():
        raise ValueError("wall_time_s must be nonnegative")

    summary = (
        results_df.groupby(group_columns, as_index=False, dropna=False)
        .agg(
            n_runs=("seed", "size"),
            hits=("found_optimum", "sum"),
            hit_rate=("found_optimum", "mean"),
            median_wall_time_s=("wall_time_s", "median"),
        )
        .sort_values(group_columns)
        .reset_index(drop=True)
    )
    summary["hits"] = summary["hits"].astype(int)
    summary["runs_99"] = summary["hit_rate"].apply(runs_to_target_probability)
    summary["tts99_s"] = summary["runs_99"] * summary["median_wall_time_s"]
    summary.loc[summary["hit_rate"] == 0.0, "tts99_s"] = math.inf
    return summary


def performance_ratio_table(results_df, tolerance=PRIMARY_TOLERANCE, budget=None):
    """Build a method-by-problem table of Dolan-More performance ratios."""
    data = annotate_solve_status(results_df, tolerance)
    if budget is not None:
        data = data[data["max_evals"] == budget]

    pivot = (
        data.groupby(["csv_name", "seed", "method"], dropna=False)[
            "evals_to_solve"
        ]
        .min()
        .unstack("method")
    )
    best = pivot.min(axis=1, skipna=True)
    if pivot.empty:
        return pivot
    return pivot.div(best, axis=0)


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
        methods = ordered_method_names(ratios.columns, method_order)

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
                ax.step(
                    tau_values,
                    fractions,
                    where="post",
                    label=method,
                    color=METHOD_COLORS.get(method),
                    lw=2,
                )

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
        methods = ordered_methods(data, method_order)
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
            ax.step(
                x_values,
                fractions,
                where="post",
                label=method,
                color=METHOD_COLORS.get(method),
                lw=2,
            )

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
        methods = ordered_methods(data, method_order)
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


def winner_heatmap_frames(results_df, method_order=METHOD_ORDER):
    """Return winner labels and best-to-runner-up margins by grid and budget."""
    pivot = results_df.pivot_table(
        index=["csv_name", "max_evals"],
        columns="method",
        values="best_value",
        aggfunc="mean",
    )
    methods = ordered_method_names(pivot.columns, method_order)
    if len(methods) < 2:
        raise ValueError("Winner heatmaps require at least two methods")

    rows = []
    for (grid_name, budget), values in pivot[methods].iterrows():
        if values.isna().all():
            continue
        if values.isna().any():
            rows.append(
                {
                    "csv_name": grid_name,
                    "max_evals": budget,
                    "winner": "incomplete",
                    "winning_margin": math.nan,
                }
            )
            continue
        best_value = float(values.min())
        winners = [
            method
            for method in methods
            if method in values.index
            and np.isclose(float(values[method]), best_value)
        ]
        if len(winners) > 1:
            margin = 0.0
        elif len(values) > 1:
            margin = float(values.nsmallest(2).iloc[1] - best_value)
        else:
            margin = math.nan
        rows.append(
            {
                "csv_name": grid_name,
                "max_evals": budget,
                "winner": " / ".join(winners),
                "winning_margin": margin,
            }
        )

    if not rows:
        raise ValueError("No rows found for winner heatmap")
    frame = pd.DataFrame(rows)
    labels = frame.pivot(index="csv_name", columns="max_evals", values="winner")
    margins = frame.pivot(
        index="csv_name",
        columns="max_evals",
        values="winning_margin",
    )
    return labels, margins


def plot_winner_heatmap(results_df, method_order=METHOD_ORDER):
    """Heatmap of the winning method and its margin over the runner-up."""
    plt = _pyplot()
    labels, margins = winner_heatmap_frames(results_df, method_order)
    plot_values = np.ma.masked_invalid(margins.to_numpy(dtype=float))

    fig_height = max(4.0, 0.35 * len(margins.index))
    fig, ax = plt.subplots(figsize=(8.0, fig_height))
    image = ax.imshow(plot_values, cmap="YlGn", aspect="auto", vmin=0.0)
    ax.set_xticks(np.arange(len(margins.columns)), labels=margins.columns)
    ax.set_yticks(np.arange(len(margins.index)), labels=margins.index)
    ax.set_xlabel("max_evals")
    ax.set_ylabel("grid")
    ax.set_title("Average winner and margin over runner-up")

    finite_margins = margins.to_numpy(dtype=float)
    finite_margins = finite_margins[np.isfinite(finite_margins)]
    max_margin = float(finite_margins.max()) if finite_margins.size else 0.0
    for y_index, grid_name in enumerate(labels.index):
        for x_index, budget in enumerate(labels.columns):
            label = labels.loc[grid_name, budget]
            margin = margins.loc[grid_name, budget]
            if pd.isna(label):
                annotation = "missing"
            elif pd.isna(margin):
                annotation = str(label)
            else:
                annotation = f"{label}\n{margin:.3g}"
            text_color = (
                "white"
                if max_margin > 0 and pd.notna(margin) and margin > max_margin / 2
                else "black"
            )
            ax.text(
                x_index,
                y_index,
                annotation,
                ha="center",
                va="center",
                fontsize=8,
                color=text_color,
            )

    fig.colorbar(image, ax=ax, label="runner-up mean - winning mean best_value")
    fig.tight_layout()
    return fig


def plot_wall_time_scatter(
    results_df,
    method_a="DSDA",
    method_b=None,
    method_order=METHOD_ORDER,
):
    """Plot paired wall times for one baseline against every other method."""
    plt = _pyplot()
    methods = ordered_methods(results_df, method_order)
    if method_a not in methods:
        raise ValueError(f"Expected {method_a} in results")
    comparison_methods = (
        [method_b] if method_b is not None else [m for m in methods if m != method_a]
    )
    missing = set(comparison_methods).difference(methods)
    if missing:
        raise ValueError(f"Missing comparison method(s): {', '.join(sorted(missing))}")
    if not comparison_methods:
        raise ValueError("Wall-time comparisons require at least two methods")

    paired = results_df.pivot_table(
        index=["csv_name", "seed", "max_evals"],
        columns="method",
        values="wall_time_s",
        aggfunc="mean",
    )
    fig, axes = plt.subplots(
        1,
        len(comparison_methods),
        figsize=(4.8 * len(comparison_methods), 4.2),
        squeeze=False,
    )

    for ax, comparison_method in zip(
        axes.ravel(), comparison_methods, strict=True
    ):
        comparison = paired.dropna(subset=[method_a, comparison_method])
        if comparison.empty:
            ax.text(0.5, 0.5, "No paired wall-time rows", ha="center", va="center")
        else:
            ax.scatter(
                comparison[method_a],
                comparison[comparison_method],
                alpha=0.7,
                color=METHOD_COLORS.get(comparison_method),
            )
            max_time = float(
                np.nanmax(comparison[[method_a, comparison_method]].to_numpy())
            )
            max_time = max(max_time, 1e-12)
            ax.plot([0, max_time], [0, max_time], color="black", ls="--", lw=1)

        ax.set_xlabel(f"{method_a} wall_time_s")
        ax.set_ylabel(f"{comparison_method} wall_time_s")
        ax.set_title(f"{method_a} vs {comparison_method}")

    fig.suptitle("Paired wall-time comparison")
    fig.tight_layout()
    return fig


def plot_tts99_comparison(results_df, method_order=METHOD_ORDER):
    """Plot per-problem TTS99 values by method and evaluation budget."""
    plt = _pyplot()
    summary = tts99_summary(results_df)
    budgets = sorted(summary["max_evals"].unique())
    methods = ordered_methods(summary, method_order)
    fig, axes = plt.subplots(
        1,
        len(budgets),
        figsize=(4.2 * len(budgets), 3.8),
        sharey=True,
        squeeze=False,
    )

    finite_values = summary.loc[np.isfinite(summary["tts99_s"]), "tts99_s"]
    marker_height = (
        max(1.0, float(finite_values.max()) * 1.1) if len(finite_values) else 1.0
    )

    for ax, budget in zip(axes.ravel(), budgets, strict=True):
        budget_summary = summary[summary["max_evals"] == budget]
        for method_index, method in enumerate(methods, start=1):
            values = budget_summary.loc[
                budget_summary["method"] == method,
                "tts99_s",
            ].to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            if finite.size:
                ax.scatter(
                    np.full(finite.size, method_index),
                    finite,
                    color=METHOD_COLORS.get(method),
                    alpha=0.7,
                )
                median = float(np.median(finite))
                ax.plot(
                    [method_index - 0.2, method_index + 0.2],
                    [median, median],
                    color="black",
                    lw=2,
                )

            infinite_count = int(np.isinf(values).sum())
            if infinite_count:
                ax.scatter(
                    [method_index],
                    [marker_height],
                    marker="^",
                    color="red",
                    zorder=3,
                )
                ax.annotate(
                    f"∞×{infinite_count}",
                    (method_index, marker_height),
                    xytext=(0, 5),
                    textcoords="offset points",
                    ha="center",
                    color="red",
                    fontsize=8,
                )

        ax.set_xticks(range(1, len(methods) + 1), labels=methods)
        ax.set_title(f"max_evals = {budget}")
        ax.set_xlabel("method")
        ax.set_ylim(bottom=0.0, top=marker_height * 1.2)

    axes.ravel()[0].set_ylabel("TTS99 (seconds)")
    fig.suptitle("TTS99 by problem (∞ marks zero-hit groups)")
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
        if not isinstance(trajectory, (list, tuple)) or not trajectory:
            raise ValueError(
                "Missing incumbent trajectory for "
                f"grid={row.csv_name}, method={row.method}, seed={row.seed}"
            )
        trajectory = [float(incumbent) for incumbent in trajectory]
        for eval_number in range(1, int(budget) + 1):
            incumbent = trajectory[min(eval_number - 1, len(trajectory) - 1)]
            rows.append(
                {
                    "csv_name": row.csv_name,
                    "method": row.method,
                    "seed": row.seed,
                    "max_evals": row.max_evals,
                    "eval_number": eval_number,
                    "incumbent": incumbent,
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
    """Plot seed-averaged convergence, with one panel per selected grid."""
    plt = _pyplot()
    if budget is None:
        budget = int(results_df["max_evals"].max())
    budget_data = results_df[results_df["max_evals"] == budget]
    if grid_name is None:
        grid_names = sorted(budget_data["csv_name"].unique())
    else:
        grid_names = [grid_name]
    if not grid_names:
        raise ValueError(f"No trajectories found for budget={budget}")

    n_columns = min(3, len(grid_names))
    n_rows = math.ceil(len(grid_names) / n_columns)
    figure_height = 3.3 * n_rows
    fig, axes = plt.subplots(
        n_rows,
        n_columns,
        figsize=(4.2 * n_columns, figure_height),
        squeeze=False,
        sharex=True,
    )
    methods = ordered_methods(budget_data, method_order)
    for ax, selected_grid in zip(axes.ravel(), grid_names, strict=False):
        means = trajectory_mean_frame(
            results_df,
            grid_name=selected_grid,
            budget=budget,
        )
        for method in methods:
            method_data = means[means["method"] == method]
            if method_data.empty:
                continue
            ax.plot(
                method_data["eval_number"],
                method_data["incumbent"],
                marker="o",
                markersize=3,
                linewidth=1.8,
                label=method,
                color=METHOD_COLORS.get(method),
            )
        ax.set_xlabel("evaluation count")
        ax.set_ylabel("mean incumbent best_value")
        ax.set_title(selected_grid)

    for ax in axes.ravel()[len(grid_names) :]:
        ax.set_visible(False)

    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    header_height = 0.7
    if handles:
        legend_y = 1.0 - 0.28 / figure_height
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, legend_y),
            ncol=len(labels),
        )
    fig.suptitle(f"Convergence curves, max_evals={budget}", y=0.995)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 1.0 - header_height / figure_height))
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

    adjusted["holm_alpha"] = float(alpha)
    adjusted["holm_reject"] = adjusted["holm_p_value"] <= alpha
    sort_columns = [
        column
        for column in ("max_evals", "method_a", "method_b")
        if column in adjusted
    ]
    return adjusted.sort_values(sort_columns).reset_index(drop=True)


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


def pairwise_wilcoxon_by_budget(results_df, method_order=METHOD_ORDER):
    """Run every method pair and apply one Holm correction to all tests."""
    methods = ordered_methods(results_df, method_order)
    rows = []
    for method_a, method_b in itertools.combinations(methods, 2):
        comparison = wilcoxon_by_budget(results_df, method_a, method_b)
        if comparison.empty:
            continue
        rows.append(
            comparison.drop(
                columns=["holm_p_value", "holm_alpha", "holm_reject"],
                errors="ignore",
            )
        )
    if not rows:
        return pd.DataFrame()
    return holm_bonferroni(pd.concat(rows, ignore_index=True))


def friedman_by_budget(results_df, method_order=METHOD_ORDER):
    """Run Friedman tests by budget when three or more methods are present."""
    methods = ordered_methods(results_df, method_order)
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

    return holm_bonferroni(pd.DataFrame(rows))


def average_ranks_by_budget(results_df, method_order=METHOD_ORDER):
    """Return average minimization ranks over complete grid blocks."""
    methods = ordered_methods(results_df, method_order)
    if len(methods) < 2:
        raise ValueError("Average ranks require at least two methods.")

    aggregated = results_df.groupby(
        ["csv_name", "max_evals", "method"], as_index=False
    )["best_value"].mean()
    rows = []
    for budget, budget_df in aggregated.groupby("max_evals"):
        paired = budget_df.pivot(
            index="csv_name",
            columns="method",
            values="best_value",
        ).dropna(subset=methods)
        if paired.empty:
            continue
        average_ranks = paired[methods].rank(axis=1, method="average").mean(axis=0)
        for method in methods:
            rows.append(
                {
                    "max_evals": int(budget),
                    "n_blocks": len(paired),
                    "method": method,
                    "average_rank": float(average_ranks[method]),
                }
            )
    return pd.DataFrame(rows)


def nemenyi_by_budget(results_df, alpha=0.05, method_order=METHOD_ORDER):
    """Run Nemenyi all-pairs post-hoc comparisons on average method ranks."""
    methods = ordered_methods(results_df, method_order)
    if len(methods) < 3:
        raise ValueError("Nemenyi tests require at least three methods.")

    rank_frame = average_ranks_by_budget(results_df, method_order)
    rows = []
    n_methods = len(methods)
    q_alpha = float(
        stats.studentized_range.ppf(1.0 - alpha, n_methods, np.inf) / np.sqrt(2.0)
    )
    for budget, budget_ranks in rank_frame.groupby("max_evals"):
        n_blocks = int(budget_ranks["n_blocks"].iloc[0])
        standard_error = math.sqrt(
            n_methods * (n_methods + 1) / (6.0 * n_blocks)
        )
        critical_difference = q_alpha * standard_error
        ranks = budget_ranks.set_index("method")["average_rank"]
        for method_a, method_b in itertools.combinations(methods, 2):
            rank_difference = abs(float(ranks[method_a] - ranks[method_b]))
            statistic = rank_difference / standard_error
            p_value = float(
                stats.studentized_range.sf(
                    statistic * np.sqrt(2.0),
                    n_methods,
                    np.inf,
                )
            )
            rows.append(
                {
                    "max_evals": int(budget),
                    "n_blocks": n_blocks,
                    "method_a": method_a,
                    "method_b": method_b,
                    "average_rank_a": float(ranks[method_a]),
                    "average_rank_b": float(ranks[method_b]),
                    "rank_difference": rank_difference,
                    "critical_difference": critical_difference,
                    "p_value": p_value,
                    "significant": rank_difference > critical_difference,
                }
            )
    return pd.DataFrame(rows)


def nonsignificant_rank_groups(nemenyi_results, methods_by_rank):
    """Return maximal contiguous method groups not separated by Nemenyi tests."""
    methods_by_rank = list(methods_by_rank)
    significance = {
        frozenset((row.method_a, row.method_b)): bool(row.significant)
        for row in nemenyi_results.itertuples(index=False)
    }
    candidates = []
    for start in range(len(methods_by_rank) - 1):
        for stop in range(start + 2, len(methods_by_rank) + 1):
            group = tuple(methods_by_rank[start:stop])
            if all(
                not significance.get(frozenset(pair), True)
                for pair in itertools.combinations(group, 2)
            ):
                candidates.append(group)

    return [
        group
        for group in candidates
        if not any(set(group) < set(other) for other in candidates)
    ]


def plot_critical_difference_diagrams(
    results_df,
    alpha=0.05,
    method_order=METHOD_ORDER,
):
    """Plot average ranks and the Nemenyi critical difference by budget."""
    plt = _pyplot()
    methods = ordered_methods(results_df, method_order)
    if len(methods) < 3:
        raise ValueError("Critical-difference diagrams require at least three methods")

    rank_frame = average_ranks_by_budget(results_df, method_order)
    nemenyi = nemenyi_by_budget(results_df, alpha, method_order)
    budgets = sorted(rank_frame["max_evals"].unique())
    if not budgets:
        raise ValueError("No complete method blocks found for rank comparison")

    fig, axes = plt.subplots(
        1,
        len(budgets),
        figsize=(5.0 * len(budgets), 3.8),
        squeeze=False,
    )
    for ax, budget in zip(axes.ravel(), budgets, strict=True):
        budget_ranks = rank_frame[rank_frame["max_evals"] == budget].sort_values(
            "average_rank"
        )
        y_positions = np.linspace(0.65, 0.25, len(budget_ranks))
        ax.hlines(0.75, 1, len(methods), color="black", linewidth=1)
        ax.set_xticks(range(1, len(methods) + 1))
        ax.set_xlim(0.75, len(methods) + 0.25)
        ax.set_ylim(0.0, 1.0)
        ax.set_yticks([])
        ax.set_xlabel("average rank (lower is better)")
        ax.set_title(f"max_evals = {budget}")

        for y_position, row in zip(
            y_positions, budget_ranks.itertuples(index=False), strict=True
        ):
            ax.plot([row.average_rank, row.average_rank], [y_position, 0.75], c="0.5")
            ax.scatter(
                row.average_rank,
                y_position,
                color=METHOD_COLORS.get(row.method),
                zorder=3,
            )
            ax.text(
                row.average_rank,
                y_position - 0.06,
                f"{row.method} ({row.average_rank:.2f})",
                ha="center",
                va="top",
            )

        critical_difference = nemenyi.loc[
            nemenyi["max_evals"] == budget,
            "critical_difference",
        ].iloc[0]
        budget_nemenyi = nemenyi[nemenyi["max_evals"] == budget]
        groups = nonsignificant_rank_groups(
            budget_nemenyi,
            budget_ranks["method"],
        )
        rank_by_method = budget_ranks.set_index("method")["average_rank"]
        group_y_values = np.linspace(0.80, 0.88, len(groups))
        for group, group_y in zip(groups, group_y_values, strict=True):
            group_ranks = rank_by_method.loc[list(group)]
            ax.plot(
                [group_ranks.min(), group_ranks.max()],
                [group_y, group_y],
                color="black",
                linewidth=4,
                solid_capstyle="butt",
            )

        cd_start = 1.0
        cd_end = min(len(methods), cd_start + critical_difference)
        ax.plot([cd_start, cd_end], [0.92, 0.92], c="black", linewidth=3)
        ax.text(
            (cd_start + cd_end) / 2,
            0.94,
            f"CD = {critical_difference:.2f}",
            ha="center",
            va="bottom",
        )

    fig.suptitle(f"Nemenyi critical-difference diagrams (alpha={alpha:g})")
    fig.tight_layout()
    return fig


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
        ("tts99_comparison.png", lambda: plot_tts99_comparison(results_df)),
    ]

    methods = ordered_methods(results_df)
    if len(methods) >= 2:
        figure_factories.extend(
            [
                ("winner_heatmap.png", lambda: plot_winner_heatmap(results_df)),
                (
                    "wall_time_scatter.png",
                    lambda: plot_wall_time_scatter(results_df, method_a=methods[0]),
                ),
            ]
        )
    if len(methods) >= 3:
        figure_factories.append(
            (
                "critical_difference_diagrams.png",
                lambda: plot_critical_difference_diagrams(results_df),
            )
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
    """Save solved-summary and applicable multi-method statistics tables."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    summary_path = output_dir / "solved_fraction_summary.csv"
    solved_fraction_summary(results_df, tolerance).to_csv(summary_path)
    saved_paths.append(summary_path)

    tts99_path = output_dir / "tts99_summary.csv"
    tts99_summary(results_df).to_csv(tts99_path, index=False)
    saved_paths.append(tts99_path)

    methods = ordered_methods(results_df)
    if len(methods) >= 2:
        wilcoxon_path = output_dir / "wilcoxon_by_budget.csv"
        pairwise_wilcoxon_by_budget(results_df).to_csv(wilcoxon_path, index=False)
        saved_paths.append(wilcoxon_path)

    if len(methods) >= 3:
        friedman_path = output_dir / "friedman_by_budget.csv"
        friedman_by_budget(results_df).to_csv(friedman_path, index=False)
        saved_paths.append(friedman_path)

        nemenyi_path = output_dir / "nemenyi_by_budget.csv"
        nemenyi_by_budget(results_df).to_csv(nemenyi_path, index=False)
        saved_paths.append(nemenyi_path)

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
