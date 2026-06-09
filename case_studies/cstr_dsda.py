"""DSDA runner for the CSTR case study."""

import argparse
import math
import time
from pathlib import Path

from grid_dsda import dsda_from_csv
from instrumentation import TrackedObjective, make_result_record, save_results_csv

from .common import generate_lhc_starting_points, rank_starting_points
from .cstr_case import (
    DEFAULT_GRID_SIZE,
    DEFAULT_MAX_EVALUATIONS,
    LOWER_BOUNDS,
    cstr_objective,
    load_cstr_case_data,
)
from .cstr_rbfopt import DEFAULT_SEED


def choose_best_feasible_start(
    starting_points,
    tracked_objective,
    feasible_objectives,
):
    """
    Choose the feasible LHC start with the lowest CSTR objective value.

    All generated LHC points are evaluated through the shared tracker so the
    initial design accounting matches RBFOpt, then feasible starts are ranked
    for the DSDA descent run.
    """
    return rank_starting_points(
        starting_points,
        tracked_objective,
        lambda point: point in feasible_objectives,
    )


def run_cstr_dsda(
    grid_size=DEFAULT_GRID_SIZE,
    seed=DEFAULT_SEED,
    n_starts=3,
    max_evaluations=DEFAULT_MAX_EVALUATIONS,
    diagonal=True,
    tie_break="first",
    verbose=False,
):
    """Run DSDA on the CSTR case from the best feasible LHC start."""
    start_time = time.perf_counter()
    case_data = load_cstr_case_data(grid_size)
    upper_bounds = case_data["upper_bounds"]
    feasible_objectives = case_data["feasible_objectives"]
    known_best_point = case_data["known_best_point"]
    known_best_value = case_data["known_best_value"]

    starting_points = generate_lhc_starting_points(
        n_dims=2,
        n_points=n_starts,
        lb=LOWER_BOUNDS,
        ub=upper_bounds,
        seed=seed,
    )
    tracked_objective = TrackedObjective(
        lambda point: cstr_objective(
            point,
            grid_size=grid_size,
            feasible_objectives=feasible_objectives,
        )
    )
    (
        selected_start,
        selected_start_value,
        feasible_start_values,
        starting_point_values,
    ) = choose_best_feasible_start(
        starting_points,
        tracked_objective,
        feasible_objectives,
    )

    remaining_budget = None
    if max_evaluations is not None:
        remaining_budget = max_evaluations - tracked_objective.call_count
        if remaining_budget <= 0:
            remaining_budget = 0

    run_result = None
    if remaining_budget != 0:
        run_result = dsda_from_csv(
            csv_path=f"/cstr/case/{case_data['csv_name']}",
            start_point=selected_start,
            diagonal=diagonal,
            maximize=False,
            tie_break=tie_break,
            verbose=verbose,
            max_points_explored=remaining_budget,
            grid=feasible_objectives,
            tracked_objective=tracked_objective,
            start_value=selected_start_value,
        )

    if run_result is None:
        best_point, best_value = feasible_start_values[0]
        stopped_early = True
        stop_reason = "max_evaluations"
    else:
        best_point = run_result["best_point"]
        best_value = run_result["best_value"]
        stopped_early = run_result["stopped_early"]
        stop_reason = run_result["stop_reason"]

    wall_time_s = time.perf_counter() - start_time
    found_optimum = (
        tuple(best_point) == known_best_point
        and math.isclose(best_value, known_best_value, abs_tol=1e-12, rel_tol=0.0)
    )
    result_record = make_result_record(
        csv_name=case_data["csv_name"],
        method="DSDA",
        seed=seed,
        n_starts=n_starts,
        max_evals=max_evaluations,
        best_value=best_value,
        best_point=best_point,
        total_evals=tracked_objective.call_count,
        wall_time_s=wall_time_s,
        found_optimum=found_optimum,
        incumbent_trajectory=tracked_objective.incumbent_trajectory,
    )
    return {
        "case_name": "cstr",
        "grid_size": int(grid_size),
        "starting_points": starting_points,
        "starting_point_values": starting_point_values,
        "feasible_start_values": feasible_start_values,
        "selected_start": selected_start,
        "selected_start_value": selected_start_value,
        "best_value": best_value,
        "best_point": best_point,
        "tracked_evals": tracked_objective.call_count,
        "incumbent_trajectory": tracked_objective.incumbent_trajectory,
        "objective_wall_times": tracked_objective.wall_times,
        "run_result": run_result,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "result_record": result_record,
    }


def main(output_path=None, **kwargs):
    """Run the CSTR DSDA case and optionally save one result record."""
    result = run_cstr_dsda(**kwargs)
    if output_path is not None:
        save_results_csv([result["result_record"]], Path(output_path))

    print("CSTR DSDA run completed.")
    print("Grid size:", result["grid_size"])
    print("Starting points:", result["starting_points"])
    print("Feasible starting points:", result["feasible_start_values"])
    print("Selected start:", result["selected_start"])
    print("Best objective value found:", result["best_value"])
    print("At lattice point:", result["best_point"])
    return result


def parse_args():
    """Parse command-line arguments for running the CSTR DSDA case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid-size", type=int, default=DEFAULT_GRID_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--n-starts", type=int, default=3)
    parser.add_argument("--max-evaluations", type=int, default=DEFAULT_MAX_EVALUATIONS)
    parser.add_argument("--tie-break", default="first")
    parser.add_argument("--no-diagonal", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        output_path=args.output,
        grid_size=args.grid_size,
        seed=args.seed,
        n_starts=args.n_starts,
        max_evaluations=args.max_evaluations,
        diagonal=not args.no_diagonal,
        tie_break=args.tie_break,
        verbose=args.verbose,
    )
