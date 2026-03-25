# QHDOPT Benchmark Data and Pseudo-LDSDA Search

## Scope
This directory contains precomputed benchmark grids and lightweight documentation
for the CSV-driven pseudo-LDSDA experiments in this repository.

The current `qhdopt_gdp.py` implementation works directly on the normalized CSV
files stored in `qhdopt/`. It does not build Pyomo GDP models, and it does not
implement the Quantum Hamiltonian Descent (QHD) algorithm itself.

## Data Files
Each CSV file stores a normalized objective grid with the columns
`Point`, `x`, `y`, and `z_norm`.

- `Point`: string representation of the lattice point, retained intentionally for readability and traceability in the CSV files
- `x`, `y`: integer lattice indices
- `z_norm`: normalized objective value at that lattice point

The pseudo-LDSDA code uses `x`, `y`, and `z_norm` for loading and lookup. The
`Point` column is kept in the datasets on purpose and is not being removed.

The current benchmark grids are 31 x 31 and use indices `0, ..., 30` in each
coordinate.

## Search Procedure
`qhdopt_gdp.py` runs a pseudo-LDSDA search on one CSV grid at a time.

1. Load the selected grid from CSV.
2. Choose one or more starting points on the lattice.
3. Evaluate the 4-neighborhood or 8-neighborhood around the current point.
4. Select an improving neighbor and define the search direction.
5. Continue line search along that direction until improvement stops or the
   trial point leaves the grid.
6. Restart neighborhood search from the last improving point.

The module also includes a helper routine that ranks several starting points by
initial objective value before running the search from best to worst.

## Reference
The benchmark grids used here are adapted from benchmark examples listed on:
[Quantum Hamiltonian Descent - Nonconvex 2D](https://jiaqileng.github.io/quantum-hamiltonian-descent/nonconvex2d.html)

That reference is used here as a source for the benchmark test set. The search
code in this repository is a discrete pseudo-LDSDA procedure over precomputed
CSV data.

## Usage Notes
- `load_grid_csv` validates the CSV schema and returns both the DataFrame and a
  dictionary lookup keyed by `(x, y)`.
- `ldsda_from_csv` runs one pseudo-LDSDA search from a single starting point.
- `run_ldsda_from_best_starting_points` ranks starting points by initial value
  and runs the search from best to worst.
