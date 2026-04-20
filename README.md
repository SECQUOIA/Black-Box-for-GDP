# RBFopt_Test

RBFopt_Test is a research and testing repository for derivative-free
optimization case studies. It focuses on comparing RBFOpt-based optimization
with DSDA-style search procedures over discrete benchmark grids.

## Project Purpose

The goal of this repository is to organize scripts, notebooks, benchmark data,
and visual outputs used to document selected optimization case studies on
grid-based test problems. The repository is intended for regression testing and
documentation of workflows involving RBFOpt and related discrete search methods.

## Repository Map

- `grid_dsda.py`: DSDA-style search utilities for precomputed CSV grids.
- `grid_rbfopt.py`: RBFOpt wrapper utilities for grid-based objective
  functions.
- `qhdopt/`: normalized benchmark grid data and notes about data provenance.
- `tests/`: regression tests for the grid-loading and search helper modules.
- `gif/`: generated visualizations from optimization runs.
- `*.ipynb`: notebooks used to run and inspect optimization case studies.
- `compl_enum_*.csv`: completed enumeration data from benchmark case studies.

## License

This project is distributed under the MIT License. See `LICENSE` for the full
license text.
