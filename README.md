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

To persist every evaluated integer point for Column, CSTR, Small Batch, and
Dynamic, use `case_study_benchmark.py --trace-evaluations`. See the
[evaluation tracing and GDP timing workflow](docs/evaluation_tracing.md) for
the original-start audit, Dantzig rerun command, resume support, and point-cost
inventory.
The [completed 417-run coordinate audit](results/process_evaluation_traces_20260917/README.md)
includes the evaluation CSVs, original trace bundle, and GDP model connection probes.

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
data profiles, per-grid convergence and winner plots, TTS99 comparisons,
pairwise Wilcoxon tables, and Friedman/Nemenyi comparisons under
`results/figures/`.

TTS99 estimates the time required for repeated independent runs to reach a 99%
probability of success. For hit rate `p`, the analysis uses
`runs_99 = ceil(log(0.01) / log(1 - p))` and
`TTS99 = runs_99 * median_wall_time_s`. A hit is an exact global-optimum event
recorded by `found_optimum`; the per-run time is the median across seeds for the
same problem, method, initialization size, and evaluation budget. A hit rate of
one requires one run. A zero hit rate is reported as infinite TTS99 so failed
configurations remain visible in both `tts99_summary.csv` and the generated
figure. The comparison figure's black median marker includes infinite TTS99
groups; when the median is infinite, the figure labels it explicitly. Method
labels also show the number of seed runs contributing to each problem group,
or a range when group sizes differ.

The four-method Grid comparison generated by `fmqa_compare.py` includes DSDA,
RBFOpt, BAM 5.0.0 and FMQA-SA. Its TTS99 hits are recomputed with the same
`1e-5 * max(1, abs(target))` tolerance as its performance profiles, rather than
using historical exact-hit flags. See the [Grid comparison guide](docs/fmqa_grids.md)
for the plots and reproduction commands.

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
containing `bonmin` and `ipopt`. The small-batch default combines the Gutmann
algorithm with sampling, but Gutmann still uses Bonmin for its target-value
subproblem, so its solver paths cannot be omitted. Case-study BAM runners
accept `--bam-license-file` and default to `BAM_LICENSE_FILE` when it is set.

To collect the reproducible three-method process case-study matrix in one
audited CSV, run:

```bash
python case_study_benchmark.py \
    --cases column,cstr,small_batch,dynamic \
    --methods dsda,rbfopt,bam \
    --seeds 0-9 \
    --column-seeds 1-9 \
    --n-starts 3 \
    --solver-dir "$COIN_BIN" \
    --bam-license-file "$BAM_LICENSE_FILE" \
    --max-run-seconds 1800 \
    --output results/case_studies
```

The default matrix uses budget 16 for column, budget 10 for small-batch,
budgets 12, 15, 20, 30, 37, and 50 for dynamic, and CSTR grid sizes 5, 10, 15,
20, 25, and 30. CSTR budgets are scaled as
`ceil(10 * grid_size / 7)`. Column uses seeds 1-9 because seed 0 does not
produce a feasible DSDA initial point. The runner writes all methods and cases
to a single timestamped `process_case_studies_*.csv` file using the unified
audit schema from `instrumentation.py`. The complete default plan contains 139
case/seed/budget configurations and 417 method runs. Duplicate cases, methods,
seeds, and budgets are rejected so every planned run has a unique identifier.

Each completed method run is atomically checkpointed to a neighboring
`*.partial.csv`, with a paired running manifest. If a solver fails or the
process is interrupted, rerun the same protocol options with `--resume` and
set `--output` to the checkpoint's corresponding explicit final CSV path; for
example, resume `process_case_studies_<timestamp>.partial.csv` with
`--output results/case_studies/process_case_studies_<timestamp>.csv`. The
runner validates the checkpoint before skipping its completed prefix.
Checkpoint updates pass through a neighboring `*.partial.pending.csv` pair;
after an interruption, `--resume` selects and promotes the newest complete,
checksum-valid generation. These pending files are internal recovery artifacts
and should not be edited or analyzed directly. Final CSV/manifest promotion is
also recoverable: if it is interrupted between the two atomic replacements,
rerun the same command with `--resume` and the explicit final CSV path.
The planned matrix and result-affecting protocol options must remain identical
when resuming. Execution-only `--max-run-seconds` and `--verbose` may change;
the manifest records their values and the completed-row boundary for every
attempt. A deterministic non-timeout failure must be corrected without
changing hashed source/data inputs or the planned matrix; narrowing the matrix
is intentionally rejected, so a source-level fix requires a new benchmark run.
`--max-run-seconds` supplies a best-effort POSIX wall-time deadline for each
method run. An explicit completed CSV is never replaced unless `--overwrite`
is supplied; timestamped directory output naturally chooses a new filename.
The completed manifest records the protocol, per-attempt execution context,
software/source identity, input and initial-design hashes, row count, and
output checksum without recording a BAM license path. Git commit, branch, and
dirty-state metadata and the operating-system kernel release are informational
during resume; Python and dependency versions, platform system/machine, and
source/data/design hashes remain strict.

