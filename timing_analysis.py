"""Completed-run time profiles and work/time tradeoffs for archived benchmarks.

The CSVs record total run time, not timestamps of incumbent improvements.
Successful runs therefore enter the profiles at their recorded completion time;
these plots must not be interpreted as measured first-hit-time profiles.
"""

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import tempfile
import zipfile

import numpy as np
import pandas as pd

from benchmark_analysis import (
    METHOD_COLORS,
    PRIMARY_TOLERANCE,
    configure_plot_style,
    load_analysis_dataset,
    ordered_method_names,
)
from case_study_analysis import CASE_DISPLAY_NAMES, CASE_ORDER, load_case_study_results


INSTANCE_COLUMNS = ["csv_name", "seed", "n_starts", "max_evals"]
CONFIG_COLUMNS = ["csv_name", "n_starts", "max_evals"]


def prepare_timing_data(results, tolerance=PRIMARY_TOLERANCE):
    """Assign unsuccessful runs infinite cost, retaining every paired instance.

    Success means a finite terminal objective within
    ``tolerance * max(1, abs(target))`` of the recorded optimum. The ratio is
    successful-run completion time divided by the fastest successful method's
    completion time on the same problem, seed, initialization and budget.
    All-failed instances retain infinite ratios and remain in the denominator.
    """
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and nonnegative")
    required = set(
        INSTANCE_COLUMNS
        + [
            "method",
            "best_value",
            "target_value",
            "wall_time_s",
            "total_evals",
        ]
    )
    missing = required.difference(results.columns)
    if missing:
        raise ValueError(f"Missing timing columns: {', '.join(sorted(missing))}")
    data = results.copy()
    if data.empty or data[INSTANCE_COLUMNS + ["method"]].isna().any().any():
        raise ValueError("Timing input must contain nonmissing run identifiers")
    if data.duplicated(INSTANCE_COLUMNS + ["method"]).any():
        raise ValueError("Duplicate timing run identifier")
    counts = data.groupby(INSTANCE_COLUMNS)["method"].nunique()
    if not (counts == data["method"].nunique()).all():
        raise ValueError("Timing profiles require the same methods for every instance")
    for column in ("wall_time_s", "total_evals", "target_value", "best_value"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    if not np.isfinite(data["wall_time_s"]).all() or (data["wall_time_s"] <= 0).any():
        raise ValueError("wall_time_s must be finite and strictly positive")
    if not np.isfinite(data["target_value"]).all():
        raise ValueError("target_value must be finite")
    if not np.isfinite(data["total_evals"]).all() or (data["total_evals"] < 0).any():
        raise ValueError("total_evals must be finite and nonnegative")
    scale = np.maximum(1.0, data["target_value"].abs())
    gap = data["best_value"] - data["target_value"]
    if (gap < -1e-10 * scale).any():
        raise ValueError("Objective below the recorded optimum; check input metadata")
    data["solved"] = np.isfinite(gap) & (gap.abs() <= tolerance * scale)
    data["tolerance"] = tolerance
    data["successful_run_time_s"] = data["wall_time_s"].where(data["solved"], math.inf)
    best = data.groupby(INSTANCE_COLUMNS)["successful_run_time_s"].transform("min")
    data["time_ratio"] = math.inf
    solved = data["solved"]
    data.loc[solved, "time_ratio"] = data.loc[solved, "wall_time_s"] / best[solved]
    if "solver_iterations" not in data:
        data["solver_iterations"] = math.nan
    data["solver_iterations"] = pd.to_numeric(data["solver_iterations"], errors="raise")
    iterations = data["solver_iterations"].dropna()
    if not np.isfinite(iterations).all() or (iterations < 0).any():
        raise ValueError("Reported solver_iterations must be finite and nonnegative")
    return data


def timing_summary(data, dataset):
    """Summarize all runs, including failures; iterations exclude missing reports."""
    groups = ["n_starts", "max_evals", "method"]
    if dataset == "case":
        groups = ["case_name", "problem_label", "csv_name", *groups]
    summary = data.groupby(groups, as_index=False, sort=False).agg(
        n_runs=("seed", "size"),
        solved_runs=("solved", "sum"),
        solved_fraction=("solved", "mean"),
        median_wall_time_s=("wall_time_s", "median"),
        q25_wall_time_s=("wall_time_s", lambda x: x.quantile(0.25)),
        q75_wall_time_s=("wall_time_s", lambda x: x.quantile(0.75)),
        median_total_evals=("total_evals", "median"),
        median_solver_iterations=("solver_iterations", "median"),
        solver_iteration_runs=("solver_iterations", "count"),
    )
    return summary


def _panels(data, dataset):
    if dataset == "grid":
        return [
            (f"Grid, B={budget}, starts={starts}", group)
            for (starts, budget), group in data.groupby(["n_starts", "max_evals"])
        ]
    panels = []
    for case in CASE_ORDER:
        selected = data[data["case_name"] == case]
        for (_, starts, budget), group in selected.groupby(CONFIG_COLUMNS, sort=False):
            label = group["problem_label"].iloc[0]
            panels.append((f"{label}, B={budget}, starts={starts}", group))
    return panels


def plot_time_profiles(data, dataset, relative=True):
    """Plot exact empirical steps on time ratios or seconds, including failures."""
    import matplotlib.pyplot as plt

    panels = _panels(data, dataset)
    columns = min(3, len(panels))
    rows = math.ceil(len(panels) / columns)
    fig, axes = plt.subplots(
        rows, columns, figsize=(4.8 * columns, 3.4 * rows + 0.8), squeeze=False
    )
    methods = ordered_method_names(data["method"])
    metric = "time_ratio" if relative else "successful_run_time_s"
    for axis, (title, panel) in zip(axes.flat, panels):
        finite = panel.loc[np.isfinite(panel[metric]), metric].to_numpy()
        left = 1.0 if relative else (float(finite.min()) * 0.8 if finite.size else 1e-3)
        right = max(left * 2, float(finite.max()) * 1.1) if finite.size else left * 10
        x = np.unique(np.r_[left, finite, right])
        denominator = len(panel[INSTANCE_COLUMNS].drop_duplicates())
        for method in methods:
            values = np.sort(panel.loc[panel["method"] == method, metric].to_numpy())
            fractions = np.searchsorted(values, x, side="right") / denominator
            axis.step(
                x,
                fractions,
                where="post",
                color=METHOD_COLORS.get(method),
                label=method,
                linewidth=2,
            )
        axis.set_xscale("log")
        axis.set_xlim(left, right)
        axis.set_ylim(0.0, 1.02)
        axis.set_title(f"{title}\n{denominator} paired instances", fontsize=10)
        axis.set_xlabel(
            "Completion-time ratio to fastest successful method"
            if relative
            else "Recorded run completion time (s)",
            fontsize=9,
        )
        axis.set_ylabel("Fraction of all instances solved")
    for axis in axes.flat[len(panels) :]:
        axis.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    height = fig.get_figheight()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=len(methods),
        bbox_to_anchor=(0.5, 1 - 0.35 / height),
    )
    title = (
        "Time performance profiles"
        if relative
        else "Successful completion versus wall time"
    )
    fig.suptitle(title, y=1 - 0.05 / height)
    tolerance = data["tolerance"].iloc[0]
    fig.text(
        0.5,
        0.08 / height,
        f"Tolerance = {tolerance:g} × max(1, |optimum|). Failures remain in the denominator.\n"
        "Uses full recorded run time; first-hit timestamps were not logged.",
        ha="center",
        va="bottom",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.65 / height, 1, 1 - 0.8 / height))
    return fig


