"""
CSV-driven DSDA-style experiments for the QHDOpt benchmark grids.

This module loads normalized benchmark grids from `qhdopt/*.csv` and runs a
discrete steepest descent search directly on the sampled lattice. It does not
build Pyomo GDP models, and it does not implement the full GDP-based LDSDA
solver.

The benchmark grids used here are derived from benchmark examples listed on:
https://jiaqileng.github.io/quantum-hamiltonian-descent/nonconvex2d.html

Here, DSDA stands for the Discrete Steepest Descent Algorithm; see, for example,
Ovalle et al., “Logic-Based Discrete-Steepest Descent: A Solution Method for
Process Synthesis Generalized Disjunctive Programs.”

Although the filename is retained from an earlier GDP-oriented version, the
current implementation operates directly on precomputed CSV grids.
"""

import pandas as pd
import random
from itertools import product
from math import isclose, sqrt


def load_grid_csv(csv_path):
    """
    Load a precomputed normalized 2D benchmark grid from CSV.

    Required columns:
        - x
        - y
        - z_norm

    Returns
    -------
    df : pandas.DataFrame
    grid : dict
        grid[(x, y)] = precomputed z_norm
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
        Coordinate tuple for the current grid point.
    grid : dict
        grid[coordinate_tuple] = z
    diagonal : bool
        If True, use the full L-infinity neighborhood.
        If False, use one-coordinate moves only.
    """
    directions = []
    for step in product((-1, 0, 1), repeat=len(point)):
        if all(delta == 0 for delta in step):
            continue
        if not diagonal and sum(abs(delta) for delta in step) != 1:
            continue
        directions.append(step)

    neighbors = []
    for step in directions:
        candidate = tuple(coord + delta for coord, delta in zip(point, step))
        if candidate in grid:
            neighbors.append(candidate)

    return neighbors


def dsda_from_csv(
    csv_path,
    start_point,
    diagonal=False,
    maximize=False,
    tol=1e-12,
    tie_break="first",
    verbose=True,
    max_points_explored=None,
    grid=None,
):
    """
    DSDA-style search on a discrete grid loaded from CSV.

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
        If True, use the full L-infinity neighborhood. Otherwise use one-coordinate moves.
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
    max_points_explored : int or None, optional
        Maximum number of evaluated points allowed for this DSDA run. This
        budget is enforced on total point evaluations, not on unique explored
        points. If the budget is reached in the middle of the run, the search stops and returns
        the best point found so far.
    grid : dict or None, optional
        Pre-loaded grid dictionary mapping coordinate tuples to z_norm values.
        When provided, csv_path is not read again, avoiding redundant I/O
        in multi-start loops.

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
            "point_evaluations": ...,
            "unique_explored_points": [...],
            "path": [...],
            "history": [...],
            "explored_points": [...],
            "stopped_early": ...,
            "stop_reason": ...,
        }
    """
    if max_points_explored is not None and max_points_explored < 1:
        raise ValueError("max_points_explored must be at least 1.")

    if grid is None:
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
        return sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

    current = start_point
    current_val = grid[current]
    best_seen_point = current
    best_seen_value = current_val

    path = [current]

    major_iter = 0
    unique_explored_points = set()
    explored_points = []
    stopped_early = False
    stop_reason = None

    def budget_reached():
        # Budget is enforced on total point evaluations, not unique points.
        return (
            max_points_explored is not None
            and len(explored_points) >= max_points_explored
        )

    def update_best(point, value):
        nonlocal best_seen_point, best_seen_value
        if better(value, best_seen_value):
            best_seen_point = point
            best_seen_value = value

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
        if budget_reached():
            stopped_early = True
            stop_reason = "max_points_explored"
            if verbose:
                print("Maximum point-exploration budget reached. Stop.")
            history.append(
                {
                    "major_iter": major_iter,
                    "base_point": current,
                    "base_value": current_val,
                    "neighbor_points": [],
                    "line_search_points": [],
                    "unique_points_explored_so_far": len(unique_explored_points),
                    "stopped_early": True,
                    "stop_reason": stop_reason,
                }
            )
            break

        major_iter += 1

        # Capture the base state before any updates so that the history
        # entry records the actual starting point of this iteration.
        iter_base_point = current
        iter_base_val = current_val

        # 1. Neighbor search
        neighbors = get_neighbors(current, grid, diagonal=diagonal)

        neighbor_points = []
        improving = []
        line_search_points = []

        for nb in neighbors:
            if budget_reached():
                stopped_early = True
                stop_reason = "max_points_explored"
                if verbose:
                    print(
                        "Maximum point-exploration budget reached during neighbor search. Stop."
                    )
                break

            nb_val = grid[nb]
            neighbor_points.append((nb, nb_val))
            explored_points.append((nb, nb_val, "neighbor_search", major_iter))
            unique_explored_points.add(nb)
            update_best(nb, nb_val)

            if better(nb_val, current_val):
                improving.append((nb, nb_val))

        if verbose:
            print(f"\nMajor iteration {major_iter}")
            print(f"Base point: {current} -> {current_val:.12f}")
            print("Neighbor search explored:")
            for pt, val in neighbor_points:
                print(f"   {pt} -> {val:.12f}")
            print(f"Unique points explored so far: {len(unique_explored_points)}")

        if stopped_early:
            history.append(
                {
                    "major_iter": major_iter,
                    "base_point": current,
                    "base_value": current_val,
                    "neighbor_points": neighbor_points,
                    "line_search_points": line_search_points,
                    "unique_points_explored_so_far": len(unique_explored_points),
                    "stopped_early": True,
                    "stop_reason": stop_reason,
                }
            )
            break

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

        direction = tuple(
            next_coord - cur_coord for next_coord, cur_coord in zip(next_point, current)
        )

        if verbose:
            print(f"Chosen improving neighbor: {next_point} -> {next_val:.12f}")
            print(f"Chosen direction: {direction}")

        # 3. Line search
        last_improving_point = next_point
        last_improving_val = next_val

        # next_point was already evaluated during neighbor search,
        # so do not count it again as a unique explored point
        path.append(next_point)
        line_search_points.append((next_point, next_val, "accepted"))

        current_line_point = next_point
        current_line_val = next_val

        while True:
            if budget_reached():
                stopped_early = True
                stop_reason = "max_points_explored"
                if verbose:
                    print(
                        "Maximum point-exploration budget reached during line search. Stop."
                    )
                break

            trial_point = tuple(
                coord + step for coord, step in zip(current_line_point, direction)
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
            update_best(trial_point, trial_val)

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
                "base_point": iter_base_point,
                "base_value": iter_base_val,
                "neighbor_points": neighbor_points,
                "line_search_points": line_search_points,
                "direction": direction,
                "unique_points_explored_so_far": len(unique_explored_points),
                "stopped_early": stopped_early,
                "stop_reason": stop_reason,
            }
        )

        if stopped_early:
            break

    return {
        "start_point": start_point,
        "start_value": grid[start_point],
        "best_point": best_seen_point,
        "best_value": best_seen_value,
        "major_iterations": major_iter,
        "points_explored": len(unique_explored_points),
        "point_evaluations": len(explored_points),
        "unique_explored_points": sorted(unique_explored_points),
        "path": path,
        "history": history,
        "explored_points": explored_points,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "max_points_explored": max_points_explored,
    }


