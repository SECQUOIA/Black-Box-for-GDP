import csv
import os
import random
import time
import warnings
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import rbfopt

warnings.filterwarnings(
    "ignore",
    message="Signature .* for <class 'numpy.longdouble'> does not match any known type"
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "qhdopt"
LOG_DIR = BASE_DIR / "logs"


# =============================
# LIST OF QHDOPT CSV FILES
# =============================
csv_files = [
    DATA_DIR / "hosaki.csv",
    DATA_DIR / "levy.csv",
    DATA_DIR / "levy13.csv",
    DATA_DIR / "michalewicz.csv",
    DATA_DIR / "rastrigin.csv",
    DATA_DIR / "rosenbrock.csv",
    DATA_DIR / "shubert.csv",
    DATA_DIR / "styblinski_tang.csv",
    DATA_DIR / "sum_of_squares.csv",
    DATA_DIR / "xin_she_yang3.csv",
    DATA_DIR / "alpine1.csv",
    DATA_DIR / "alpine2.csv",
    DATA_DIR / "bohachevsky2.csv",
    DATA_DIR / "camel3.csv",
    DATA_DIR / "csendes.csv",
    DATA_DIR / "deflected_corrugated_spring.csv",
    DATA_DIR / "dropwave.csv",
    DATA_DIR / "easom.csv",
    DATA_DIR / "griewank.csv",
    DATA_DIR / "holder_table.csv",
    DATA_DIR / "ackley.csv",
]

max_eval_list = [10, 30, 50, 70, 100]
# max_eval_list = [100]
n_repeats = 5

# =============================
# OUTPUT FOLDER FOR LOGS
# =============================
log_dir = LOG_DIR
os.makedirs(log_dir, exist_ok=True)


def load_grid(filename=DATA_DIR / "ackley.csv"):
    """
    Load grid data from CSV.
    Expected CSV columns include "Point", "x", "y", and "z_norm".
    The loader uses "x", "y", and "z_norm"; the "Point" column is retained in
    the CSV files for readability and traceability.
    Returns a dictionary mapping (x, y) tuples to the normalized objective value.
    """
    grid_data = {}
    with open(filename, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                x_val = int(row["x"])
                y_val = int(row["y"])
                obj_val = float(row["z_norm"])
                grid_data[(x_val, y_val)] = obj_val
            except Exception:
                continue
    return grid_data


# Load the data from a default grid; overwritten inside batch loops.
grid_data = load_grid()

PENALTY = 1e5  # adjust this penalty as appropriate
# PENALTY = np.inf  # use infinity as penalty for infeasible points
# PENALTY = np.nan  # use NaN as penalty for infeasible points
# PENALTY = None  # use None as penalty for infeasible points

rng = random.Random(0)
starting_points = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(3)]
print("Starting points:")
for sp in starting_points:
    print(sp)


def obj_funct(x):
    """
    Given a candidate point x (a list or 1-D numpy array with 2 elements),
    this function rounds x to the nearest integers and returns the objective value
    if the point exists in grid_data. Otherwise, returns a penalty value.
    """
    x_int = int(round(x[0]))
    y_int = int(round(x[1]))

    if (x_int, y_int) in grid_data:
        return grid_data[(x_int, y_int)]
    return PENALTY


# =============================
# BATCH RUNS: 21 files x 5 max_evals x 5 repeats = 525 runs
# =============================
def main():
    global grid_data

    run_id = 0
    total_runs = len(csv_files) * len(max_eval_list) * n_repeats

    # Set COIN_BIN to your local AMPL/COIN solver binaries directory
    # before running with solver-based global search.
    coin_bin = os.environ.get("COIN_BIN", "").strip()
    if not coin_bin:
        raise ValueError(
            "Set the COIN_BIN environment variable to your AMPL/COIN solver "
            "binary directory before running qhdopt_rbfopt.py"
        )

    minlp_solver_path = f"{coin_bin}/bonmin"
    nlp_solver_path = f"{coin_bin}/ipopt"

    for max_eval in max_eval_list:
        for repeat in range(1, n_repeats + 1):
            for csv_name in csv_files:
                run_id += 1
                csv_label = Path(csv_name).stem
                log_file = log_dir / f"run_{run_id:04d}__{csv_label}__E{max_eval}__R{repeat}.log"

                with open(log_file, "w") as f, redirect_stdout(f):
                    print("===================================")
                    print(f"RUN: {run_id}/{total_runs}")
                    print("CSV:", Path(csv_name).name)
                    print("MAX_EVAL:", max_eval)
                    print("REPEAT:", repeat)
                    print("===================================")

                    grid_data = load_grid(csv_name)

                    print("Starting points used:")
                    for sp in starting_points:
                        print(sp)

                    init_node_pos = np.array(starting_points, dtype=float)

                    black_box = rbfopt.RbfoptUserBlackBox(
                        2,
                        np.array([0, 0]),
                        np.array([30, 30]),
                        np.array(["I", "I"]),
                        obj_funct,
                    )

                    settings = rbfopt.RbfoptSettings(
                        max_evaluations=max_eval,
                        minlp_solver_path=minlp_solver_path,
                        nlp_solver_path=nlp_solver_path,
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

                    start = time.time()
                    best_val, best_point, itercount, evalcount, fast_evalcount = alg.optimize()
                    end = time.time()

                    print("Optimization completed.")
                    print("Best objective value found:", best_val)
                    print("At lattice point (rounded):", [int(round(v)) for v in best_point])
                    print("Iterations:", itercount, "Function evaluations:", evalcount)
                    print("Runtime (seconds):", end - start)

    print(f"All runs completed. Logs saved in: {log_dir}")


if __name__ == "__main__":
    main()
