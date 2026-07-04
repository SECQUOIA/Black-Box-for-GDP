# RBFopt_Test

RBFopt_Test is a research and testing repository for derivative-free
optimization case studies. It focuses on comparing RBFOpt, BAM, and DSDA-style
search procedures over discrete benchmark grids.

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

## Solver Setup for RBFOpt Runs

The RBFOpt batch scripts depend on external BONMIN and IPOPT solver binaries.
Before running `grid_rbfopt.py` or the RBFOpt side of `benchmark.py`, set the
`COIN_BIN` environment variable to the directory containing those executables:

```bash
export COIN_BIN="/path/to/coin/bin"
```

The script expects at least:

- `bonmin`
- `ipopt`

The recommended user-space installation path is conda-forge:

```bash
conda install -c conda-forge coin-or-bonmin ipopt
export COIN_BIN="$(dirname "$(which bonmin)")"
```

Then verify that both solver executables are visible:

```bash
which bonmin
which ipopt
python - <<'PY'
from pyomo.environ import SolverFactory
for name in ("bonmin", "ipopt"):
    solver = SolverFactory(name)
    print(name, solver.available(exception_flag=False), solver.executable())
PY
```

On Ubuntu, `coinor-libbonmin*` apt packages may install Bonmin libraries without
the `bonmin` executable that Pyomo/RBFOpt expects. Use the conda-forge package
above, or otherwise provide a solver binary directory containing both
executables and pass it to `benchmark.py` with `--solver-dir`.

If `COIN_BIN` is unset, `benchmark.py` also checks `PATH`. Solver mode fails
before starting the benchmark when BONMIN or IPOPT cannot be found; pass
`--solver-dir`, pass explicit solver paths, or configure RBFOpt to use a
solver-free global search method.

## Solver Setup for BAM Runs

BAM support is optional. Install the BAM Python wrapper when you want to include
BAM as a separate optimizer in benchmark comparisons:

```bash
python -m pip install -e ".[test,lint,bam]"
```

The packaged `benchmark_grids/` problems are two-dimensional, so BAM can run
them in its free mode. For higher-dimensional cases, point BAM at a local
license file without committing it to the repository:

```bash
export BAM_LICENSE_FILE="/home/bernalde/packages/bamlice.txt"
```

You can also pass the license path directly to the benchmark runner with
`--bam-license-file`. BAM is run as a sibling benchmark method beside DSDA and
RBFOpt; this repository does not call BAM from inside RBFOpt.

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

To run the automated DSDA/RBFOpt head-to-head benchmark on all packaged grids:

```bash
python benchmark.py \
    --methods dsda,rbfopt \
    --seeds 0-9 \
    --n-starts 3 \
    --max-evals 10,30,50,70,100 \
    --grids-dir benchmark_grids \
    --output results
```

The benchmark runner writes a unified CSV such as
`results/benchmark_YYYYMMDD_HHMMSS_ffffff.csv`. Each `--max-evals` value must
be at least `--n-starts` because all shared initial LHC points count toward the
evaluation budget. BAM receives the same pre-evaluated LHC design through its
warm-start data and then spends only the remaining budget on adaptive
evaluations. The CSV includes audit columns for initial evaluations, adaptive
evaluations, unique evaluated points, and solver metadata such as evaluation
count, status, and message when the solver exposes them.

Custom grid directories must contain complete integer lattices: every `(x, y)`
coordinate within the grid's minimum and maximum bounds must be present. The
runner rejects sparse grids before starting the benchmark matrix.

To include BAM in the same benchmark matrix:

```bash
python benchmark.py \
    --methods dsda,rbfopt,bam \
    --seeds 0-9 \
    --n-starts 3 \
    --max-evals 10,30,50,70,100 \
    --grids-dir benchmark_grids \
    --output results \
    --bam-license-file /home/bernalde/packages/bamlice.txt
```

To create the standard benchmark analysis figures and statistics tables from a
benchmark results CSV:

```bash
python benchmark_analysis.py \
    --results-csv results/benchmark_YYYYMMDD_HHMMSS_ffffff.csv \
    --grids-dir benchmark_grids \
    --figure-dir results/figures
```

If `--results-csv` is omitted, `benchmark_analysis.py` uses the newest
`results/benchmark_*.csv` file. The script writes three-method performance and
data profiles, per-grid convergence and winner plots, pairwise Wilcoxon tables,
and Friedman/Nemenyi comparisons under `results/figures/`.

Every `csv_name` in the results file must have a matching grid CSV under
`--grids-dir`; analysis stops rather than inventing an optimum or dimension for
missing metadata. Convergence averages carry the last incumbent from runs that
terminate early through the selected evaluation budget. Wilcoxon and Friedman
p-values are Holm-Bonferroni corrected across the reported comparisons and
budget levels.

For extracted process case studies, run the DSDA and RBFOpt modules directly:

```bash
python -m case_studies.column_dsda --seed 1 --n-starts 3 --max-evaluations 16
python -m case_studies.column_rbfopt --seed 1 --n-starts 3 --max-evaluations 16
```

The column, CSTR, small-batch, and dynamic case studies also provide BAM
runners with the same shared LHC initialization pattern:

```bash
python -m case_studies.column_bam --seed 1 --n-starts 3 --max-evaluations 16
python -m case_studies.cstr_bam --grid-size 7 --seed 0 --n-starts 3 --max-evaluations 10
python -m case_studies.small_batch_bam --seed 0 --n-starts 3 --max-evaluations 10
python -m case_studies.dynamic_bam --seed 0 --n-starts 3 --max-evaluations 12
```

The case-study RBFOpt runners accept the same solver configuration pattern as
`grid_rbfopt.py`. Set `COIN_BIN` or pass `--solver-dir` to a directory
containing `bonmin` and `ipopt`; for examples that use sampling, such as the
small-batch runner, solver paths can be omitted unless you switch the global
search method back to a solver-backed mode. Case-study BAM runners accept
`--bam-license-file` and default to `BAM_LICENSE_FILE` when it is set.

## Benchmark Overview

The `benchmark_grids/` directory contains normalized benchmark grids stored as
CSV files. These grids are used by the DSDA, RBFOpt, and BAM utilities to
compare search behavior on discrete lattice problems. The notebooks in the
repository build on these datasets to document selected case studies and visual
results.

## Repository Map

- `grid_dsda.py`: DSDA-style search utilities for precomputed CSV grids.
- `grid_rbfopt.py`: RBFOpt wrapper utilities for grid-based objective
  functions.
- `benchmark.py`: automated benchmark runner with DSDA, RBFOpt, and BAM as
  separate methods using shared Latin Hypercube initialization and unified CSV
  output.
- `benchmark_analysis.py`: reusable analysis and plotting helpers for the
  benchmark results CSV, plus a CLI for saving figures and statistics tables.
- `benchmark_grids/`: normalized benchmark grid data and notes about data provenance.
- `case_study_data/`: completed enumeration CSV data for process case studies,
  grouped by column, CSTR, and small-batch examples.
- `tests/`: regression tests for the grid-loading and search helper modules.
- `scripts/`: utility scripts for generating visual examples and report
  figures, including `create_rbfopt_example.py` for producing a GIF that
  illustrates the concept of derivative-free optimization on an integer
  lattice for presentation and teaching materials.
- `gif/`: generated visualizations from optimization case studies.
- `*.ipynb`: notebooks used to run and inspect optimization case studies.

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
python -m ruff check benchmark.py benchmark_analysis.py grid_dsda.py grid_rbfopt.py case_studies tests scripts
```

## License

This project is distributed under the MIT License. See `LICENSE` for the full
license text.
