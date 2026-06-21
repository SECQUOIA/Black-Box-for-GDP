"""Automated DSDA vs RBFOpt benchmark runner for packaged grid CSVs."""

import argparse
import math
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from case_studies.common import generate_lhc_starting_points
from grid_dsda import load_grid_csv, run_dsda_from_best_starting_points
from instrumentation import TrackedObjective, make_result_record, save_results_csv


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_GRIDS_DIR = BASE_DIR / "benchmark_grids"
DEFAULT_RESULTS_DIR = BASE_DIR / "results"
DEFAULT_METHODS = ("dsda", "rbfopt")
DEFAULT_MAX_EVALS = (10, 30, 50, 70, 100)
PENALTY = 1e5


def parse_int_sequence(value):
    """Parse comma-separated integers and inclusive ranges, e.g. ``0-2,5``."""
    values = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(
                    f"Invalid integer range: {chunk}"
                ) from exc
            if end < start:
                raise argparse.ArgumentTypeError(
                    f"Range end must be greater than or equal to start: {chunk}"
                )
            values.extend(range(start, end + 1))
        else:
            try:
                values.append(int(chunk))
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"Invalid integer: {chunk}") from exc

    if not values:
        raise argparse.ArgumentTypeError("At least one integer value is required")
    return values


def parse_methods(value):
    """Parse and validate a comma-separated method list."""
    methods = tuple(method.strip().lower() for method in str(value).split(","))
    methods = tuple(method for method in methods if method)
    if not methods:
        raise argparse.ArgumentTypeError("At least one method is required")

    allowed = set(DEFAULT_METHODS)
    invalid = sorted(set(methods).difference(allowed))
    if invalid:
        invalid_text = ", ".join(invalid)
        allowed_text = ", ".join(DEFAULT_METHODS)
        raise argparse.ArgumentTypeError(
            f"Unsupported method(s): {invalid_text}. Choose from: {allowed_text}"
        )
    return methods


def normalize_methods(methods):
    """Normalize methods supplied by the CLI or direct Python callers."""
    if isinstance(methods, str):
        return parse_methods(methods)
    return parse_methods(",".join(str(method) for method in methods))


def normalize_int_sequence(values, name):
    """Normalize integer sequences supplied as strings or iterables."""
    if isinstance(values, str):
        return parse_int_sequence(values)

    normalized = list(values)
    if not normalized:
        raise ValueError(f"{name} must include at least one value")
    return normalized


def prepend_solver_dir_to_path(solver_dir):
    """Prepend a solver directory to PATH if it is not already present."""
    solver_dir = str(Path(solver_dir))
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if solver_dir not in path_entries:
        os.environ["PATH"] = os.pathsep.join([solver_dir, *path_entries])


def resolve_solver_paths(
    solver_dir=None,
    minlp_solver_path="",
    nlp_solver_path="",
):
    """
    Resolve BONMIN and IPOPT executable paths for RBFOpt.

    Explicit solver paths win. Otherwise ``solver_dir`` is used, followed by
    ``COIN_BIN`` when it is set. Empty paths are returned when no solver
    location is configured, allowing RBFOpt to use its own defaults or tests to
    inject a fake RBFOpt module.
    """
    if minlp_solver_path and nlp_solver_path:
        return str(minlp_solver_path), str(nlp_solver_path)

    if solver_dir is None:
        solver_dir = os.environ.get("COIN_BIN", "").strip()
    elif isinstance(solver_dir, str):
        solver_dir = solver_dir.strip()

    if not solver_dir:
        return str(minlp_solver_path), str(nlp_solver_path)

    solver_path = Path(solver_dir)
    prepend_solver_dir_to_path(solver_path)
    resolved_minlp = (
        Path(minlp_solver_path) if minlp_solver_path else solver_path / "bonmin"
    )
    resolved_nlp = Path(nlp_solver_path) if nlp_solver_path else solver_path / "ipopt"

    missing_paths = [
        path for path in (resolved_minlp, resolved_nlp) if not path.exists()
    ]
    if missing_paths:
        missing_text = ", ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(
            f"Missing solver executable(s): {missing_text}. "
            "Pass --solver-dir pointing to the directory containing bonmin and ipopt."
        )

    return str(resolved_minlp), str(resolved_nlp)