def _place_budget_labels(axis, labels, renderer):
    """Offset nearby budget labels without moving or merging the observations."""
    from matplotlib.text import Text

    occupied = []
    bounds = axis.get_window_extent(renderer)
    for x, y, label, color in labels:
        annotation = axis.annotate(
            label,
            (x, y),
            xytext=(5, 6),
            textcoords="offset points",
            fontsize=7,
            color=color,
            arrowprops={"arrowstyle": "-", "color": color, "lw": 0.4},
        )
        placed = False
        for dx, alignment in ((5, "left"), (-5, "right"), (25, "left")):
            for dy in (6, 18, 30, 42, 54, -12, -24, -36, -48):
                annotation.set_position((dx, dy))
                annotation.set_ha(alignment)
                annotation.update_positions(renderer)
                box = Text.get_window_extent(annotation, renderer).expanded(1.05, 1.2)
                inside = bounds.contains(box.x0, box.y0) and bounds.contains(
                    box.x1, box.y1
                )
                if inside and not any(box.overlaps(other) for other in occupied):
                    occupied.append(box)
                    placed = True
                    break
            if placed:
                break


def plot_time_work_tradeoff(summary, dataset):
    """Show median recorded time versus evaluations and method-specific iterations.

    Marker area indicates terminal success fraction, so low-cost failed runs
    cannot be mistaken for dominant solutions. Lines connect configurations,
    not within-run trajectories. Every seed (successful or not) enters medians.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    groups = (
        [("Grid (pooled over problems and seeds)", summary)]
        if dataset == "grid"
        else [
            (CASE_DISPLAY_NAMES[case], summary[summary["case_name"] == case])
            for case in CASE_ORDER
            if (summary["case_name"] == case).any()
        ]
    )
    fig, axes = plt.subplots(
        len(groups), 2, figsize=(13, 3.7 * len(groups) + 1.0), squeeze=False
    )
    methods = ordered_method_names(summary["method"])
    metrics = [
        ("median_total_evals", "Median total function evaluations"),
        ("median_solver_iterations", "Median reported solver iterations*"),
    ]
    labels_by_axis = []
    for row, (title, panel) in enumerate(groups):
        for column, (metric, label) in enumerate(metrics):
            axis = axes[row, column]
            budget_labels = []
            for method in methods:
                for _, points in panel[panel["method"] == method].groupby("n_starts"):
                    points = points.sort_values("max_evals")
                    points = points[points[metric].notna()]
                    if points.empty:
                        continue
                    color = METHOD_COLORS.get(method)
                    axis.plot(
                        points[metric],
                        points["median_wall_time_s"],
                        color=color,
                        linewidth=1,
                        alpha=0.6,
                    )
                    axis.scatter(
                        points[metric],
                        points["median_wall_time_s"],
                        s=35 + 130 * points["solved_fraction"],
                        color=color,
                        edgecolor="white",
                        linewidth=0.7,
                        zorder=3,
                    )
                    for point in points.itertuples(index=False):
                        annotation = f"B{point.max_evals}"
                        if panel["n_starts"].nunique() > 1:
                            annotation += f" / S{point.n_starts}"
                        budget_labels.append(
                            (
                                getattr(point, metric),
                                point.median_wall_time_s,
                                annotation,
                                color,
                            )
                        )
            axis.set_yscale("log")
            axis.margins(x=0.15, y=0.25)
            axis.set_xlim(left=0.0)
            axis.set_xlabel(label)
            axis.set_ylabel("Median recorded run time (s)")
            axis.set_title(title)
            if not axis.lines:
                axis.text(
                    0.5,
                    0.5,
                    "No iteration counts reported",
                    ha="center",
                    transform=axis.transAxes,
                )
            elif metric == "median_solver_iterations":
                missing_methods = [
                    m
                    for m in methods
                    if panel.loc[panel["method"] == m, metric].isna().all()
                ]
                if missing_methods:
                    axis.text(
                        0.98,
                        0.03,
                        f"{', '.join(missing_methods)}: iterations not recorded",
                        ha="right",
                        va="bottom",
                        fontsize=8,
                        transform=axis.transAxes,
                    )
            labels_by_axis.append((axis, budget_labels))
    handles = [
        Line2D([], [], color=METHOD_COLORS.get(m), marker="o", label=m) for m in methods
    ]
    handles += [
        Line2D(
            [],
            [],
            color="none",
            marker="o",
            markerfacecolor="gray",
            markersize=math.sqrt(35 + 130 * fraction),
            label=f"{fraction:.0%} solved",
        )
        for fraction in (0, 0.5, 1)
    ]
    height = fig.get_figheight()
    fig.legend(
        handles=handles,
        loc="upper center",
        ncol=len(handles),
        bbox_to_anchor=(0.5, 1 - 0.35 / height),
    )
    fig.suptitle(
        "Time / work tradeoff at the tested evaluation budgets", y=1 - 0.05 / height
    )
    fig.text(
        0.5,
        0.08 / height,
        "B = evaluation budget; marker area = solved fraction. Medians include unsuccessful runs.\n"
        "* Solver iterations are method-specific and not directly comparable. "
        "Lines connect budgets, not trajectories.",
        ha="center",
        va="bottom",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.65 / height, 1, 1 - 0.8 / height))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for axis, labels in labels_by_axis:
        _place_budget_labels(axis, labels, renderer)
    return fig


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_input(dataset, results_csv, archive, grids_dir):
    loader = (
        load_case_study_results
        if dataset == "case"
        else (lambda path: load_analysis_dataset(path, grids_dir=grids_dir)[0])
    )
    if archive is None:
        results_csv = Path(results_csv)
        data = loader(results_csv)
        return data, {"csv": str(results_csv), "csv_sha256": _sha256(results_csv)}
    archive = Path(archive)
    basename = "process_case_studies.csv" if dataset == "case" else "benchmark.csv"
    with zipfile.ZipFile(archive) as source, tempfile.TemporaryDirectory() as temp:
        members = [name for name in source.namelist() if Path(name).name == basename]
        if len(members) != 1:
            raise ValueError(f"Expected exactly one {basename} in archive")
        member = members[0]
        path = Path(temp) / basename
        path.write_bytes(source.read(member))
        if dataset == "case":
            manifest_member = str(Path(member).with_suffix(".manifest.json"))
            path.with_suffix(".manifest.json").write_bytes(source.read(manifest_member))
        data = loader(path)
        provenance = {
            "archive": str(archive),
            "archive_sha256": _sha256(archive),
            "csv_member": member,
            "csv_sha256": _sha256(path),
        }
    return data, provenance


def create_timing_outputs(
    dataset,
    output_dir,
    results_csv=None,
    archive=None,
    grids_dir="benchmark_grids",
    tolerance=PRIMARY_TOLERANCE,
    dpi=200,
):
    """Read audited result files or a ZIP directly; save plots and their source tables."""
    if dataset not in {"grid", "case"}:
        raise ValueError("dataset must be grid or case")
    if (results_csv is None) == (archive is None):
        raise ValueError("Provide exactly one of results_csv and archive")
    results, provenance = _load_input(dataset, results_csv, archive, grids_dir)
    data = prepare_timing_data(results, tolerance)
    summary = timing_summary(data, dataset)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    columns = INSTANCE_COLUMNS + [
        "method",
        "target_value",
        "best_value",
        "tolerance",
        "solved",
        "wall_time_s",
        "successful_run_time_s",
        "time_ratio",
    ]
    data[columns].to_csv(output_dir / "time_profile_runs.csv", index=False)
    summary.to_csv(output_dir / "time_work_summary.csv", index=False)
    configure_plot_style()
    import matplotlib.pyplot as plt

    factories = {
        "time_performance_profiles.png": lambda: plot_time_profiles(data, dataset),
        "completion_time_profiles.png": lambda: plot_time_profiles(
            data, dataset, relative=False
        ),
        "time_work_tradeoff.png": lambda: plot_time_work_tradeoff(summary, dataset),
    }
    for name, factory in factories.items():
        figure = factory()
        figure.savefig(output_dir / name, dpi=dpi, bbox_inches="tight")
        plt.close(figure)
    source_dir = Path(__file__).resolve().parent
    provenance.update(
        {
            "dataset": dataset,
            "n_runs": len(data),
            "tolerance": tolerance,
            "success_rule": "abs(best_value - target_value) <= tolerance * max(1, abs(target_value))",
            "time_measure": "recorded full run time, conditional on terminal success; failures have infinite cost",
            "first_hit_timestamps_available": False,
            "source_sha256": {
                name: _sha256(source_dir / name)
                for name in (
                    "timing_analysis.py",
                    "benchmark_analysis.py",
                    "case_study_analysis.py",
                )
            },
            "python": platform.python_version(),
            "packages": {
                name: importlib.metadata.version(name)
                for name in ("numpy", "pandas", "matplotlib", "scipy")
            },
        }
    )
    if dataset == "grid":
        provenance["grid_sha256"] = {
            name: _sha256(Path(grids_dir) / name)
            for name in sorted(data["csv_name"].unique())
        }
    else:
        validation = results.attrs["input_validation"]
        provenance["input_validation"] = {
            "verified": validation["verified"],
            "warning": validation["warning"],
            "manifest_filename": validation["manifest_path"].name,
        }
    (output_dir / "timing_analysis.manifest.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return {"data": data, "summary": summary, "output_dir": output_dir}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("grid", "case"), required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--results-csv", type=Path)
    source.add_argument("--archive", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--grids-dir", type=Path, default=Path("benchmark_grids"))
    parser.add_argument("--tolerance", type=float, default=PRIMARY_TOLERANCE)
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args(argv)
    outputs = create_timing_outputs(**vars(args))
    print(
        f"Analyzed {len(outputs['data'])} runs; saved outputs to {outputs['output_dir']}"
    )
    return outputs


if __name__ == "__main__":
    main()
