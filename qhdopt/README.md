# QHDOPT Benchmark Data and DSDA-Style Search

## Scope
This directory contains precomputed benchmark grids and lightweight documentation
for the CSV-driven DSDA-style experiments in this repository.

The current `grid_dsda.py` implementation works directly on the normalized CSV
files stored in `qhdopt/`. It does not build Pyomo GDP models, and it does not
implement the Quantum Hamiltonian Descent (QHD) algorithm itself.

## Data Files
Each CSV file stores a normalized objective grid with the columns
`Point`, `x`, `y`, and `z_norm`.

- `Point`: string representation of the lattice point, retained intentionally for readability and traceability in the CSV files
- `x`, `y`: integer lattice indices
- `z_norm`: normalized objective value at that lattice point

The DSDA-style code in `grid_dsda.py` uses `x`, `y`, and `z_norm` for loading
and lookup. The `Point` column is kept in the datasets on purpose and is not
being removed.

The current benchmark grids are 31 x 31 and use indices `0, ..., 30` in each
coordinate.

## Search Procedure
`grid_dsda.py` runs a DSDA-style search on one CSV grid at a time.

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
code in this repository is a discrete DSDA-style procedure over precomputed
CSV data.

### License and data usage
The above web page is the authoritative source for the original benchmark
problems. Users of this repository should consult that reference (and any
associated project pages or repositories) for the applicable license and data
usage terms. The CSV grids in this directory are provided solely for research
and experimental benchmarking purposes and should be redistributed or reused
only in ways that are compatible with the licensing and usage terms of the
original Quantum Hamiltonian Descent benchmark materials.

### Adaptation details
The CSV grids in `qhdopt/` are not direct copies of any files from the linked
reference. Each benchmark surface is sampled on a 31 x 31 integer lattice
(`x, y in {0, ..., 30}`) and min-max normalized per grid so that
`z_norm in [0, 1]` (0 = best, 1 = worst). Non-finite rows are dropped before
normalization. No additional smoothing or modification is applied.

## Usage Notes
- `load_grid_csv` validates the CSV schema and returns both the DataFrame and a
  dictionary lookup keyed by `(x, y)`.
- `z_norm` is treated as a precomputed input column; `grid_dsda.py` does not
  regenerate the normalization from raw objective values.
- `dsda_from_csv` runs one DSDA search from a single starting point.
- `run_dsda_from_best_starting_points` ranks starting points by initial value
  and runs the search from best to worst.
- `grid_rbfopt.py` wraps RBFOpt for black-box optimization on the same CSV
  grids, using `make_obj_funct` to create per-grid objective callbacks.
