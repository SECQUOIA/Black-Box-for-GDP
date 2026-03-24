"""
CSV-driven pseudo-LDSDA experiments for the QHDOpt benchmark grids.

This module loads normalized benchmark grids from `qhdopt/*.csv` and runs a
discrete local-descent search that mimics the main structure of LDSDA on a
sampled lattice. It does not build Pyomo GDP models, and it does not implement
the full LDSDA solver.

The benchmark grids used here are derived from benchmark examples listed on:
https://jiaqileng.github.io/quantum-hamiltonian-descent/nonconvex2d.html

Although the filename is retained from an earlier GDP-oriented version, the
current implementation operates directly on precomputed CSV grids.
"""

import pandas as pd
import random
from math import isclose, sqrt


def load_grid_csv(csv_path):
    """
    Load a normalized 2D benchmark grid from CSV.

    Required columns:
        - x
        - y
        - z_norm

    Returns
    -------
    df : pandas.DataFrame
    grid : dict
        grid[(x, y)] = z_norm
    """
    df = pd.read_csv(csv_path)

    required_cols = {"x", "y", "z_norm"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    df["x"] = df["x"].astype(int)
    df["y"] = df["y"].astype(int)

    grid = {
        (int(row.x), int(row.y)): float(row.z_norm)
        for row in df.itertuples(index=False)
    }
    return df, grid


def get_neighbors(point, grid, diagonal=False):
    """
    Return valid neighbors of a grid point.

    Parameters
    ----------
    point : tuple
        (x, y)
    grid : dict
        grid[(x, y)] = z
    diagonal : bool
        If True, use 8-neighborhood, L-infinity.
        If False, use 4-neighborhood, L-2.
    """
    x, y = point

    if diagonal:
        directions = [
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
            (-1, -1),
            (-1, 1),
            (1, -1),
            (1, 1),
        ]
    else:
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    neighbors = []
    for dx, dy in directions:
        candidate = (x + dx, y + dy)
        if candidate in grid:
            neighbors.append(candidate)

    return neighbors


def ldsda_from_csv(
    csv_path,
    start_point,
    diagonal=False,
    maximize=False,
    tol=1e-12,
    tie_break="first",
    verbose=True,
):
    """
    Pseudo-LDSDA search on a 2D discrete grid loaded from CSV.

    Procedure
    ---------
    1. Perform neighbor search around the current point.
    2. Choose the best improving neighbor.
    3. Define the search direction from the current point to that neighbor.
    4. Perform line search along that direction until the next point is worse
       (or out of bounds).
    5. Restart neighbor search from the last improving point.

    Parameters
    ----------
    csv_path : str
        Path to CSV file.
    start_point : tuple
        Initial point as (x, y).
    diagonal : bool, optional
        If True, use 8-neighborhood. Otherwise 4-neighborhood.
    maximize : bool, optional
        If True, maximize z_norm. Otherwise minimize.
    tol : float, optional
        Improvement tolerance.
    tie_break : str, optional
        How to break ties between equally good improving neighbors.
        Options:
            - "first"
            - "nearest"
            - "farthest"
    verbose : bool, optional
        Print iteration log.

    Returns
    -------
    result : dict
        {
            "start_point": ...,
            "start_value": ...,
            "best_point": ...,
            "best_value": ...,
            "major_iterations": ...,
            "points_explored": ...,
            "unique_explored_points": [...],
            "path": [...],
            "history": [...],
            "explored_points": [...]
        }
    """
    _, grid = load_grid_csv(csv_path)

    start_point = tuple(start_point)
    if start_point not in grid:
        raise ValueError(f"Start point {start_point} is not in the grid.")

    def better(new_val, current_val):
        if maximize:
            return new_val > current_val + tol
        return new_val < current_val - tol

    def equal_obj(a, b):
        return isclose(a, b, abs_tol=tol, rel_tol=0.0)

    def move_distance(p1, p2):
        return sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    current = start_point
    current_val = grid[current]

    path = [current]

    major_iter = 0
    unique_explored_points = set()
    explored_points = []

    # Include the start point as an evaluated point
    unique_explored_points.add(current)
    explored_points.append((current, current_val, "start_point", 0))

    history = [
        {
            "major_iter": 0,
            "base_point": current,
            "base_value": current_val,
            "neighbor_points": [],
            "line_search_points": [],
            "unique_points_explored_so_far": 1,
        }
    ]

    if verbose:
        print(f"Start | point={current} | z_norm={current_val:.12f}")
        print("Unique points explored so far: 1")

    while True:
        major_iter += 1

        # 1. Neighbor search
        neighbors = get_neighbors(current, grid, diagonal=diagonal)

        neighbor_points = []
        improving = []

        for nb in neighbors:
            nb_val = grid[nb]
            neighbor_points.append((nb, nb_val))
            explored_points.append((nb, nb_val, "neighbor_search", major_iter))
            unique_explored_points.add(nb)

            if better(nb_val, current_val):
                improving.append((nb, nb_val))

        if verbose:
            print(f"\nMajor iteration {major_iter}")
            print(f"Base point: {current} -> {current_val:.12f}")
            print("Neighbor search explored:")
            for pt, val in neighbor_points:
                print(f"   {pt} -> {val:.12f}")
            print(f"Unique points explored so far: {len(unique_explored_points)}")

        # Stop if no improving neighbor exists
        if not improving:
            if verbose:
                print("No improving neighbor found. Stop.")
            history.append(
                {
                    "major_iter": major_iter,
                    "base_point": current,
                    "base_value": current_val,
                    "neighbor_points": neighbor_points,
                    "line_search_points": [],
                    "unique_points_explored_so_far": len(unique_explored_points),
                    "stopped": True,
                }
            )
            break

        # 2. Pick best improving neighbor
        if maximize:
            best_val = max(val for _, val in improving)
        else:
            best_val = min(val for _, val in improving)

        candidate_points = [
            (pt, val) for pt, val in improving if equal_obj(val, best_val)
        ]

        if tie_break == "first":
            next_point, next_val = candidate_points[0]
        elif tie_break == "nearest":
            next_point, next_val = min(
                candidate_points, key=lambda item: move_distance(current, item[0])
            )
        elif tie_break == "farthest":
            next_point, next_val = max(
                candidate_points, key=lambda item: move_distance(current, item[0])
            )
        else:
            raise ValueError("tie_break must be one of: 'first', 'nearest', 'farthest'")

        direction = (next_point[0] - current[0], next_point[1] - current[1])

        if verbose:
            print(f"Chosen improving neighbor: {next_point} -> {next_val:.12f}")
            print(f"Chosen direction: {direction}")

        # 3. Line search
        line_search_points = []

        last_improving_point = next_point
        last_improving_val = next_val

        # next_point was already evaluated during neighbor search,
        # so do not count it again as a unique explored point
        path.append(next_point)
        line_search_points.append((next_point, next_val, "accepted"))

        current_line_point = next_point
        current_line_val = next_val

        while True:
            trial_point = (
                current_line_point[0] + direction[0],
                current_line_point[1] + direction[1],
            )

            if trial_point not in grid:
                line_search_points.append((trial_point, None, "out_of_bounds"))
                if verbose:
                    print(
                        f"Line search trial {trial_point} -> out of bounds, stop line search."
                    )
                break

            trial_val = grid[trial_point]
            explored_points.append((trial_point, trial_val, "line_search", major_iter))
            unique_explored_points.add(trial_point)

            if better(trial_val, current_line_val):
                current_line_point = trial_point
                current_line_val = trial_val
                last_improving_point = trial_point
                last_improving_val = trial_val
                path.append(current_line_point)
                line_search_points.append((trial_point, trial_val, "accepted"))

                if verbose:
                    print(f"Line search accepted: {trial_point} -> {trial_val:.12f}")
            else:
                line_search_points.append((trial_point, trial_val, "rejected"))
                if verbose:
                    print(f"Line search rejected: {trial_point} -> {trial_val:.12f}")
                    print("Restart neighbor search from last improving point.")
                break

        # 4. Restart from last improving point
        current = last_improving_point
        current_val = last_improving_val

        history.append(
            {
                "major_iter": major_iter,
                "base_point": current,
                "base_value": current_val,
                "neighbor_points": neighbor_points,
                "line_search_points": line_search_points,
                "direction": direction,
                "unique_points_explored_so_far": len(unique_explored_points),
            }
        )

    return {
        "start_point": start_point,
        "start_value": grid[start_point],
        "best_point": current,
        "best_value": current_val,
        "major_iterations": major_iter,
        "points_explored": len(unique_explored_points),
        "unique_explored_points": sorted(unique_explored_points),
        "path": path,
        "history": history,
        "explored_points": explored_points,
    }


def run_ldsda_from_best_starting_points(
    csv_path,
    starting_points,
    diagonal=False,
    maximize=False,
    tol=1e-12,
    tie_break="first",
    target_value=0.0,
    verbose=True,
):
    """
    Rank starting points by initial value, then run pseudo-LDSDA from best to worst.

    Returns
    -------
    result : dict
        {
            "ordered_starting_points": [...],
            "starting_point_values": [...],
            "runs": [...],
            "best_run": ...,
            "best_value": ...,
            "best_point": ...,
            "total_points_explored_across_runs": ...,
            "total_unique_points_explored_across_runs": ...,
            "all_unique_points_explored": [...]
        }
    """
    _, grid = load_grid_csv(csv_path)

    cleaned_points = [tuple(pt) for pt in starting_points]

    for pt in cleaned_points:
        if pt not in grid:
            raise ValueError(f"Starting point {pt} is not in the grid.")

    # Evaluate starting point values first
    starting_point_values = [(pt, grid[pt]) for pt in cleaned_points]

    # Sort starting points by initial value
    starting_point_values.sort(key=lambda item: item[1], reverse=maximize)
    ordered_starting_points = [pt for pt, _ in starting_point_values]

    if verbose:
        print("Starting points ranked by initial value:")
        for rank, (pt, val) in enumerate(starting_point_values, start=1):
            print(f"{rank}. {pt} -> {val:.12f}")

    runs = []
    best_run = None

    # Count the initial ranking evaluations of the starting points
    initial_points_evaluated = len(cleaned_points)

    total_points_explored_across_runs = 0
    all_unique_points_explored = set(cleaned_points)

    def target_reached(val):
        return isclose(val, target_value, abs_tol=tol, rel_tol=0.0)

    for i, pt in enumerate(ordered_starting_points, start=1):
        if verbose:
            print("\n" + "=" * 70)
            print(f"Run {i} starting from {pt}")
            print("=" * 70)

        run_result = ldsda_from_csv(
            csv_path=csv_path,
            start_point=pt,
            diagonal=diagonal,
            maximize=maximize,
            tol=tol,
            tie_break=tie_break,
            verbose=verbose,
        )

        runs.append(run_result)

        total_points_explored_across_runs += run_result["points_explored"]
        all_unique_points_explored.update(run_result["unique_explored_points"])

        if best_run is None:
            best_run = run_result
        else:
            if maximize:
                if run_result["best_value"] > best_run["best_value"] + tol:
                    best_run = run_result
            else:
                if run_result["best_value"] < best_run["best_value"] - tol:
                    best_run = run_result

        if verbose:
            print(f"\nRun {i} result:")
            print(f"  Start point            : {run_result['start_point']}")
            print(f"  Start value            : {run_result['start_value']:.12f}")
            print(f"  Best point             : {run_result['best_point']}")
            print(f"  Best value             : {run_result['best_value']:.12f}")
            print(f"  Points explored (run)  : {run_result['points_explored']}")

        if target_reached(run_result["best_value"]):
            if verbose:
                print(f"\nTarget value {target_value} reached. Stopping the loop.")
            break

    return {
        "ordered_starting_points": ordered_starting_points,
        "starting_point_values": starting_point_values,
        "runs": runs,
        "best_run": best_run,
        "best_value": best_run["best_value"],
        "best_point": best_run["best_point"],
        "initial_points_evaluated": initial_points_evaluated,
        "total_points_explored_across_runs": total_points_explored_across_runs,
        "total_points_explored_including_initial_ranking": initial_points_evaluated
        + total_points_explored_across_runs,
        "total_unique_points_explored_across_runs": len(all_unique_points_explored),
        "all_unique_points_explored": sorted(all_unique_points_explored),
    }


# Example batch run across all benchmark grids.
rng = random.Random(0)
starting_points = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(3)]
print("Starting points:")
for sp in starting_points:
    print(sp)

