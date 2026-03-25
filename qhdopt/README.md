# QHDOPT Benchmark Data and DSDA-Style Search

## Scope
This directory contains precomputed benchmark grids and lightweight documentation
for the CSV-driven DSDA-style experiments in this repository.

The current `qhdopt_gdp.py` implementation works directly on the normalized CSV
files stored in `qhdopt/`. It does not build Pyomo GDP models, and it does not
implement the Quantum Hamiltonian Descent (QHD) algorithm itself.

## Data Files
Each CSV file stores a normalized objective grid with the columns
`Point`, `x`, `y`, and `z_norm`.

- `Point`: string representation of the lattice point, retained intentionally for readability and traceability in the CSV files
- `x`, `y`: integer lattice indices
- `z_norm`: normalized objective value at that lattice point

The DSDA-style code uses `x`, `y`, and `z_norm` for loading and lookup. The
`Point` column is kept in the datasets on purpose and is not being removed.

The current benchmark grids are 31 x 31 and use indices `0, ..., 30` in each
coordinate.

## Search Procedure
`qhdopt_gdp.py` runs a DSDA-style search on one CSV grid at a time.

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
reference. Instead, each benchmark surface is sampled on a regular integer
lattice and normalized into the following schema:

- The domain is discretized on a 31 × 31 lattice with indices `x, y ∈ {0, …, 30}`.
- `x` and `y` are integer lattice indices; any mapping from indices to the
  continuous coordinates used in the original reference is handled in the code
  that generated these CSVs and is not required for running the DSDA-style
  normalization is performed independently for each grid using a min–max
  scaling to the closed interval `[0, 1]`:

  - Let `f(x, y)` be the original objective value at lattice point `(x, y)` and
    let `f_min` and `f_max` be the minimum and maximum of `f` over all points in
    that grid, after dropping any rows with non-finite values (`NaN`, `+/-inf`).
  - If `f_max > f_min`, the normalized value is

    `z_norm(x, y) = (f(x, y) - f_min) / (f_max - f_min)`.

    This guarantees `z_norm ∈ [0, 1]`, with `z_norm = 0.0` at the smallest
    (best) objective value and `z_norm = 1.0` at the largest (worst) objective
    value. The pseudo-LDSDA search therefore treats **smaller** `z_norm` values
    as preferable, and any ties in the original objective are preserved as
    identical `z_norm` values.
  - If `f_max == f_min` (a degenerate surface where all objective values are
    identical), all points in the grid are assigned `z_norm = 0.0`.
  - No additional clipping or rounding is applied beyond the finite precision of
    the CSV representation.
- `z_norm` stores a precomputed, per-grid normalized objective value at each
  lattice point. The normalization is performed during dataset generation and
  written directly into the CSV files. The DSDA-style code reads `z_norm` as-is
  and treats smaller `z_norm` values as better when minimizing the benchmark
  grids.

These adaptation steps are limited to discretization and normalization; no
additional smoothing, noise injection, or qualitative modification of the
benchmark surfaces has been intentionally introduced.

## Usage Notes
- `load_grid_csv` validates the CSV schema and returns both the DataFrame and a
  dictionary lookup keyed by `(x, y)`.
- `z_norm` is treated as a precomputed input column; `qhdopt_gdp.py` does not
  regenerate the normalization from raw objective values.
- `dsda_from_csv` runs one DSDA search from a single starting point.
- `run_dsda_from_best_starting_points` ranks starting points by initial value
  and runs the search from best to worst.
