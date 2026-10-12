# Grid GDP benchmark and exhaustive IPOPT point costs

The execution ZIP contains all 21 analytic GDP models, their 31-by-31 reference
CSVs, a full-GDP benchmark driver, and an exhaustive IPOPT point-timing driver.
The grid definition and original analytic objective are unchanged. Default
`run` first measures **20,181 points** (21 × 961), then attempts **105 full-GDP
jobs** (21 × 5 methods). Everything runs sequentially on one selected CPU.

The completed [IPOPT timings](../results/grid_gdp_20261009/README.md),
[original-profile retries](../results/grid_gdp_retry_20261009/README.md) and
[corrected retries](../results/grid_gdp_corrected_20261009/README.md) are already
published. Their result archives retain the executed source snapshots. This
guide describes generating a new execution bundle from the current checkout;
historical reruns use their frozen sources as described below.

## Correct the ten repeated errors from the October 9 retry

Use the retained [corrected retry package](../results/runners/grid_gdp_error_fix.md)
for this historical operation. Its `grid_gdp_error_fix_runner.zip` is published
with the exact source required by the recorded retry's source guard.
The `pyomo610-grid-v1` profile keeps the original analytic formulas, solvers,
CPU, threads and time limits. It changes two Pyomo 6.10.0 processing steps:

- For Camel3, Dropwave and Sum of Squares, restore fixed exponent bounds to
  their exact constant value before FBBT inverse-power propagation. Roundoff
  must not turn a constant integer exponent into a nondegenerate interval.
- For Alpine1/LOA, check the existing finite lower/upper bound convergence
  criterion before generating another OA cut. At the recorded optimum, both
  bounds are already zero and differentiating `abs(0)` is unnecessary.

The corrections are scoped to the worker and restored on exit. Run metadata
and result records explicitly label the changed profile. It is not an
unchanged-process-profile measurement. No CSV lookup replaces an objective;
no smoothing or new optimum initialization is introduced. Existing IPOPT
measurements are reused because the point model and timing code are unchanged.

From this package on Dantzig, inspect the exact ten jobs:

```bash
bash run_grid_gdp_dantzig.sh retry-errors \
  --run-dir /local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdp_benchmark/grid_gdp_retry_all_20261009_153057_czhvd9w7 \
  --retry-fix-profile pyomo610-grid-v1 --dry-run
```

Start those jobs in a new directory (zero point evaluations):

```bash
GRID_GDP_CPU=6 nohup bash run_grid_gdp_dantzig.sh retry-errors \
  --run-dir /local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdp_benchmark/grid_gdp_retry_all_20261009_153057_czhvd9w7 \
  --retry-fix-profile pyomo610-grid-v1 \
  > /local/scratch/a/lee4382/repository/RBFopt_Test/grid_gdp_fixed_retry.log 2>&1 &
tail -f /local/scratch/a/lee4382/repository/RBFopt_Test/grid_gdp_fixed_retry.log
```

This selects Alpine1/LOA and all three GDPopt methods for Camel3, Dropwave and
Sum of Squares. Holder Table misses, timeouts and 32 BARON-unsupported cases
are not errors selected by this command. For unchanged-profile historical
retries, use the `source/` snapshot in the
[original-profile retry archive](../results/archives/grid_gdp_retry_all_20261009_153057_czhvd9w7.zip).
The source guard rejects corrected solver code without the explicit flag.

Validation reproduced all three FBBT failures, checked all 2,883 affected grid
points with and without MC++, and completed the Alpine1/LOA regression. A
restricted 4-by-4 candidate-set smoke test also completed all nine affected
RIC/GLOA/LOA combinations with native HiGHS and MC++. Those smoke tests are
algorithm checks, not Dantzig GAMS/BARON benchmark measurements. Dropwave/LOA
can report its existing skipped-cut warning at radius zero without throwing
an exception. The [completed corrected Dantzig run](../results/grid_gdp_corrected_20261009/README.md)
records ten target hits, seven optimal terminations and three time limits,
with no errors.