csv_paths = [
    "qhdopt/ackley.csv",
    "qhdopt/alpine1.csv",
    "qhdopt/alpine2.csv",
    "qhdopt/bohachevsky2.csv",
    "qhdopt/camel3.csv",
    "qhdopt/csendes.csv",
    "qhdopt/deflected_corrugated_spring.csv",
    "qhdopt/dropwave.csv",
    "qhdopt/easom.csv",
    "qhdopt/griewank.csv",
    "qhdopt/holder_table.csv",
    "qhdopt/hosaki.csv",
    "qhdopt/levy.csv",
    "qhdopt/levy13.csv",
    "qhdopt/michalewicz.csv",
    "qhdopt/rastrigin.csv",
    "qhdopt/rosenbrock.csv",
    "qhdopt/shubert.csv",
    "qhdopt/styblinski_tang.csv",
    "qhdopt/sum_of_squares.csv",
    "qhdopt/xin_she_yang3.csv",
]

for csv_path in csv_paths:
    print("\n" + "=" * 80)
    print(f"Running: {csv_path}")
    print("=" * 80)

    multi_result = run_ldsda_from_best_starting_points(
        csv_path=csv_path,
        starting_points=starting_points,
        diagonal=True,
        maximize=False,
        tie_break="first",
        target_value=0.0,
        verbose=True,
    )

    print("\nOverall summary:")
    print(
        "Ordered starting points                        :",
        multi_result["ordered_starting_points"],
    )
    print("Overall best point                             :", multi_result["best_point"])
    print("Overall best value                             :", multi_result["best_value"])
    print(
        "Initial starting points evaluated              :",
        multi_result["initial_points_evaluated"],
    )
    print(
        "Total points explored across runs              :",
        multi_result["total_points_explored_across_runs"],
    )
    print(
        "Total points explored incl. initial ranking    :",
        multi_result["total_points_explored_including_initial_ranking"],
    )
    print(
        "Total unique points explored overall           :",
        multi_result["total_unique_points_explored_across_runs"],
    )
