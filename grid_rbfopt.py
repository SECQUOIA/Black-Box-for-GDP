import csv
import os
import random
import time
import warnings
from contextlib import redirect_stdout
from math import isclose
from pathlib import Path

import numpy as np
import rbfopt

from instrumentation import (
    TrackedObjective,
    make_result_record,
    make_timestamped_results_dir,
    save_results_csv,
)

warnings.filterwarnings(
    "ignore",
    message="Signature .* for <class 'numpy.longdouble'> does not match any known type",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "benchmark_grids"
LOG_DIR = BASE_DIR / "logs"
RESULTS_DIR = BASE_DIR / "results"

PENALTY = 1e5


def load_grid(filename=DATA_DIR / "ackley.csv"):
    """
    Load grid data from CSV.
    Expected CSV columns include "Point", "x", "y", and "z_norm".
    The loader uses "x", "y", and "z_norm"; the "Point" column is retained in
    the CSV files for readability and traceability.
    Returns a dictionary mapping (x, y) tuples to the normalized objective value.
    """
    grid_data = {}
    with open(filename, "r", newline="") as f:
        reader = csv.DictReader(f)

        required_fields = {"x", "y", "z_norm"}
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"CSV file {filename} is missing a header row")

        missing_fields = required_fields.difference(fieldnames)
        if missing_fields:
            missing_list = ", ".join(sorted(missing_fields))
            raise ValueError(
                f"CSV file {filename} is missing required columns: {missing_list}"
            )

        for row_num, row in enumerate(reader, start=2):
            try:
                x_val = int(row["x"])
                y_val = int(row["y"])
                obj_val = float(row["z_norm"])
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Malformed row {row_num} in {filename}: {row}"
                ) from exc

            grid_data[(x_val, y_val)] = obj_val

    if not grid_data:
        raise ValueError(f"No valid grid points were loaded from {filename}")

    return grid_data


def grid_bounds(grid_data):
    """Derive the lower and upper bounds from the grid keys."""
    keys = list(grid_data.keys())
    xs = [k[0] for k in keys]
    ys = [k[1] for k in keys]
    return np.array([min(xs), min(ys)]), np.array([max(xs), max(ys)])


def make_obj_funct(grid_data):
    """
    Return an objective callback bound to *grid_data*.

    RBFOpt may supply coordinates as floats even for integer variables,
    so the callback rounds to the nearest lattice point before lookup.
    Points outside the grid receive a finite penalty.
    """

    def obj_funct(x):
        x_int = int(round(x[0]))
        y_int = int(round(x[1]))
        if (x_int, y_int) in grid_data:
            return grid_data[(x_int, y_int)]
        return PENALTY

    return obj_funct


def main():
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    max_eval_list = [10, 30, 50, 70, 100]
    # Number of independent RBFOpt runs per (CSV file, max_evaluations) setting
    n_repeats = 5

    log_dir = LOG_DIR
    os.makedirs(log_dir, exist_ok=True)

    seed = 0
    rng = random.Random(seed)
    starting_points = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(3)]
    print("Starting points:")
    for sp in starting_points:
        print(sp)

    coin_bin = os.environ.get("COIN_BIN", "").strip()
    if not coin_bin:
        raise ValueError(
            "Set the COIN_BIN environment variable to your AMPL/COIN solver "
            "binary directory before running grid_rbfopt.py"
        )

    coin_bin_path = Path(coin_bin)
    minlp_solver_path = coin_bin_path / "bonmin"
    nlp_solver_path = coin_bin_path / "ipopt"

    missing_paths = [p for p in (minlp_solver_path, nlp_solver_path) if not p.exists()]
    if missing_paths:
        missing_str = ", ".join(str(p) for p in missing_paths)
        raise FileNotFoundError(
            f"Missing solver executable(s): {missing_str}. "
            "Check that COIN_BIN points to the correct solver binary directory."
        )

    run_id = 0
    total_runs = len(csv_files) * len(max_eval_list) * n_repeats
    result_records = []
    results_dir = make_timestamped_results_dir(RESULTS_DIR, "rbfopt")
    results_path = results_dir / "rbfopt_results.csv"

    for max_eval in max_eval_list:
        for repeat in range(1, n_repeats + 1):
            for csv_name in csv_files:
                run_id += 1
                csv_label = Path(csv_name).stem
                log_file = (
                    log_dir
                    / f"run_{run_id:04d}__{csv_label}__E{max_eval}__R{repeat}.log"
                )

                with open(log_file, "w") as f, redirect_stdout(f):
                    print("===================================")
                    print(f"RUN: {run_id}/{total_runs}")
                    print("CSV:", Path(csv_name).name)
                    print("MAX_EVAL:", max_eval)
                    print("REPEAT:", repeat)
                    print("===================================")

                    grid_data = load_grid(csv_name)
                    obj_fn = make_obj_funct(grid_data)
                    tracked_obj_fn = TrackedObjective(obj_fn)
                    lb, ub = grid_bounds(grid_data)

                    print("Starting points used:")
                    for sp in starting_points:
                        print(sp)

                    init_node_pos = np.array(starting_points, dtype=float)

                    # 2 decision variables (x, y), both integer-valued
                    black_box = rbfopt.RbfoptUserBlackBox(
                        2, lb, ub, np.array(["I", "I"]), tracked_obj_fn
                    )

                    settings = rbfopt.RbfoptSettings(
                        max_evaluations=max_eval,
                        minlp_solver_path=str(minlp_solver_path),
                        nlp_solver_path=str(nlp_solver_path),
                        algorithm="MSRSM",
                        rbf="auto",
                        global_search_method="solver",
                    )

                    alg = rbfopt.RbfoptAlgorithm(
                        settings,
                        black_box,
                        init_node_pos=init_node_pos,
                        init_node_val=None,
                        do_init_strategy=False,
                    )

                    start = time.perf_counter()
                    best_val, best_point, itercount, evalcount, _fast_evalcount = (
                        alg.optimize()
                    )
                    end = time.perf_counter()
                    wall_time_s = end - start
                    best_point_rounded = [int(round(v)) for v in best_point]

                    result_record = make_result_record(
                        csv_name=Path(csv_name).name,
                        method="RBFOpt",
                        seed=seed,
                        n_starts=len(starting_points),
                        max_evals=max_eval,
                        best_value=best_val,
                        best_point=best_point_rounded,
                        total_evals=tracked_obj_fn.call_count,
                        wall_time_s=wall_time_s,
                        found_optimum=isclose(
                            best_val, 0.0, abs_tol=1e-12, rel_tol=0.0
                        ),
                        incumbent_trajectory=tracked_obj_fn.incumbent_trajectory,
                        initial_evals=len(starting_points),
                        adaptive_evals=max(
                            0, tracked_obj_fn.call_count - len(starting_points)
                        ),
                        unique_evals=tracked_obj_fn.unique_evaluation_count,
                        solver_evalcount=evalcount,
                        solver_iterations=itercount,
                    )
                    result_records.append(result_record)

                    print("Optimization completed.")
                    print("Best objective value found:", best_val)
                    print(
                        "At lattice point (rounded):",
                        best_point_rounded,
                    )
                    print("Iterations:", itercount, "Function evaluations:", evalcount)
                    print("Tracked objective evaluations:", tracked_obj_fn.call_count)
                    print("Runtime (seconds):", wall_time_s)
                    print("Result record:", result_record)

    print(f"All runs completed. Logs saved in: {log_dir}")
    save_results_csv(result_records, results_path)
    print(f"RBFOpt result records saved in: {results_path}")
    return result_records, results_path


if __name__ == "__main__":
    main()