## Retry only recorded benchmark errors

`retry-errors` reads the original run's sealed `status="error"` records and
creates a **new run with exactly those grid/method pairs**. It never measures
the 20,181 points again, overwrites original results, or includes successful,
time-limited or unsupported cases. Every selected case gets one fresh attempt;
a repeated error stays an error instead of triggering an unlimited retry loop.
Solver settings, time limits and the CPU are inherited from the original run.
Without the explicit correction profile, this command does **not** fix FBBT
or differentiation errors. `--error-kind
network` is the recommended first retry for the October 9 run: 11 network
errors. `--error-kind all` selects all 21 errors, including the nine FBBT and
one differentiation errors that may recur unchanged.

For a new experiment created with this runner, use the same extracted source
directory to preview its exact error selection without solver calls or new results:

```bash
bash run_grid_gdp_dantzig.sh retry-errors \
  --run-dir /absolute/path/from/RUN_DIR \
  --error-kind all --dry-run
```

Retry the selected errors in a separate run:

```bash
GRID_GDP_CPU=6 nohup bash run_grid_gdp_dantzig.sh retry-errors \
  --run-dir /absolute/path/from/RUN_DIR \
  --error-kind all \
  > /local/scratch/a/lee4382/repository/RBFopt_Test/grid_gdp_retry_errors.log 2>&1 &

tail -n 50 -f /local/scratch/a/lee4382/repository/RBFopt_Test/grid_gdp_retry_errors.log
```

Use `--error-kind network` instead of `all` to select network errors only.
Additional selectors are `fbbt`, `differentiation`, and `other`. Do not launch
the all-errors and network-only commands concurrently on the same CPU.

The new run prints `RUN_DIR` and `RESULT_ZIP`, and retains `retry_plan.json`
with the original run path, result hashes and error causes. Its summary counts
the exact selected pairs (21 or 11), not their Cartesian product, and reports
`planned_points=0`. Source snapshots, solver logs, settings and runtime identity
remain recorded. Original model/input/solver files must match the original
source hashes; changing the solver implementation requires a separate profile.

If interrupted, use `resume --run-dir NEW_RETRY_RUN_DIR` from this updated
package. Resume processes unfinished attempts only. If a retry itself ends in
an error, that attempt is terminal and retained. Another explicit
`retry-errors --run-dir NEW_RETRY_RUN_DIR` creates a separate subsequent attempt.

## Solver profile matched to the current process comparison

| Method | Solver | Internal/master configuration |
|---|---|---|
| Big-M, Hull | GAMS BARON | CPLEX (`LPSol 3`), IPOPT (`NLPSol 9`), no warm start |
| GDPopt RIC, GLOA, LOA | BARON NLP + HiGHS MILP | BARON CLP/CBC (`LPSol 8`), IPOPT (`NLPSol 9`) |
| Every fixed grid point | GAMS IPOPT | MUMPS, `tol=1e-8`, `bound_relax_factor=0`, `max_iter=3000`, no NLP warm start |

The profile is taken from the final selected process experiments: September 25
Big-M/Hull and October 1 BARON/HiGHS RIC/GLOA/LOA. `grid_gdp_process_profile.json`
records their source-manifest hashes and settings. Full-GDP jobs reuse the
existing `gdp_models.comparison.solve_method` implementation and watchdog:
1,800 seconds per method, including transformation, search and validation;
all subsolver calls share the remaining budget. GAMS uses `optcr=1e-5`,
`optca=0`, `threads=1`; GDPopt bound tolerance is `1e-5`. The Column-specific
`LBTTDo 0` workaround does not apply to grid models.

The expected Dantzig runtime is GAMS 52.2 and Pyomo 6.10.0 with the existing
MC++ build. Numerical-library thread counts are forced to one before import;
workers and GAMS processes inherit CPU affinity. CPU 6 is the wrapper default,
leaving the existing RBFOpt CPU 0 and BAM CPU 2 runs separate; verify that the
chosen CPUs belong to different physical cores and are available.