Wall time starts after case-data loading, dependency resolution, and generation
of the shared LHC design. It includes the initial black-box evaluations and the
optimizer execution; for RBFOpt it also includes construction of the algorithm
instance. Evaluation counts are the primary cross-method work measure.
Iteration counts are retained as method telemetry, but DSDA, RBFOpt, and BAM do
not define an iteration equivalently.

After a benchmark completes, generate the Issue #18 summary tables and static
figures from its audited CSV:

```bash
python case_study_analysis.py \
    --results-csv results/case_studies/process_case_studies_YYYYMMDD_HHMMSS_ffffff.csv \
    --output-dir results/case_studies/analysis
```

This writes `case_study_summary.csv`,
`evaluation_convergence_summary.csv`, `case_study_overview.png`, and
`evaluation_convergence.png`. The overview includes exact-optimum hit rate,
normalized gap, wall time, TTS99, total/unique/adaptive evaluations, and a
clearly qualified method-specific iteration panel. Convergence is indexed by
black-box evaluation rather than solver iteration. A run with no finite
incumbent yet contributes an infinite, censored gap instead of disappearing
from the median denominator. The analysis verifies a paired completed manifest,
CSV checksum, and row count when present, and prints a warning for a legacy
unmanifested CSV. New structured CSV values use strict JSON (`null` for a
leading non-finite incumbent); the analysis also accepts legacy
`NaN`/`Infinity` traces and explicitly marks an all-non-finite trace as a
terminal-only fallback instead of reconstructing progress.

