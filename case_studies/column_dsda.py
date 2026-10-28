"""DSDA runner for the distillation column case study."""

import argparse
import math
import time
from pathlib import Path

from dsda_protocol import (
    IMPROVEMENT_ABS_TOL, ObservedObjective, add_target_report, validate_tolerances,
)
from grid_dsda import dsda_from_csv
from instrumentation import make_result_record, save_results_csv
from .dsda_domain import box_membership, rank_observed_starts, validate_design

from .column_case import (
    COLUMN_CSV_NAME,
    DEFAULT_MAX_EVALUATIONS,
    KNOWN_BEST_POINT,
    KNOWN_BEST_VALUE,
    LOWER_BOUNDS,
    PENALTY,
    UPPER_BOUNDS,
    column_objective,
)
from .common import generate_lhc_starting_points


DEFAULT_SEED = 1


def choose_best_feasible_start(starting_points, tracked_objective):
    """
    Choose the feasible LHC start with the lowest column objective value.

    All generated LHC points are evaluated through the shared tracker so the
    initial design accounting matches RBFOpt, then feasible starts are ranked
    for the DSDA descent run.
    """
    return rank_observed_starts(
        starting_points, tracked_objective, penalty=PENALTY
    )


def run_column_dsda(
    seed=DEFAULT_SEED,
    n_starts=3,
    max_evaluations=DEFAULT_MAX_EVALUATIONS,
    diagonal=True,
    tie_break="first",
    verbose=False,
    starting_points=None,
    improvement_abs_tol=IMPROVEMENT_ABS_TOL,
):
    """Run DSDA on the column case from the best feasible LHC start."""
    validate_tolerances(1e-12, improvement_abs_tol)
    if starting_points is None:
        starting_points = generate_lhc_starting_points(
            n_dims=2,
            n_points=n_starts,
            lb=LOWER_BOUNDS,
            ub=UPPER_BOUNDS,
            seed=seed,
        )
    starting_points = validate_design(
        starting_points, LOWER_BOUNDS, UPPER_BOUNDS, n_starts, max_evaluations,
    )
    domain = box_membership(LOWER_BOUNDS, UPPER_BOUNDS)
    tracked_objective = ObservedObjective(column_objective, penalty=PENALTY, legacy=improvement_abs_tol is None)
    start_time = time.perf_counter()
    (
        selected_start,
        selected_start_value,
        feasible_start_values,
        starting_point_values,
    ) = choose_best_feasible_start(
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
            csv_path="/column/case/no-csv.csv",
            start_point=selected_start,
            diagonal=diagonal,
            maximize=False,
            tie_break=tie_break,
            verbose=verbose,
            max_points_explored=remaining_budget,
            grid=domain,
            tracked_objective=tracked_objective,
            start_value=selected_start_value,
            improvement_abs_tol=improvement_abs_tol,
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
        csv_name=COLUMN_CSV_NAME,
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
        initial_evals=len(starting_point_values),
        adaptive_evals=max(0, tracked_objective.call_count - len(starting_point_values)),
        unique_evals=tracked_objective.unique_evaluation_count,
        solver_iterations=(
            0 if run_result is None else run_result["major_iterations"]
        ),
    )
    result = {
        "case_name": "column",
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
    add_target_report(result, tracked_objective.observed_incumbent, KNOWN_BEST_VALUE)
    return result


def main(output_path=None, **kwargs):
    """Run the column DSDA case and optionally save one result record."""
    result = run_column_dsda(**kwargs)
    if output_path is not None:
        save_results_csv([result["result_record"]], Path(output_path))

    print("Column DSDA run completed.")
    print("Starting points:", result["starting_points"])
    print("Feasible starting points:", result["feasible_start_values"])
    print("Selected start:", result["selected_start"])
    print("Best objective value found:", result["best_value"])
    print("At lattice point:", result["best_point"])
    return result


def parse_args():
    """Parse command-line arguments for running the column DSDA case."""
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
