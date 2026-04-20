# RBFopt_Test

Benchmark utilities and notebooks for comparing discrete search methods on
precomputed derivative-free optimization grids.

This repository currently focuses on two lightweight workflows:

- `grid_dsda.py` runs a discrete steepest descent style search directly on CSV
  benchmark grids.
- `grid_rbfopt.py` wraps RBFOpt so the same grids can be optimized with an
  RBF-based black-box optimizer.

The benchmark data in `qhdopt/` contains normalized 31 x 31 integer grids for
two-dimensional nonconvex test functions. See `qhdopt/README.md` for data
format, adaptation notes, and source references.

## Repository Layout

- `grid_dsda.py`: CSV-driven DSDA-style search.
- `grid_rbfopt.py`: RBFOpt wrapper for the same CSV grids.
- `qhdopt/`: normalized benchmark grid data and dataset notes.
- `tests/`: regression tests for the grid modules.
- `*.ipynb`: exploratory notebooks and visual comparisons.
- `gif/`: generated visual assets used by the notebooks and documentation.

## Installation

Create and activate a virtual environment, then install the project in editable
mode with test and notebook dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,dev]"
```

RBFOpt itself is listed as a project dependency. Running `grid_rbfopt.py` also
requires local BONMIN and IPOPT solver binaries.

## Running Tests

```bash
pytest tests/
```

The test suite exercises the Python modules without requiring the full RBFOpt
solver stack to run an optimization job.

## DSDA-Style Grid Search

Run the DSDA-style search over all CSV grids with the default example settings:

```bash
python grid_dsda.py
```

Use the module functions directly for a single grid:

```python
from grid_dsda import dsda_from_csv

result = dsda_from_csv(
    "qhdopt/ackley.csv",
    start_point=(14, 14),
    diagonal=True,
    verbose=False,
)

print(result["best_point"], result["best_value"])
```

## RBFOpt Grid Search

Before running the RBFOpt wrapper, set `COIN_BIN` to the directory containing
the `bonmin` and `ipopt` executables:

```bash
export COIN_BIN=/path/to/coin/bin
python grid_rbfopt.py
```

`grid_rbfopt.py` validates that both solver binaries exist before starting the
batch run. Logs are written under `logs/`.

## Benchmark Data

The CSV files in `qhdopt/` store normalized objective values with columns
`Point`, `x`, `y`, and `z_norm`. The Python modules use the integer lattice
coordinates and normalized objective values directly; they do not regenerate
the underlying continuous benchmark functions.

For details about data provenance, normalization, and usage notes, read
`qhdopt/README.md`.

## License

This project is distributed under the MIT License. See `LICENSE` for the full
license text.