The completed Dantzig run for [Issue #18](https://github.com/SECQUOIA/RBFopt_Test/issues/18)
is available in [the case-study results bundle](results/case_studies/dantzig_20260910/README.md).
It contains all 417 audited method runs, the original manifest, regenerated
three-method static figures, summary tables, and the exact regeneration command.

Time performance profiles, successful completions versus seconds, and
time/evaluation/iteration tradeoffs are included in the
[Dantzig grid results](results/grid_benchmarks/dantzig_20260910/README.md) and
[process-case bundle](results/case_studies/dantzig_20260910/README.md).
`timing_analysis.py` can read the archived ZIP directly. The profiles use
successful runs' recorded completion times and retain failures in the
denominator; first-hit timestamps were not recorded. Each bundle documents
the tolerance, interpretation, source tables, and regeneration command.

[Updated three-method profiles with BAM 5.0.0](results/bam_20260916/README.md)
use the September 16 BAM rerun with the original DSDA/RBFOpt observations.
The bundle includes replacement grid and process-case time-profile figures,
their source tables, and a regeneration script. The earlier BAM 4.1.1 bundles
remain available for comparison.

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
- `case_study_benchmark.py`: resumable, audited aggregate runner for the four
  process case studies and all three methods.
- `case_study_analysis.py`: reproducible process-case summary tables and static
  BAM/DSDA/RBFOpt comparison figures.
- `timing_analysis.py`: completion-time performance profiles and time/work
  tradeoffs from grid or process CSVs, including direct ZIP input.
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
workflow. Existing notebook/GIF trajectories do not include BAM and are
qualitative demonstrations, not evidence for the three-method comparison; use
the audited static outputs from `case_study_analysis.py` for Issue #18.

## Original GDP Models

Use `python -m gdp_models.dantzig setup` to initialize the original sources.
The default matrix includes Column, CSTR30, Small Batch and Dynamic: 593
external integer candidates per solver. Run through the Python entry point;
server shell wrappers are local files and are not required.
See [server setup, resume, and download instructions](docs/gdp_dantzig.md).

The [Dantzig point timing dataset](results/gdp_point_timings_20260922/README.md)
contains IPOPT, IPOPTH and CONOPT measurements for these four cases, with the
seven successful CSTR30 IPOPT retries merged by coordinate. Original failures,
retry costs, initialization policies and one-time Dynamic discretization are
preserved separately. CSTR5–25 measurements are excluded from this dataset.

For a full-model comparison of GDPopt RIC/GLOA (IPOPT subproblems) against
Big-M/Hull + BARON with 30-minute limits per instance/method, see the
[Dantzig GDP comparison runner](docs/gdp_comparison.md).
This full-model comparison includes CSTR5/10/15/20/25/30, Column, Dynamic and
Small Batch (36 jobs); the CSTR30-only scope above concerns point NLP timings.
The [current full-GDP results](results/gdp_comparison_20260925/analysis/README.md)
use the September 25 CPU 2 rerun: all 36 saved solutions passed an independent
original-GDP feasibility check. Nine jobs reached the solver time limit.
Three cross-method BARON bound conflicts are flagged explicitly.

The [corrected Dantzig timing comparison](results/fmqa_20260925/analysis/nlp/README.md)
uses the original 556 Dantzig lookup completion times and outcomes. The earlier
Mac-trace-based NLP-inclusive totals and first-hit profiles were withdrawn.
The original DSDA/RBFOpt/BAM records lack complete evaluation coordinates and
first-hit timestamps, so their NLP-inclusive and first-hit times remain missing.
FMQA's available Dantzig traces retain a separate NLP cost table, using only
successful evaluations and zero cost for infeasible lookups under the stated
assumption. No Mac paths or clocks are substituted.
Run `python nlp_cost_analysis.py --output results/new_dantzig_timing_comparison`
to reproduce the corrected figures and tables from the original archives.

The original Column, CSTR, Small Batch, and Dynamic GDP models are now linked
as pinned submodules under `external/`. The optional `gdp_models` package fixes
an integer point, solves its actual NLP, and records preparation and solve
times. Existing lookup benchmarks and their performance profiles still exclude
this NLP cost. See [setup, execution, and timing details](docs/original_gdp_models.md).

To enumerate all external integer candidates for one case, use
`python -m gdp_models.batch --case small_batch --solver ipopt --output-dir results/live_gdp/small_batch_all`.
The batch saves per-point CSV/JSON results and supports `--resume` and
`--dry-run`; see [enumeration options](docs/original_gdp_models.md#enumerate-all-integer-combinations).

## Development Checks

The [current FMQA results and figure index](results/fmqa_20260925/README.md)
use the September 25 reruns: 1,050 Grid runs on CPU 0 and 139 process-case runs
on CPU 4, with different recorded physical cores. Raw archives, comparison
tables, Grid TTS99, timing profiles and NLP-inclusive estimates use these new
measurements. The contaminated September 22 FMQA archives and derived results
have been removed. The full GDPopt/BARON baseline now uses the September 25
CPU 2 rerun, on a different physical core from both FMQA jobs. The contaminated
September 22 GDP comparison archive and its derived results have also been removed.

For FMQA with local simulated annealing, the same original three-point designs
and all 139 process-case conditions, see the
[FMQA-SA Dantzig runner and comparison guide](docs/fmqa_benchmark.md).
This uses pinned `bbo_via_fmqa` sources with a documented NumPy port of its
legacy FM backend, and pairs results with DSDA, RBFOpt and BAM 5.0.0.
The runner ZIP is self-contained; no quantum token or solver license is needed.
For a separate 1,050-run experiment on the 21 QHDOpt-derived grids, use the
[Grid-only FMQA-SA runner](docs/fmqa_grids.md).

Run the current regression tests with:

```bash
python -m pytest tests/ -q
```

Run the basic lint checks used by GitHub Actions with:

```bash
python -m ruff check benchmark.py benchmark_analysis.py case_study_benchmark.py case_study_analysis.py timing_analysis.py grid_dsda.py grid_rbfopt.py instrumentation.py case_studies gdp_models tests scripts
```

## License

This project's code is distributed under the MIT License. See `LICENSE` for
the full license text. External source submodules retain their upstream terms;
see [original GDP source attribution](docs/original_gdp_models.md#original-sources).