def resolve_required_solver_paths(
    solver_dir=None,
    minlp_solver_path="",
    nlp_solver_path="",
):
    """Resolve both executables required by RBFOpt's solver search mode."""
    minlp_solver_path, nlp_solver_path = resolve_solver_paths(
        solver_dir=solver_dir,
        minlp_solver_path=minlp_solver_path,
        nlp_solver_path=nlp_solver_path,
    )

    def find_executable(configured_path, command):
        if configured_path and Path(configured_path).is_file():
            return str(configured_path)
        return shutil.which(str(configured_path or command)) or ""

    minlp_solver_path = find_executable(minlp_solver_path, "bonmin")
    nlp_solver_path = find_executable(nlp_solver_path, "ipopt")

    missing = []
    if not minlp_solver_path:
        missing.append("BONMIN")
    if not nlp_solver_path:
        missing.append("IPOPT")
    if missing:
        missing_text = " and ".join(missing)
        raise FileNotFoundError(
            f"RBFOpt solver mode requires {missing_text}. Set COIN_BIN, pass "
            "--solver-dir or explicit solver paths, ensure the executables are "
            "on PATH, or choose a solver-free --global-search-method."
        )

    return minlp_solver_path, nlp_solver_path


def grid_bounds(grid):
    """Derive integer lower and upper bounds from a grid mapping."""
    if not grid:
        raise ValueError("Cannot derive bounds from an empty grid")

    n_dims = len(next(iter(grid)))
    lower_bounds = []
    upper_bounds = []
    for dim in range(n_dims):
        coordinates = [point[dim] for point in grid]
        lower_bounds.append(min(coordinates))
        upper_bounds.append(max(coordinates))
    return np.asarray(lower_bounds), np.asarray(upper_bounds)


def validate_full_lattice(grid, lower_bounds, upper_bounds, grid_name):
    """Require every integer point within the grid bounds to be present."""
    axis_sizes = [
        int(upper) - int(lower) + 1
        for lower, upper in zip(lower_bounds, upper_bounds)
    ]
    expected_points = math.prod(axis_sizes)
    if len(grid) != expected_points:
        raise ValueError(
            f"Benchmark grid {grid_name} must contain a complete integer lattice; "
            f"found {len(grid)} points, expected {expected_points} within its bounds"
        )


def make_grid_objective(grid, penalty=PENALTY):
    """Create an RBFOpt-compatible grid objective with an out-of-grid penalty."""

    def objective(point):
        lattice_point = tuple(int(round(value)) for value in point)
        return grid.get(lattice_point, penalty)

    return objective


def benchmark_output_path(output, now=None):
    """Return the CSV output path for a benchmark run."""
    output = Path(output)
    if output.suffix.lower() == ".csv":
        return output

    now = now or datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
    return output / f"benchmark_{timestamp}.csv"


def discover_grid_paths(grids_dir):
    """Return sorted benchmark CSV paths from a directory."""
    grids_dir = Path(grids_dir)
    csv_paths = sorted(grids_dir.glob("*.csv"))
    if not csv_paths:
        raise ValueError(f"No benchmark CSV files found in {grids_dir}")
    return csv_paths


def run_dsda_benchmark_case(
    csv_path,
    starting_points,
    seed,
    n_starts,
    max_evals,
    target_value,
    diagonal=True,
    tie_break="first",
    verbose=False,
):
    """Run one DSDA benchmark case and return its unified result record."""
    result = run_dsda_from_best_starting_points(
        csv_path=str(csv_path),
        starting_points=starting_points,
        diagonal=diagonal,
        maximize=False,
        tie_break=tie_break,
        target_value=target_value,
        verbose=verbose,
        max_points_explored=max_evals,
    )
    record = dict(result["result_record"])
    record.update(
        {
            "seed": seed,
            "n_starts": n_starts,
            "max_evals": max_evals,
            "found_optimum": math.isclose(
                record["best_value"], target_value, abs_tol=1e-12, rel_tol=0.0
            ),
        }
    )
    result["result_record"] = record
    return result


