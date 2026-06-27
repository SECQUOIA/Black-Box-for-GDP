"""BAM runner for the CSTR case study."""

import argparse
import math
import os
from pathlib import Path

from instrumentation import make_result_record, save_results_csv

from .bam_common import run_bam_with_initial_design
from .common import generate_lhc_starting_points
from .cstr_case import (
    DEFAULT_GRID_SIZE,
    DEFAULT_MAX_EVALUATIONS,
    LOWER_BOUNDS,
    cstr_objective,
    load_cstr_case_data,
)
from .cstr_rbfopt import DEFAULT_SEED


def run_cstr_bam(
    grid_size=DEFAULT_GRID_SIZE,
    seed=DEFAULT_SEED,
    n_starts=3,
    max_evaluations=DEFAULT_MAX_EVALUATIONS,
    bam_license_file=None,
    bam_module=None,
    verbose=False,
):
    """Run BAM on the CSTR case from shared, pre-evaluated LHC points."""
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
    result = run_bam_with_initial_design(
        objective=lambda point: cstr_objective(
            point,
            grid_size=grid_size,
            feasible_objectives=feasible_objectives,
        ),
        lower_bounds=LOWER_BOUNDS,
        upper_bounds=upper_bounds,
        starting_points=starting_points,
        max_evaluations=max_evaluations,
        bam_license_file=bam_license_file,
        bam_module=bam_module,
        verbose=verbose,
    )
    found_optimum = (
        list(known_best_point) == result["best_point"]
        and math.isclose(
            result["best_value"], known_best_value, abs_tol=1e-12, rel_tol=0.0
        )
    )
    result_record = make_result_record(
        csv_name=case_data["csv_name"],
        method="BAM",
        seed=seed,
        n_starts=n_starts,
        max_evals=max_evaluations,
        best_value=result["best_value"],
        best_point=result["best_point"],
        total_evals=result["tracked_evals"],
        wall_time_s=result["wall_time_s"],
        found_optimum=found_optimum,
        incumbent_trajectory=result["incumbent_trajectory"],
        initial_evals=result["initial_evals"],
        adaptive_evals=result["adaptive_evals"],
        unique_evals=result["unique_evals"],
        solver_evalcount=result["evalcount"],
        solver_iterations=result["iterations"],
        solver_status=result["status"],
        solver_message=result["message"],
    )
    result.update(
        {
            "case_name": "cstr",
            "grid_size": int(grid_size),
            "result_record": result_record,
        }
    )
    return result


def main(output_path=None, **kwargs):
    """Run the CSTR BAM case and optionally save one result record."""
    result = run_cstr_bam(**kwargs)
    if output_path is not None:
        save_results_csv([result["result_record"]], Path(output_path))

    print("CSTR BAM run completed.")
    print("Grid size:", result["grid_size"])
    print("Starting points:", result["starting_points"])
    print("Best objective value found:", result["best_value"])
    print("At lattice point:", result["best_point"])
    return result


def parse_args():
    """Parse command-line arguments for running the CSTR BAM case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid-size", type=int, default=DEFAULT_GRID_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--n-starts", type=int, default=3)
    parser.add_argument("--max-evaluations", type=int, default=DEFAULT_MAX_EVALUATIONS)
    parser.add_argument(
        "--bam-license-file",
        default=os.environ.get("BAM_LICENSE_FILE", ""),
        help="Path to a BAM license file. Defaults to BAM_LICENSE_FILE.",
    )
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
        bam_license_file=args.bam_license_file,
        verbose=args.verbose,
    )
