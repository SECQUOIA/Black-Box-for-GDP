"""DSDA runner for the small-batch case study."""

import argparse
import math
import time
from pathlib import Path

from grid_dsda import dsda_from_csv
from instrumentation import TrackedObjective, make_result_record, save_results_csv

from .common import generate_lhc_starting_points
from .small_batch_case import (
    DEFAULT_MAX_EVALUATIONS,
    KNOWN_BEST_POINT,
    KNOWN_BEST_VALUE,
    LOWER_BOUNDS,
    SMALL_BATCH_CSV_NAME,
    SMALL_BATCH_FEASIBLE_OBJECTIVES,
    UPPER_BOUNDS,
)
from .small_batch_rbfopt import DEFAULT_SEED


def choose_best_feasible_start(starting_points, tracked_objective):
    """
    Choose the feasible LHC start with the lowest small-batch objective value.

    Feasible points are evaluated through the shared tracker so ranking
    evaluations count toward the DSDA budget.
    """
    feasible_start_values = []
    for point in starting_points:
        lattice_point = tuple(point)
        if lattice_point in SMALL_BATCH_FEASIBLE_OBJECTIVES:
            value = tracked_objective(lattice_point)
            feasible_start_values.append((lattice_point, value))

    if not feasible_start_values:
        raise ValueError("No feasible LHC starting points were generated for DSDA.")

    feasible_start_values.sort(key=lambda item: item[1])
    return feasible_start_values[0][0], feasible_start_values


def run_small_batch_dsda(
    seed=DEFAULT_SEED,
    n_starts=3,
    max_evaluations=DEFAULT_MAX_EVALUATIONS,
    diagonal=True,
    tie_break="first",
    verbose=False,
):
    """Run DSDA on the small-batch case from the best feasible LHC start."""
    start_time = time.perf_counter()
    starting_points = generate_lhc_starting_points(
        n_dims=3,
        n_points=n_starts,
        lb=LOWER_BOUNDS,
        ub=UPPER_BOUNDS,
        seed=seed,
    )
    tracked_objective = TrackedObjective(
        lambda point: SMALL_BATCH_FEASIBLE_OBJECTIVES[tuple(point)]
    )
    selected_start, feasible_start_values = choose_best_feasible_start(
        starting_points,
        tracked_objective,
    )

    remaining_budget = None
    if max_evaluations is not None:
        remaining_budget = max_evaluations - tracked_objective.call_count
        if remaining_budget <= 0:
            remaining_budget = 0

    run_result = None
    if remaining_budget != 0:
        run_result = dsda_from_csv(
            csv_path="/small-batch/case/no-csv.csv",
            start_point=selected_start,
            diagonal=diagonal,
            maximize=False,
            tie_break=tie_break,
            verbose=verbose,
            max_points_explored=remaining_budget,
            grid=SMALL_BATCH_FEASIBLE_OBJECTIVES,
            tracked_objective=tracked_objective,
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
        tuple(best_point) == KNOWN_BEST_POINT
        and math.isclose(best_value, KNOWN_BEST_VALUE, abs_tol=1e-12, rel_tol=0.0)
    )
    result_record = make_result_record(
        csv_name=SMALL_BATCH_CSV_NAME,
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
        "case_name": "small_batch",
        "starting_points": starting_points,
        "feasible_start_values": feasible_start_values,
        "selected_start": selected_start,
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
    """Run the small-batch DSDA case and optionally save one result record."""
    result = run_small_batch_dsda(**kwargs)
    if output_path is not None:
        save_results_csv([result["result_record"]], Path(output_path))

    print("Small-batch DSDA run completed.")
    print("Starting points:", result["starting_points"])
    print("Feasible starting points:", result["feasible_start_values"])
    print("Selected start:", result["selected_start"])
    print("Best objective value found:", result["best_value"])
    print("At lattice point:", result["best_point"])
    return result


def parse_args():
    """Parse command-line arguments for running the small-batch DSDA case."""
    parser = argparse.ArgumentParser(description=__doc__)
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
        seed=args.seed,
        n_starts=args.n_starts,
        max_evaluations=args.max_evaluations,
        diagonal=not args.no_diagonal,
        tie_break=args.tie_break,
        verbose=args.verbose,
    )