def run_rbfopt_benchmark_case(
    csv_path,
    grid,
    lower_bounds,
    upper_bounds,
    starting_points,
    seed,
    n_starts,
    max_evals,
    target_value,
    solver_dir=None,
    minlp_solver_path="",
    nlp_solver_path="",
    algorithm="MSRSM",
    rbf="auto",
    global_search_method="solver",
    rbfopt_module=None,
):
    """Run one RBFOpt benchmark case and return its unified result record."""
    if rbfopt_module is None:
        import rbfopt as rbfopt_module

    explicit_solver_config = (
        bool(minlp_solver_path)
        or bool(nlp_solver_path)
        or (solver_dir is not None and str(solver_dir).strip() != "")
    )
    if global_search_method == "solver":
        minlp_solver_path, nlp_solver_path = resolve_required_solver_paths(
            solver_dir=solver_dir,
            minlp_solver_path=minlp_solver_path,
            nlp_solver_path=nlp_solver_path,
        )
    elif explicit_solver_config:
        minlp_solver_path, nlp_solver_path = resolve_solver_paths(
            solver_dir=solver_dir,
            minlp_solver_path=minlp_solver_path,
            nlp_solver_path=nlp_solver_path,
        )

    n_dims = len(lower_bounds)
    init_node_pos = np.asarray(starting_points, dtype=float)
    tracked_objective = TrackedObjective(make_grid_objective(grid))
    black_box = rbfopt_module.RbfoptUserBlackBox(
        n_dims,
        lower_bounds,
        upper_bounds,
        np.asarray(["I"] * n_dims),
        tracked_objective,
    )
    settings = rbfopt_module.RbfoptSettings(
        max_evaluations=max_evals,
        minlp_solver_path=minlp_solver_path,
        nlp_solver_path=nlp_solver_path,
        algorithm=algorithm,
        rbf=rbf,
        global_search_method=global_search_method,
    )
    algorithm_instance = rbfopt_module.RbfoptAlgorithm(
        settings,
        black_box,
        init_node_pos=init_node_pos,
        init_node_val=None,
        do_init_strategy=False,
    )

    start_time = time.perf_counter()
    best_value, best_point, itercount, evalcount, fast_evalcount = (
        algorithm_instance.optimize()
    )
    wall_time_s = time.perf_counter() - start_time
    best_point_rounded = [int(round(value)) for value in best_point]

    result_record = make_result_record(
        csv_name=Path(csv_path).name,
        method="RBFOpt",
        seed=seed,
        n_starts=n_starts,
        max_evals=max_evals,
        best_value=best_value,
        best_point=best_point_rounded,
        total_evals=tracked_objective.call_count,
        wall_time_s=wall_time_s,
        found_optimum=math.isclose(
            best_value, target_value, abs_tol=1e-12, rel_tol=0.0
        ),
        incumbent_trajectory=tracked_objective.incumbent_trajectory,
    )
    return {
        "csv_name": Path(csv_path).name,
        "starting_points": starting_points,
        "best_value": best_value,
        "best_point": best_point_rounded,
        "iterations": itercount,
        "evalcount": evalcount,
        "fast_evalcount": fast_evalcount,
        "tracked_evals": tracked_objective.call_count,
        "wall_time_s": wall_time_s,
        "incumbent_trajectory": tracked_objective.incumbent_trajectory,
        "objective_wall_times": tracked_objective.wall_times,
        "minlp_solver_path": minlp_solver_path,
        "nlp_solver_path": nlp_solver_path,
        "result_record": result_record,
    }


