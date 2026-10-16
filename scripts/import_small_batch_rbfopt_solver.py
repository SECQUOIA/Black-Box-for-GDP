"""Audit the solver-search supplement and retain its immutable Dantzig archive."""

import argparse
from pathlib import Path

from scripts.import_small_batch_full_domain import ROOT, build
import small_batch_rbfopt_solver as experiment

OUTPUT = ROOT / "results/small_batch_rbfopt_solver_20261013"
FILES = ("run.json", "summary.json", "runs.csv", "trajectories.csv", "auxiliary_solver_calls.csv",
         "evaluation_costs.csv", "completion_estimates.csv", "runtime_dfo.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.archive, args.output_dir, experiment=experiment, files=FILES)