def run_dsda_from_best_starting_points(
    csv_path,
    starting_points,
    diagonal=False,
    maximize=False,
    tol=1e-12,
    tie_break="first",
    target_value=0.0,
    verbose=True,
    max_points_explored=100,
):
    """
    Rank starting points by initial value, then run DSDA from best to worst.

    Parameters
    ----------
    max_points_explored : int or None, optional
        Maximum total number of evaluated points allowed across the full
        multi-start procedure, including the initial ranking of starting points.
        If the budget is reached in the middle of a DSDA run, that run stops and
        returns its best point found so far.

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
            "all_unique_points_explored": [...],
            "total_point_evaluations_across_runs": ...,
            "total_point_evaluations_including_initial_ranking": ...,
            "stopped_early": ...,
            "stop_reason": ...,
        }
    """
    if max_points_explored is not None and max_points_explored < 1:
        raise ValueError("max_points_explored must be at least 1.")

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
    total_point_evaluations_across_runs = 0
    all_unique_points_explored = set(cleaned_points)
    stopped_early = False
    stop_reason = None

    best_point, best_value = starting_point_values[0]

    def target_reached(val):
        return isclose(val, target_value, abs_tol=tol, rel_tol=0.0)

    if (
        max_points_explored is not None
        and initial_points_evaluated >= max_points_explored
    ):
        stopped_early = True
        stop_reason = "max_points_explored"
        if verbose:
            print(
                "Maximum point-exploration budget reached during starting-point ranking."
            )
        return {
            "ordered_starting_points": ordered_starting_points,
            "starting_point_values": starting_point_values,
            "runs": runs,
            "best_run": best_run,
            "best_value": best_value,
            "best_point": best_point,
            "initial_points_evaluated": initial_points_evaluated,
            "total_points_explored_across_runs": total_points_explored_across_runs,
            "total_points_explored_including_initial_ranking": initial_points_evaluated
            + total_points_explored_across_runs,
            "total_unique_points_explored_across_runs": len(all_unique_points_explored),
            "all_unique_points_explored": sorted(all_unique_points_explored),
            "total_point_evaluations_across_runs": total_point_evaluations_across_runs,
            "total_point_evaluations_including_initial_ranking": initial_points_evaluated
            + total_point_evaluations_across_runs,
            "stopped_early": stopped_early,
            "stop_reason": stop_reason,
            "max_points_explored": max_points_explored,
        }

    for i, pt in enumerate(ordered_starting_points, start=1):
        if verbose:
            print("\n" + "=" * 70)
            print(f"Run {i} starting from {pt}")
            print("=" * 70)

        remaining_budget = None
        if max_points_explored is not None:
            remaining_budget = max_points_explored - (
                initial_points_evaluated + total_point_evaluations_across_runs
            )
            if remaining_budget <= 0:
                stopped_early = True
                stop_reason = "max_points_explored"
                if verbose:
                    print(
                        "Maximum point-exploration budget reached before starting the next DSDA run."
                    )
                break

        run_result = dsda_from_csv(
            csv_path=csv_path,
            start_point=pt,
            diagonal=diagonal,
            maximize=maximize,
            tol=tol,
            tie_break=tie_break,
            verbose=verbose,
            max_points_explored=remaining_budget,
            grid=grid,
        )

        runs.append(run_result)

        total_points_explored_across_runs += run_result["points_explored"]
        total_point_evaluations_across_runs += run_result["point_evaluations"]
        all_unique_points_explored.update(run_result["unique_explored_points"])

        if best_run is None:
            best_run = run_result
            best_point = run_result["best_point"]
            best_value = run_result["best_value"]
        else:
            if maximize:
                if run_result["best_value"] > best_value + tol:
                    best_run = run_result
                    best_point = run_result["best_point"]
                    best_value = run_result["best_value"]
            else:
                if run_result["best_value"] < best_value - tol:
                    best_run = run_result
                    best_point = run_result["best_point"]
                    best_value = run_result["best_value"]

        if verbose:
            print(f"\nRun {i} result:")
            print(f"  Start point            : {run_result['start_point']}")
            print(f"  Start value            : {run_result['start_value']:.12f}")
            print(f"  Best point             : {run_result['best_point']}")
            print(f"  Best value             : {run_result['best_value']:.12f}")
            print(f"  Points explored (run)  : {run_result['points_explored']}")
            print(f"  Point evaluations (run): {run_result['point_evaluations']}")

        if run_result["stopped_early"]:
            stopped_early = True
            stop_reason = run_result["stop_reason"]
            if verbose:
                print(
                    "\nStopping after an incomplete DSDA run because the point budget was exhausted."
                )
            break

        if target_reached(run_result["best_value"]):
            if verbose:
                print(f"\nTarget value {target_value} reached. Stopping the loop.")
            break

    return {
        "ordered_starting_points": ordered_starting_points,
        "starting_point_values": starting_point_values,
        "runs": runs,
        "best_run": best_run,
        "best_value": best_value,
        "best_point": best_point,
        "initial_points_evaluated": initial_points_evaluated,
        "total_points_explored_across_runs": total_points_explored_across_runs,
        "total_points_explored_including_initial_ranking": initial_points_evaluated
        + total_points_explored_across_runs,
        "total_unique_points_explored_across_runs": len(all_unique_points_explored),
        "all_unique_points_explored": sorted(all_unique_points_explored),
        "total_point_evaluations_across_runs": total_point_evaluations_across_runs,
        "total_point_evaluations_including_initial_ranking": initial_points_evaluated
        + total_point_evaluations_across_runs,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "max_points_explored": max_points_explored,
    }


# Backward-compatible aliases retained from the earlier LDSDA naming.
ldsda_from_csv = dsda_from_csv
run_ldsda_from_best_starting_points = run_dsda_from_best_starting_points


def main():
    """Run DSDA search on all benchmark grids with random starting points."""
    from pathlib import Path

    csv_dir = Path(__file__).resolve().parent / "qhdopt"
    csv_paths = sorted(csv_dir.glob("*.csv"))

    rng = random.Random(0)
    starting_points = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(3)]
    print("Starting points:")
    for sp in starting_points:
        print(sp)

    for csv_path in csv_paths:
        print("\n" + "=" * 80)
        print(f"Running: {csv_path.name}")
        print("=" * 80)

        multi_result = run_dsda_from_best_starting_points(
            csv_path=str(csv_path),
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
        print(
            "Overall best point                             :",
            multi_result["best_point"],
        )
        print(
            "Overall best value                             :",
            multi_result["best_value"],
        )
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
        print(
            "Total point evaluations incl. initial ranking  :",
            multi_result["total_point_evaluations_including_initial_ranking"],
        )
        print(
            "Stopped early due to point budget              :",
            multi_result["stopped_early"],
        )


if __name__ == "__main__":
    main()