## BARON expression compatibility

GAMS/BARON 52 does not support sine/cosine. Sixteen original grid objectives
contain those functions. Their Big-M/Hull jobs explicitly record
`unsupported_expression`, preserving the original analytic formulation and
not replacing BARON or using a CSV lookup. The five objectives without sine
or cosine are camel3, hosaki, rosenbrock, styblinski_tang and sum_of_squares.
GDPopt jobs are attempted with the specified solvers; any subproblem or
relaxation failure is preserved in its result and logs. This package does not
promise that all 105 jobs obtain solutions. IPOPT point timings cover all 21
grids regardless of BARON compatibility.

See [GAMS 52 BARON functions](https://www.gams.com/52/docs/S_BARON.html#BARON_ALLOWABLE_NONLINEAR_FUNCTIONS).

## Build, upload and execute a new experiment

From the repository root on the Mac, create a bundle in temporary storage:

```bash
cd /Users/albertlee0125/Repos/RBFopt_Test
python grid_gdp_benchmark.py bundle --output /tmp/grid_gdp_runner.zip
scp /tmp/grid_gdp_runner.zip /tmp/grid_gdp_runner.zip.sha256 \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
ssh lee4382@dantzig.ecn.purdue.edu
```

On Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c grid_gdp_runner.zip.sha256 &&
unzip -n grid_gdp_runner.zip -d grid_gdp_package &&
cd grid_gdp_package/grid_gdp_runner &&
sha256sum -c SHA256SUMS

/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-gdp/bin/python cpu_affinity.py --check-pair 0 6 &&
/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-gdp/bin/python cpu_affinity.py --check-pair 2 6 &&
GRID_GDP_CPU=6 bash run_grid_gdp_dantzig.sh check

GRID_GDP_CPU=6 nohup bash run_grid_gdp_dantzig.sh run > ../grid_gdp_benchmark.log 2>&1 &
tail -f ../grid_gdp_benchmark.log
```

The bundle command refuses to overwrite an existing ZIP; choose a fresh output
name and extraction directory for another version. The bundle contains source,
all 21 grids, instructions and member checksums. Generated execution ZIPs need
not be committed alongside their source. For an existing run, retain its
original extraction: resume and historical retries enforce source hashes,
including model documentation, as well as runtime and CPU identity.

The existing GDP Python environment and solver installations are reused. Only
if required, `bash run_grid_gdp_dantzig.sh setup` installs the process comparison
requirements and builds its pinned MC++ interface. Override `GRID_GDP_PYTHON`,
`GRID_GDP_REPOSITORY`, `GAMS_BIN`, `GDP_GAMS_VERSION`, or `PYOMO_CONFIG_DIR` when
using another installation. An override is recorded in the experiment.

For separate phases, run one of these instead of the combined `run`:

```bash
GRID_GDP_CPU=6 nohup bash run_grid_gdp_dantzig.sh points > ../grid_ipopt_points.log 2>&1 &
# After that job finishes, if desired:
GRID_GDP_CPU=6 nohup bash run_grid_gdp_dantzig.sh benchmark > ../grid_gdp_methods.log 2>&1 &
```

`pilot` measures five points per grid (105 calls) to estimate time before a
full point sweep. It is explicitly labeled a sample. `--grids ackley` selects
one grid; `--point-indices 0,480,960` selects indices `31*i+j`; `--methods hull`
selects a full-GDP method. Without selection flags, every point is measured
once. `--point-seconds 60` is a solver safety cap, not a claim that a point
requires 60 seconds. The external watchdog allows another 120 seconds for
GAMS startup, result handling and cleanup before stopping a stuck point worker.

## What is timed

Every point builds a fresh analytic GDP, fixes its two discrete coordinates,
eliminates disjunctions, and actually invokes GAMS/IPOPT. All original variables
are fixed. The standard GAMS writer creates an objective variable/equation,
so IPOPT is still called without inventing an extra physical optimization
problem. Solver logs must demonstrate the invocation; a formula-only shortcut
is not accepted as an IPOPT timing.
Solver availability and version checks occur before timing; each timed point
has one actual IPOPT invocation, without a hidden GAMS availability-test solve.

The result separates:

- `preparation_wall_s`: fresh GDP construction, point fixing and transformation.
- `solver_call_wall_s`: GAMS model writing, process startup, IPOPT execution and
  result reading (the measured external evaluation call).
- `gams_solve_s`: raw GAMS `ETSOLVE`, nested inside the preceding timer.
- `ipopt_reported_s`: IPOPT's own reported duration, also nested.
- `verification_wall_s`: objective and solver-status checks.
- `point_wall_s`: full evaluation clock including preparation, call and checks.
- `recording_and_cleanup_wall_s`: log archival and temporary-file cleanup,
  outside `point_wall_s`.

Do not sum nested solver timers. The per-point budget for replacing a recorded
DFO lookup is `point_wall_s`. Formula/CSV agreement uses `1e-12`; the returned
GAMS scalar is compared at `1e-7`, accounting for solver tolerance/output.
Normalization constants and all-961-point audits are computed once before
each grid's timing loop and recorded separately as preparation. No reference
optimal coordinates are supplied to full-GDP searches.

Grid-fixed NLPs have zero original continuous degrees of freedom. Their measured
cost will primarily describe preparation and the solver invocation. This is
reported explicitly rather than presented as a difficult continuous search.

## Output, resume and download

Each invocation prints `RUN_DIR`, then ultimately `RESULT_ZIP`. Results live
under `results/grid_gdp_benchmark/` and include source snapshots and checksums.

- `point_timings.csv`: one row per accepted IPOPT evaluation, indexed by grid
  and coordinate, with raw statuses and timing components.
- `point_budget_summary.csv/.json`: per-grid mean, median, p95, p99, maximum
  and sum; estimated costs for 10/30/50/70/100 DFO evaluations.
- `suggested_timeout_s`: twice the observed maximum rounded up to a second;
  this is an engineering margin, not a guaranteed runtime bound.
- `points/<grid>/evaluations.jsonl`: immediately flushed, checksummed records.
- `points/<grid>/ipopt.log`: solver invocation evidence for every measured point.
- `points/<grid>/failures.jsonl`: failed attempts, retained separately and
  retried on resume; completed accepted points are not rerun.
- `benchmark.csv` and `benchmark/<grid>/<method>/`: original process runner
  results, solver calls, validated solution coordinates, reference gaps and
  success/failure/unsupported statuses. A target hit is distinct from a global
  optimality certificate; GDPopt bounds retain the process audit's caveats.

Aggregate CSVs are updated after each grid or method and when packing. Progress
updates every 25 points. After an interruption, from this extraction:

```bash
bash run_grid_gdp_dantzig.sh status --run-dir /absolute/path/from/RUN_DIR
nohup bash run_grid_gdp_dantzig.sh resume --run-dir /absolute/path/from/RUN_DIR > ../grid_gdp_resume.log 2>&1 &
```

Resume checks the original source, runtime, CPU, point-record hashes and grid
identities. No active coordinator/point worker may be duplicated. Failed point
attempts remain in their own journal. To pack a stopped run, use
`bash run_grid_gdp_dantzig.sh pack --run-dir /absolute/path/from/RUN_DIR`.

From a Mac terminal, after completion:

```bash
mkdir -p ~/Downloads/grid_gdp_benchmark
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdp_benchmark/grid_gdp_*.zip' \
    'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdp_benchmark/grid_gdp_*.zip.sha256' \
    ~/Downloads/grid_gdp_benchmark/
cd ~/Downloads/grid_gdp_benchmark
shasum -a 256 -c *.zip.sha256
```

Local validation runs are labeled with their actual host/GAMS version. Their
timings are not substituted for measurements on Dantzig.