def run_benchmark(
    methods=DEFAULT_METHODS,
    seeds=range(10),
    n_starts=3,
    max_evals=DEFAULT_MAX_EVALS,
    grids_dir=DEFAULT_GRIDS_DIR,
    output=DEFAULT_RESULTS_DIR,
    solver_dir=None,
    minlp_solver_path="",
    nlp_solver_path="",
    algorithm="MSRSM",
    rbf="auto",
    global_search_method="solver",
    diagonal=True,
    tie_break="first",
    verbose=False,
    rbfopt_module=None,
):
    """Run the full benchmark matrix and write unified results to CSV."""
    methods = normalize_methods(methods)
    seeds = normalize_int_sequence(seeds, "seeds")
    max_evals = normalize_int_sequence(max_evals, "max_evals")
    if n_starts < 1:
        raise ValueError("n_starts must be at least 1")
    if any(max_eval < 1 for max_eval in max_evals):
        raise ValueError("max_evals values must be at least 1")
    if any(max_eval < n_starts for max_eval in max_evals):
        raise ValueError(
            "max_evals values must be greater than or equal to n_starts so "
            "all shared initial LHC points fit inside the evaluation budget"
        )

    csv_paths = discover_grid_paths(grids_dir)
    results_path = benchmark_output_path(output)
    result_records = []

    for csv_path in csv_paths:
        _, grid = load_grid_csv(csv_path)
        lower_bounds, upper_bounds = grid_bounds(grid)
        validate_full_lattice(grid, lower_bounds, upper_bounds, csv_path.name)
        target_value = min(grid.values())

        for seed in seeds:
            starting_points = generate_lhc_starting_points(
                n_dims=len(lower_bounds),
                n_points=n_starts,
                lb=lower_bounds,
                ub=upper_bounds,
                seed=seed,
            )

            for max_eval in max_evals:
                if "dsda" in methods:
                    dsda_result = run_dsda_benchmark_case(
                        csv_path=csv_path,
                        starting_points=starting_points,
                        seed=seed,
                        n_starts=n_starts,
                        max_evals=max_eval,
                        target_value=target_value,
                        diagonal=diagonal,
                        tie_break=tie_break,
                        verbose=verbose,
                    )
                    result_records.append(dsda_result["result_record"])

                if "rbfopt" in methods:
                    rbfopt_result = run_rbfopt_benchmark_case(
                        csv_path=csv_path,
                        grid=grid,
                        lower_bounds=lower_bounds,
                        upper_bounds=upper_bounds,
                        starting_points=starting_points,
                        seed=seed,
                        n_starts=n_starts,
                        max_evals=max_eval,
                        target_value=target_value,
                        solver_dir=solver_dir,
                        minlp_solver_path=minlp_solver_path,
                        nlp_solver_path=nlp_solver_path,
                        algorithm=algorithm,
                        rbf=rbf,
                        global_search_method=global_search_method,
                        rbfopt_module=rbfopt_module,
                    )
                    result_records.append(rbfopt_result["result_record"])

    save_results_csv(result_records, results_path)
    return result_records, results_path


def build_parser():
    """Build the benchmark CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methods", type=parse_methods, default=DEFAULT_METHODS)
    parser.add_argument("--seeds", type=parse_int_sequence, default=list(range(10)))
    parser.add_argument("--n-starts", type=int, default=3)
    parser.add_argument(
        "--max-evals",
        type=parse_int_sequence,
        default=list(DEFAULT_MAX_EVALS),
    )
    parser.add_argument("--grids-dir", type=Path, default=DEFAULT_GRIDS_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Output directory or explicit CSV path.",
    )
    parser.add_argument(
        "--solver-dir",
        default=None,
        help="Directory containing bonmin and ipopt. Defaults to COIN_BIN.",
    )
    parser.add_argument("--minlp-solver-path", default="")
    parser.add_argument("--nlp-solver-path", default="")
    parser.add_argument("--algorithm", default="MSRSM")
    parser.add_argument("--rbf", default="auto")
    parser.add_argument("--global-search-method", default="solver")
    parser.add_argument("--tie-break", default="first")
    parser.add_argument("--no-diagonal", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv=None, rbfopt_module=None):
    """CLI entry point for the benchmark runner."""
    args = build_parser().parse_args(argv)
    result_records, results_path = run_benchmark(
        methods=args.methods,
        seeds=args.seeds,
        n_starts=args.n_starts,
        max_evals=args.max_evals,
        grids_dir=args.grids_dir,
        output=args.output,
        solver_dir=args.solver_dir,
        minlp_solver_path=args.minlp_solver_path,
        nlp_solver_path=args.nlp_solver_path,
        algorithm=args.algorithm,
        rbf=args.rbf,
        global_search_method=args.global_search_method,
        diagonal=not args.no_diagonal,
        tie_break=args.tie_break,
        verbose=args.verbose,
        rbfopt_module=rbfopt_module,
    )
    print(f"Benchmark completed: {len(result_records)} runs")
    print(f"Results saved in: {results_path}")
    return result_records, results_path


if __name__ == "__main__":
    main()
