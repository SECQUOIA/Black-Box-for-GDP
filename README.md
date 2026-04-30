# RBFopt_Test

RBFopt_Test is a research and testing repository for derivative-free
optimization case studies. It focuses on comparing RBFOpt-based optimization
with DSDA-style search procedures over discrete benchmark grids.

## Project Purpose

The goal of this repository is to organize scripts, notebooks, benchmark data,
and visual outputs used to document selected optimization case studies on
grid-based test problems. The repository is intended for regression testing and
documentation of workflows involving RBFOpt and related discrete search methods.

## Installation

From a source checkout, install the project and the development tools used in
this repository:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[test,lint]"
```

The core Python dependencies are declared in `pyproject.toml`. The editable
install above is the most convenient option when working on the repository
locally because it keeps the source tree and test commands in sync.

## Solver Setup for `grid_rbfopt.py`

The RBFOpt batch script depends on external BONMIN and IPOPT solver binaries.
Before running `grid_rbfopt.py`, set the `COIN_BIN` environment variable to the
directory containing those executables:

```bash
export COIN_BIN="/path/to/coin/bin"
```

The script expects at least:

- `bonmin`
- `ipopt`

If `COIN_BIN` is unset or points to the wrong location, `grid_rbfopt.py` will
raise an error before starting the optimization runs.

## Usage Examples

For a lightweight DSDA run on one of the benchmark grids:

```python
from grid_dsda import dsda_from_csv

result = dsda_from_csv(
    "benchmark_grids/ackley.csv",
    start_point=(14, 14),
    diagonal=True,
    verbose=False,
)

print(result["best_point"], result["best_value"])
```

To run the full RBFOpt batch script after configuring `COIN_BIN`:

```bash
python grid_rbfopt.py
```

## Benchmark Overview

The `benchmark_grids/` directory contains normalized benchmark grids stored as CSV
files. These grids are used by the DSDA and RBFOpt utilities to compare search
behavior on discrete lattice problems. The notebooks in the repository build on
these datasets to document selected case studies and visual results.

## Repository Map

- `grid_dsda.py`: DSDA-style search utilities for precomputed CSV grids.
- `grid_rbfopt.py`: RBFOpt wrapper utilities for grid-based objective
  functions.
- `benchmark_grids/`: normalized benchmark grid data and notes about data provenance.
- `tests/`: regression tests for the grid-loading and search helper modules.
- `scripts/`: utility scripts for generating visual examples and report
  figures, including `create_rbfopt_example.py` for producing a GIF that
  illustrates the concept of derivative-free optimization on an integer
  lattice for presentation and teaching materials.
- `gif/`: generated visualizations from optimization case studies.
- `*.ipynb`: notebooks used to run and inspect optimization case studies.
- `compl_enum_*.csv`: completed enumeration data from benchmark case studies.

## Visual Example Script

The script `scripts/create_rbfopt_example.py` is a lightweight visualization
helper used to generate an explanatory GIF for content materials. It is meant
to illustrate the derivative-free optimization idea on a simple integer
lattice, rather than serve as part of the main benchmark or regression-testing
workflow.

## Development Checks

Run the current regression tests with:

```bash
python -m pytest tests/ -q
```

Run the basic lint checks used by GitHub Actions with:

```bash
python -m ruff check grid_dsda.py grid_rbfopt.py tests scripts
```

## License

This project is distributed under the MIT License. See `LICENSE` for the full
license text.
