"""RBFOpt runner for the distillation column case study."""

import argparse
import math
import os
import time
from contextlib import nullcontext
from pathlib import Path

import numpy as np

from instrumentation import TrackedObjective, make_result_record, save_results_csv

from .bam_common import suppress_solver_output
from .column_case import (
    COLUMN_CSV_NAME,
    DEFAULT_MAX_EVALUATIONS,
    KNOWN_BEST_POINT,
    KNOWN_BEST_VALUE,
    LOWER_BOUNDS,
    UPPER_BOUNDS,
    VAR_TYPES,
    column_objective,
)
from .common import generate_lhc_starting_points


DEFAULT_SEED = 1


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
    Resolve BONMIN and IPOPT executable paths for the column RBFOpt run.

    Explicit solver paths win. If they are omitted, ``solver_dir`` is used.
    When ``solver_dir`` is omitted too, the ``COIN_BIN`` environment variable is
    used if present.
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


def run_column_rbfopt(
    seed=DEFAULT_SEED,
    n_starts=3,
    max_evaluations=DEFAULT_MAX_EVALUATIONS,
    solver_dir=None,
    minlp_solver_path="",
    nlp_solver_path="",
    algorithm="MSRSM",
    rbf="auto",
    global_search_method="solver",
    rbfopt_module=None,
    verbose=False,
):
    """
    Run RBFOpt on the column case with shared, explicit LHC initial points.

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
        n_dims=2,
        n_points=n_starts,
        lb=LOWER_BOUNDS,
        ub=UPPER_BOUNDS,
        seed=seed,
    )
    init_node_pos = np.asarray(starting_points, dtype=float)
    tracked_objective = TrackedObjective(column_objective)

    black_box = rbfopt_module.RbfoptUserBlackBox(
        2,
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
        rand_seed=seed,
    )
    output_context = nullcontext() if verbose else suppress_solver_output()
    with output_context:
        start_time = time.perf_counter()
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
        wall_time_s = time.perf_counter() - start_time
    best_point_rounded = [int(round(value)) for value in best_point]
    found_optimum = (
        list(KNOWN_BEST_POINT) == best_point_rounded
        and math.isclose(best_value, KNOWN_BEST_VALUE, abs_tol=1e-12, rel_tol=0.0)
    )

    result_record = make_result_record(
        csv_name=COLUMN_CSV_NAME,
        method="RBFOpt",
        seed=seed,
        n_starts=n_starts,
        max_evals=max_evaluations,
        best_value=best_value,
        best_point=best_point_rounded,
        total_evals=tracked_objective.call_count,
        wall_time_s=wall_time_s,
        found_optimum=found_optimum,
        incumbent_trajectory=tracked_objective.incumbent_trajectory,
        initial_evals=len(starting_points),
        adaptive_evals=max(0, tracked_objective.call_count - len(starting_points)),
        unique_evals=tracked_objective.unique_evaluation_count,
        solver_evalcount=evalcount,
        solver_iterations=itercount,
    )
    return {
        "case_name": "column",
        "starting_points": starting_points,
        "best_value": best_value,
        "best_point": best_point_rounded,
        "iterations": itercount,
        "evalcount": evalcount,
        "fast_evalcount": fast_evalcount,
        "tracked_evals": tracked_objective.call_count,
        "wall_time_s": wall_time_s,
        "incumbent_trajectory": tracked_objective.incumbent_trajectory,
        "objective_wall_times": tracked_objective.wall_times,
        "minlp_solver_path": minlp_solver_path,
        "nlp_solver_path": nlp_solver_path,
        "result_record": result_record,
    }


def main(output_path=None, **kwargs):
    """Run the column RBFOpt case and optionally save one result record."""
    result = run_column_rbfopt(**kwargs)
    if output_path is not None:
        save_results_csv([result["result_record"]], Path(output_path))

    print("Column RBFOpt run completed.")
    print("Starting points:", result["starting_points"])
    print("Best objective value found:", result["best_value"])
    print("At lattice point:", result["best_point"])
    return result


def parse_args():
    """Parse command-line arguments for running the column RBFOpt case."""
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
    parser.add_argument("--algorithm", default="MSRSM")
    parser.add_argument("--rbf", default="auto")
    parser.add_argument("--global-search-method", default="solver")
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
        solver_dir=args.solver_dir,
        minlp_solver_path=args.minlp_solver_path,
        nlp_solver_path=args.nlp_solver_path,
        algorithm=args.algorithm,
        rbf=args.rbf,
        global_search_method=args.global_search_method,
        verbose=args.verbose,
    )
