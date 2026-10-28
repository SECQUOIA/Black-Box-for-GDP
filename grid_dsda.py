"""
CSV-driven DSDA-style experiments for the QHDOpt benchmark grids.

This module loads normalized benchmark grids from `benchmark_grids/*.csv` and runs a
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
import time
from itertools import product
from math import isclose, isfinite, sqrt
from pathlib import Path

from instrumentation import (
    make_result_record,
    make_timestamped_results_dir,
    save_results_csv,
)

from dsda_protocol import (
    IMPROVEMENT_ABS_TOL, ObservedObjective, common_target_reached,
    improves, validate_tolerances, add_target_report,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "benchmark_grids"
RESULTS_DIR = BASE_DIR / "results"


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


def make_grid_objective(grid):
    """Return an objective function that evaluates points from a grid mapping."""

    def objective(point):
        return grid[tuple(point)]

    return objective


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
    tracked_objective=None,
    start_value=None,
    improvement_abs_tol=IMPROVEMENT_ABS_TOL,
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
    start_value : float or None, optional
        Previously evaluated objective value for ``start_point``. When provided,
        the start point is not evaluated again, which lets callers include a
        shared initial design in a global evaluation budget without double
        counting the selected start.
    diagonal : bool, optional
        If True, use the full L-infinity neighborhood. Otherwise use one-coordinate moves.
    maximize : bool, optional
        If True, maximize z_norm. Otherwise minimize.
    tol : float, optional
        Internal tie tolerance (default 1e-12), also used in legacy movement.
    improvement_abs_tol : float or None, optional
        Strict absolute movement threshold (default 1e-5); None selects the
        historical arithmetic using tol.
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
    tracked_objective : TrackedObjective or None, optional
        Shared objective wrapper. When omitted, this function creates its own
        wrapper around the grid objective.

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
            "wall_time_s": ...,
            "incumbent_trajectory": [...],
            "objective_wall_times": [...],
        }
    """
    validate_tolerances(tol, improvement_abs_tol)
    if max_points_explored is not None and max_points_explored < 1:
        raise ValueError("max_points_explored must be at least 1.")

    start_time = time.perf_counter()

    if grid is None:
        _, grid = load_grid_csv(csv_path)

    start_point = tuple(start_point)
    if start_point not in grid:
        raise ValueError(f"Start point {start_point} is not in the grid.")

    if tracked_objective is None:
        tracked_objective = ObservedObjective(
            make_grid_objective(grid), maximize=maximize, legacy=improvement_abs_tol is None
        )

    initial_call_count = tracked_objective.call_count

    def run_evaluations():
        return tracked_objective.call_count - initial_call_count

    local_incumbent = None
    local_incumbent_trajectory = []

    def record_run_value(value):
        nonlocal local_incumbent

        if improvement_abs_tol is not None and (
            not isfinite(value) or value == getattr(tracked_objective, "penalty", None)
        ):
            local_incumbent_trajectory.append(local_incumbent)
            return value
        if local_incumbent is None:
            local_incumbent = value
        elif maximize:
            if value > local_incumbent:
                local_incumbent = value
        elif value < local_incumbent:
            local_incumbent = value
        local_incumbent_trajectory.append(local_incumbent)
        return value

    def evaluate_run_point(point):
        return record_run_value(tracked_objective(point))

    def run_incumbent_trajectory():
        return list(local_incumbent_trajectory)

    def run_objective_wall_times():
        return tracked_objective.wall_times[initial_call_count:]

    def better(new_val, current_val):
        return improves(new_val, current_val, maximize, tol, improvement_abs_tol)

    def equal_obj(a, b):
        return isclose(a, b, abs_tol=tol, rel_tol=0.0)

    def move_distance(p1, p2):
        return sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

    current = start_point
    used_cached_start_value = start_value is not None
    if start_value is None:
        current_val = evaluate_run_point(current)
    else:
        current_val = record_run_value(start_value)
    start_value = current_val
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
            and run_evaluations() >= max_points_explored
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

            nb_val = evaluate_run_point(nb)
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

            trial_val = evaluate_run_point(trial_point)
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
                "base_point": current,
                "base_value": current_val,
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

    wall_time_s = time.perf_counter() - start_time
    incumbent_trajectory = run_incumbent_trajectory()

    result = {
        "start_point": start_point,
        "start_value": start_value,
        "best_point": best_seen_point,
        "best_value": best_seen_value,
        "major_iterations": major_iter,
        "points_explored": len(unique_explored_points),
        "point_evaluations": run_evaluations(),
        "unique_explored_points": sorted(unique_explored_points),
        "path": path,
        "history": history,
        "explored_points": explored_points,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "max_points_explored": max_points_explored,
        "wall_time_s": wall_time_s,
        "incumbent_trajectory": incumbent_trajectory,
        "objective_wall_times": run_objective_wall_times(),
    }
    result["result_record"] = make_result_record(
        csv_name=Path(csv_path).name,
        method="DSDA",
        seed=None,
        n_starts=1,
        max_evals=max_points_explored,
        best_value=best_seen_value,
        best_point=best_seen_point,
        total_evals=run_evaluations(),
        wall_time_s=wall_time_s,
        found_optimum=None,
        incumbent_trajectory=incumbent_trajectory,
        initial_evals=0 if used_cached_start_value else 1,
        adaptive_evals=(
            run_evaluations()
            if used_cached_start_value
            else max(0, run_evaluations() - 1)
        ),
        unique_evals=len(unique_explored_points),
    )
    return result


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
    improvement_abs_tol=IMPROVEMENT_ABS_TOL,
    target_stop=common_target_reached,
    grid=None,
    tracked_objective=None,
):
    """
    Rank starting points by initial value, then run DSDA from best to worst.

    The default target_stop uses the finite observed incumbent and the adopted
    common target tolerance after each completed descent, after checking budget.
    Pass improvement_abs_tol=None and target_stop=None for legacy movement and
    absolute tol target checks; ties always use tol independently.
    Optional grid/tracked_objective inputs support stored-response replay; the
    tracker must be fresh and its incumbent must exclude invalid responses.
    Path-selected best_value is retained; observed_best_value and target_reached
    describe all accepted observations, including rejected moves.

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
            "wall_time_s": ...,
            "incumbent_trajectory": [...],
            "objective_wall_times": [...],
        }
    """
    validate_tolerances(tol, improvement_abs_tol)
    if max_points_explored is not None and max_points_explored < 1:
        raise ValueError("max_points_explored must be at least 1.")

    if target_stop is not None and not callable(target_stop):
        raise TypeError("target_stop must be callable or None")
    target_stop_checks = []

    start_time = time.perf_counter()

    if grid is None:
        _, grid = load_grid_csv(csv_path)
    if tracked_objective is None:
        tracked_objective = ObservedObjective(
            make_grid_objective(grid), maximize=maximize, legacy=improvement_abs_tol is None
        )
    if tracked_objective.call_count:
        raise ValueError("Multi-start requires a fresh objective tracker")

    cleaned_points = [tuple(pt) for pt in starting_points]
    if not cleaned_points:
        raise ValueError("At least one starting point is required")

    for pt in cleaned_points:
        if pt not in grid:
            raise ValueError(f"Starting point {pt} is not in the grid.")

    # Evaluate starting point values first, while honoring the global
    # black-box evaluation budget.
    starting_point_values = []
    for pt in cleaned_points:
        if (
            max_points_explored is not None
            and tracked_objective.call_count >= max_points_explored
        ):
            break
        starting_point_values.append((pt, tracked_objective(pt)))

    # Sort starting points by initial value
    if improvement_abs_tol is None:
        starting_point_values.sort(key=lambda item: item[1], reverse=maximize)
    else:
        starting_point_values.sort(
            key=lambda item: item[1] if isfinite(item[1]) else (
                -float("inf") if maximize else float("inf")
            ), reverse=maximize,
        )
    ordered_starting_points = [pt for pt, _ in starting_point_values]
    starting_value_by_point = {pt: val for pt, val in starting_point_values}

    if verbose:
        print("Starting points ranked by initial value:")
        for rank, (pt, val) in enumerate(starting_point_values, start=1):
            print(f"{rank}. {pt} -> {val:.12f}")

    runs = []
    best_run = None

    # Count the initial ranking evaluations of the starting points
    initial_points_evaluated = len(starting_point_values)
    total_points_explored_across_runs = 0
    total_point_evaluations_across_runs = 0
    all_unique_points_explored = {pt for pt, _ in starting_point_values}
    stopped_early = False
    stop_reason = None

    best_point, best_value = starting_point_values[0]

    def target_reached(val):
        if target_stop is not None:
            return bool(target_stop(tracked_objective.incumbent, target_value))
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
        wall_time_s = time.perf_counter() - start_time
        incumbent_trajectory = tracked_objective.incumbent_trajectory
        result = {
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
            "wall_time_s": wall_time_s,
            "incumbent_trajectory": incumbent_trajectory,
            "objective_wall_times": tracked_objective.wall_times,
        }
        result["result_record"] = make_result_record(
            csv_name=Path(csv_path).name,
            method="DSDA",
            seed=None,
            n_starts=len(cleaned_points),
            max_evals=max_points_explored,
            best_value=best_value,
            best_point=best_point,
            total_evals=tracked_objective.call_count,
            wall_time_s=wall_time_s,
            found_optimum=target_reached(best_value),
            incumbent_trajectory=incumbent_trajectory,
            initial_evals=initial_points_evaluated,
            adaptive_evals=total_point_evaluations_across_runs,
            unique_evals=len(all_unique_points_explored),
        )
        add_target_report(result, tracked_objective.incumbent, target_value)
        if target_stop is not None:
            result["target_stop_checks"] = target_stop_checks
        return result

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
            tracked_objective=tracked_objective,
            start_value=starting_value_by_point[pt],
            improvement_abs_tol=improvement_abs_tol,
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
                if improves(run_result["best_value"], best_value, True, tol, improvement_abs_tol):
                    best_run = run_result
                    best_point = run_result["best_point"]
                    best_value = run_result["best_value"]
            else:
                if improves(run_result["best_value"], best_value, False, tol, improvement_abs_tol):
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

        reached = target_reached(run_result["best_value"])
        if target_stop is not None:
            target_stop_checks.append(dict(
                descent_index=i, callback=tracked_objective.call_count,
                observed_incumbent=tracked_objective.incumbent,
                target=target_value, reached=reached,
            ))
        if reached:
            if target_stop is not None:
                stop_reason = "target_common_success"
            if verbose:
                print(f"\nTarget value {target_value} reached. Stopping the loop.")
            break

    wall_time_s = time.perf_counter() - start_time
    incumbent_trajectory = tracked_objective.incumbent_trajectory
    total_evals = initial_points_evaluated + total_point_evaluations_across_runs

    result = {
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
        "total_point_evaluations_including_initial_ranking": total_evals,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "max_points_explored": max_points_explored,
        "wall_time_s": wall_time_s,
        "incumbent_trajectory": incumbent_trajectory,
        "objective_wall_times": tracked_objective.wall_times,
    }
    result["result_record"] = make_result_record(
        csv_name=Path(csv_path).name,
        method="DSDA",
        seed=None,
        n_starts=len(cleaned_points),
        max_evals=max_points_explored,
        best_value=best_value,
        best_point=best_point,
        total_evals=total_evals,
        wall_time_s=wall_time_s,
        found_optimum=target_reached(best_value),
        incumbent_trajectory=incumbent_trajectory,
        initial_evals=initial_points_evaluated,
        adaptive_evals=total_point_evaluations_across_runs,
        unique_evals=len(all_unique_points_explored),
    )
    add_target_report(result, tracked_objective.incumbent, target_value)
    if target_stop is not None:
        result["target_stop_checks"] = target_stop_checks
    return result


# Backward-compatible aliases retained from the earlier LDSDA naming.
ldsda_from_csv = dsda_from_csv
run_ldsda_from_best_starting_points = run_dsda_from_best_starting_points


def main():
    """Run DSDA search on all benchmark grids with random starting points."""
    csv_paths = sorted(DATA_DIR.glob("*.csv"))
    result_records = []
    results_dir = make_timestamped_results_dir(RESULTS_DIR, "dsda")
    results_path = results_dir / "dsda_results.csv"

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
        result_records.append(multi_result["result_record"])

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

    save_results_csv(result_records, results_path)
    print(f"DSDA result records saved in: {results_path}")
    return result_records, results_path


if __name__ == "__main__":
    main()
