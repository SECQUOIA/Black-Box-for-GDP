"""RBFOpt runner for the small-batch case study."""

import argparse
import math
import os
from pathlib import Path

import numpy as np

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
    VAR_TYPES,
    small_batch_objective,
)


DEFAULT_SEED = 0


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
    Resolve BONMIN and IPOPT executable paths for the small-batch RBFOpt run.

    The default notebook settings use sampling for the global search, but we
    still accept solver paths for parity with the other case-study runners.
    """
    if minlp_solver_path and nlp_solver_path:
        return str(minlp_solver_path), str(nlp_solver_path)

    solver_dir = solver_dir or os.environ.get("COIN_BIN", "").strip()
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


def run_small_batch_rbfopt(
    seed=DEFAULT_SEED,
    n_starts=3,
    max_evaluations=DEFAULT_MAX_EVALUATIONS,
    solver_dir=None,
    minlp_solver_path="",
    nlp_solver_path="",
    algorithm="Gutmann",
    rbf="auto",
    global_search_method="sampling",
    rbfopt_module=None,
):
    """
    Run RBFOpt on the small-batch case with explicit LHC initial points.

    ``rbfopt_module`` is injectable so tests can verify RBFOpt wiring without
    requiring external solver binaries.
    """
    if rbfopt_module is None:
        import rbfopt as rbfopt_module

    minlp_solver_path, nlp_solver_path = resolve_solver_paths(
        solver_dir=solver_dir,
        minlp_solver_path=minlp_solver_path,
        nlp_solver_path=nlp_solver_path,
    )

    starting_points = generate_lhc_starting_points(
        n_dims=3,
        n_points=n_starts,
        lb=LOWER_BOUNDS,
        ub=UPPER_BOUNDS,
        seed=seed,
    )
    init_node_pos = np.asarray(starting_points, dtype=float)
    tracked_objective = TrackedObjective(
        lambda point: small_batch_objective(
            point,
            feasible_objectives=SMALL_BATCH_FEASIBLE_OBJECTIVES,
        )
    )

    black_box = rbfopt_module.RbfoptUserBlackBox(
        3,
        LOWER_BOUNDS,
        UPPER_BOUNDS,
        VAR_TYPES,
        tracked_objective,
    )
    settings = rbfopt_module.RbfoptSettings(
        max_evaluations=max_evaluations,
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

    best_value, best_point, itercount, evalcount, fast_evalcount = (
        algorithm_instance.optimize()
    )
    best_point_rounded = [int(round(value)) for value in best_point]
    found_optimum = (
        list(KNOWN_BEST_POINT) == best_point_rounded
        and math.isclose(best_value, KNOWN_BEST_VALUE, abs_tol=1e-12, rel_tol=0.0)
    )

    result_record = make_result_record(
        csv_name=SMALL_BATCH_CSV_NAME,
        method="RBFOpt",
        seed=seed,
        n_starts=n_starts,
        max_evals=max_evaluations,
        best_value=best_value,
        best_point=best_point_rounded,
        total_evals=tracked_objective.call_count,
        wall_time_s=sum(tracked_objective.wall_times),
        found_optimum=found_optimum,
        incumbent_trajectory=tracked_objective.incumbent_trajectory,
    )
    return {
        "case_name": "small_batch",
        "starting_points": starting_points,
        "best_value": best_value,
        "best_point": best_point_rounded,
        "iterations": itercount,
        "evalcount": evalcount,
        "fast_evalcount": fast_evalcount,
        "tracked_evals": tracked_objective.call_count,
        "incumbent_trajectory": tracked_objective.incumbent_trajectory,
        "objective_wall_times": tracked_objective.wall_times,
        "minlp_solver_path": minlp_solver_path,
        "nlp_solver_path": nlp_solver_path,
        "result_record": result_record,
    }


def main(output_path=None, **kwargs):
    """Run the small-batch RBFOpt case and optionally save one result record."""
    result = run_small_batch_rbfopt(**kwargs)
    if output_path is not None:
        save_results_csv([result["result_record"]], Path(output_path))

    print("Small-batch RBFOpt run completed.")
    print("Starting points:", result["starting_points"])
    print("Best objective value found:", result["best_value"])
    print("At lattice point:", result["best_point"])
    return result


def parse_args():
    """Parse command-line arguments for running the small-batch RBFOpt case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--n-starts", type=int, default=3)
    parser.add_argument("--max-evaluations", type=int, default=DEFAULT_MAX_EVALUATIONS)
    parser.add_argument(
        "--solver-dir",
        default=None,
        help="Directory containing bonmin and ipopt, e.g. /Users/.../ampl.macos64",
    )
    parser.add_argument("--minlp-solver-path", default="")
    parser.add_argument("--nlp-solver-path", default="")
    parser.add_argument("--algorithm", default="Gutmann")
    parser.add_argument("--rbf", default="auto")
    parser.add_argument("--global-search-method", default="sampling")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        output_path=args.output,
        seed=args.seed,
        n_starts=args.n_starts,
        max_evaluations=args.max_evaluations,
        solver_dir=args.solver_dir,
        minlp_solver_path=args.minlp_solver_path,
        nlp_solver_path=args.nlp_solver_path,
        algorithm=args.algorithm,
        rbf=args.rbf,
        global_search_method=args.global_search_method,
    )
